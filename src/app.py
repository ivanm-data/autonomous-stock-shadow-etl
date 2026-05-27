import sys
import streamlit as st
import pandas as pd
from pathlib import Path
import sqlite3
import json
import db
import ai_services
from views import dead_stock_view, efficiency_view, anomalies_view, velocity_view, tasks_view, receiving_view, ab_test_view, stock_view
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from queries import get_anomalies_query, get_insert_anomaly_query, get_close_anomaly_query, get_cancel_anomaly_query, get_sla_metrics_query

import math

# --- ЗАГРУЗКА КОНФИГУРАЦИИ ---
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"

def load_config() -> dict:
    """Загружает конфигурацию из config.json"""
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Конфигурационный файл не найден: {CONFIG_PATH}")
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = load_config()


# --- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ---

def color_rows(row):
    """
    Styler function for Pandas DataFrame to color rows based on anomaly type.
    We use pale, non-distracting colors to maintain focus on data.
    """
    anomaly_type = row['anomaly_type']
    

    colors = {
        'Успешная сверка': 'background-color: rgba(181, 230, 162, 0.4);', # Green
        'Излишек': 'background-color: rgba(255, 230, 156, 0.4);',         # Orange
        'Пересорт (Склад)': 'background-color: rgba(255, 230, 156, 0.4);',# Orange
        'Пересорт (1С)': 'background-color: rgba(255, 230, 156, 0.4);',   # Orange
        'Утеря': 'background-color: rgba(255, 199, 199, 0.4);',           # Red
        'Тихая отмена': 'background-color: rgba(255, 199, 199, 0.4);'     # Red
    }
    
    return [colors.get(anomaly_type, '')] * len(row)

def verify_shadow_forecasts():
    """Обновленная логика: следим за всеми активными прогнозами"""
    with db.get_connection() as conn:
        # 1. Теперь берем ВСЕ статусы, кроме финальных (Упущенная выгода и Точный прогноз)
        forecasts = pd.read_sql_query("""
            SELECT * FROM ai_forecasts 
            WHERE status NOT IN ('📉 Упущенная выгода', '✅ Точный прогноз', '🔄 Пересчитан ИИ')
        """, conn)
        
        if forecasts.empty: return
        
        latest_inv = db.load_inventory()
        if latest_inv.empty: return
        
        today = pd.Timestamp.now().normalize()
        
        for _, row in forecasts.iterrows():
            item_name = row['item_name']
            sku = row['sku']
            db_id = row['id']
            
            # УМНЫЙ ПОИСК: Сначала по SKU (он уникален), если нет - по имени
            match = pd.DataFrame()
            if pd.notna(sku) and str(sku).strip():
                match = latest_inv[latest_inv['Артикул'] == sku]
            
            if match.empty:
                match = latest_inv[latest_inv['Наименование'] == item_name]

            if match.empty: continue # Все еще не нашли - пропускаем
            
            curr_qty = float(match.iloc[0]['Остаток'])
            price = float(match.iloc[0]['Цена'])
            avg_sales = float(row['avg_daily_sales'])
            
            # --- ПРОВЕРКА НА НУЖНОСТЬ ПЕРЕСЧЁТА ПРИ ИЗМЕНЕНИИ lead_time ---
            current_lead_time = CONFIG['ai']['lead_time_days']
            forecast_lead_time = int(row['lead_time_days']) if row['lead_time_days'] else 14
            
            if forecast_lead_time != current_lead_time:
                # Пересчитываем математические параметры
                base_demand = int(curr_qty + avg_sales * current_lead_time)
                safety_stock = int(avg_sales * 0.2)  # Fallback: 20% от avg_sales
                recommended_qty = base_demand + safety_stock
                days_to_zero = round(curr_qty / avg_sales, 1) if avg_sales > 0 else 999.0
                calc_zero_date = (today + pd.Timedelta(days=int(days_to_zero))).strftime('%Y-%m-%d')
                
                conn.execute("""
                    UPDATE ai_forecasts
                    SET predicted_zero_date = ?, recommended_qty = ?,
                        lead_time_days = ?, safety_stock = ?, base_demand = ?,
                        needs_recalc = 0
                    WHERE id = ?
                """, (calc_zero_date, recommended_qty, current_lead_time, safety_stock,
                      base_demand - safety_stock, db_id))
                continue  # Пропускаем стандартную логику
            
            # --- ЗАЩИТА ОТ ИИ-ГАЛЛЮЦИНАЦИЙ (37 апреля и т.д.) ---
            pred_date = pd.to_datetime(row['predicted_zero_date'], errors='coerce')
            if pd.isna(pred_date):
                # Если дата кривая (NaT), ставим безопасную заглушку от "сегодня"
                pred_date = today + pd.Timedelta(days=30)

            if curr_qty <= 0:
                effective_pred_date = min(today, pred_date)
                days_lost = max(1, (today - effective_pred_date).days)
                lost_value = days_lost * avg_sales * price
                
                conn.execute("""
                    UPDATE ai_forecasts
                    SET status = '🔴 Товар отсутствует', lost_sales_value = ?, overstock_value = 0
                    WHERE id = ?
                """, (lost_value, db_id))
                continue

            # Если товар ЕСТЬ, проверяем на Перезатарку (запас > 60 дней)
            if curr_qty > (avg_sales * 60):
                overstock_qty = curr_qty - (avg_sales * 44)
                overstock_value = max(0, overstock_qty * price)
                conn.execute("""
                    UPDATE ai_forecasts
                    SET status = '🧊 Перезатарка', overstock_value = ?, lost_sales_value = 0
                    WHERE id = ?
                """, (overstock_value, db_id))
            else:
                # Если остаток в норме, возвращаем в Наблюдение
                conn.execute("UPDATE ai_forecasts SET status = '⏳ Наблюдение' WHERE id = ?", (db_id,))
        
        conn.commit()



st.set_page_config(page_title="Stock Shadow | Analytics", page_icon="💎", layout="wide")

# Скрываем лишнее
st.markdown("<style>#MainMenu {visibility: hidden;} footer {visibility: hidden;}</style>", unsafe_allow_html=True)

# --- ИНИЦИАЛИЗАЦИЯ ПАМЯТИ ---
if 'dismissed_names' not in st.session_state:
    st.session_state.dismissed_names = []
    if db.DB_PATH.exists():
        try:
            with sqlite3.connect(db.DB_PATH) as conn:
                # Создаем таблицу для хранения связей старых и новых имен
                conn.execute("CREATE TABLE IF NOT EXISTS item_aliases (new_name TEXT, old_name TEXT)")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS expected_deliveries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        item_name TEXT,
                        sku TEXT,
                        qty_expected INTEGER,
                        status TEXT DEFAULT 'Ожидает'
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS ai_forecasts (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        item_name TEXT,
                        sku TEXT,
                        predicted_zero_date DATE,
                        recommended_qty INTEGER,
                        reason TEXT,
                        avg_daily_sales REAL,
                        lead_time_days INTEGER DEFAULT 14,
                        safety_stock INTEGER DEFAULT 0,
                        base_demand INTEGER DEFAULT 0,
                        needs_recalc INTEGER DEFAULT 0,
                        status TEXT DEFAULT '⏳ Наблюдение', -- '⏳ Наблюдение', '📉 Упущенная выгода', '🧊 Перезатарка', '✅ Точный прогноз'
                        lost_sales_value REAL DEFAULT 0,
                        overstock_value REAL DEFAULT 0
                    )
                """)
                conn.commit()
                res = conn.execute("SELECT DISTINCT item_name FROM anomaly_log WHERE detected_at >= datetime('now', '-1 day', 'localtime')").fetchall()
                st.session_state.dismissed_names = [r[0] for r in res]
        except Exception:
            pass

if 'current_page' not in st.session_state:
    st.session_state.current_page = "📦 Склад" 
if 'selected_item_name' not in st.session_state:
    st.session_state.selected_item_name = None

# --- ЛОГИКА НАВИГАЦИИ ---
df_inv = db.load_inventory()
df_anomalies = db.load_anomalies()
db_stats = db.get_db_stats()

# Фильтруем активные аномалии по именам
active_anom_count = len(df_anomalies[~df_anomalies['Наименование'].isin(st.session_state.dismissed_names)]) if not df_anomalies.empty else 0

# Безопасно считаем открытые задачи из базы
try:
    with db.get_connection() as conn:
        open_tasks_count = conn.execute("SELECT COUNT(*) FROM anomaly_log WHERE status = 'Открыта'").fetchone()[0]
except Exception:
    open_tasks_count = 0

with st.sidebar:
    st.title("💎 Autonomous Stock Shadow")

    # --- ОПРЕДЕЛЯЕМ ТЕКУЩУЮ СТРАНИЦУ ---
    base_page = st.session_state.current_page.split(' (')[0]

    # --- СИНХРОНИЗИРУЕМ ВИДЖЕТЫ С ТЕКУЩЕЙ СТРАНИЦЕЙ ДО РЕНДЕРА ---
    # Это критично: если страница была изменена программно (кнопки-баннеры),
    # нужно явно сбросить session_state виджетов, чтобы index сработал правильно
    op_options = ["📦 Склад", f"⚠️ Аномалии ({active_anom_count})", f"🔥 Задачи ({open_tasks_count})", "📥 Приемка"]
    ana_options = ["🎯 Эффективность", "❄️ Неликвиды", "📈 Оборачиваемость", "⚖️ A/B Тест: AI vs Человек"]

    op_match = next((opt for opt in op_options if opt.startswith(base_page)), None)
    ana_match = next((opt for opt in ana_options if opt.startswith(base_page)), None)

    if op_match:
        st.session_state["op_nav"] = op_match
        st.session_state.pop("ana_nav", None)
    elif ana_match:
        st.session_state["ana_nav"] = ana_match
        st.session_state.pop("op_nav", None)

    # --- ЛОГИЧЕСКОЕ РАЗДЕЛЕНИЕ МЕНЮ: ОПЕРАЦИИ ---
    st.caption("🛠 ОПЕРАЦИИ")
    op_idx = next((i for i, opt in enumerate(op_options) if opt.startswith(base_page)), 0)
    op_sel = st.radio("Рабочая область", op_options, index=op_idx, key="op_nav")

    st.write("---")

    # --- ЛОГИЧЕСКОЕ РАЗДЕЛЕНИЕ МЕНЮ: АНАЛИТИКА ---
    st.caption("📊 АНАЛИТИКА И KPI")
    ana_idx = next((i for i, opt in enumerate(ana_options) if opt.startswith(base_page)), None)
    ana_sel = st.radio("Инструменты анализа", ana_options, index=ana_idx, key="ana_nav")

    # --- РЕАГИРУЕМ НА РУЧНОЙ ВЫБОР В МЕНЮ ---
    op_base = op_sel.split(' (')[0] if op_sel else None
    ana_base = ana_sel.split(' (')[0] if ana_sel else None

    if ana_base and ana_base != base_page:
        st.session_state.current_page = ana_base
        st.rerun()
    elif op_base and op_base != base_page:
        st.session_state.current_page = op_base
        st.rerun()

    # --- СИСТЕМНЫЕ КНОПКИ ---
    st.write("---")
    if db_stats:
        st.caption("📂 Статистика базы")
        st.info(f"Дней в базе: {db_stats['days_count']}")
    
    if st.button("🔄 Обновить данные", width="stretch"):
        st.cache_data.clear()
        st.rerun()

# --- СТРАНИЦЫ ---
st.title(f"{st.session_state.current_page}")

# 1. СТРАНИЦА СКЛАДА
if st.session_state.current_page == "📦 Склад":
    stock_view.show(df_inv, df_anomalies)

# 2. СТРАНИЦА АНОМАЛИЙ
elif st.session_state.current_page == "⚠️ Аномалии":
    anomalies_view.show(df_anomalies, df_inv)
# 3. СТРАНИЦА ЭФФЕКТИВНОСТИ И KPI (бывший Архив)
elif st.session_state.current_page == "🎯 Эффективность":
    efficiency_view.show()

# 4. СТРАНИЦА НЕЛИКВИДОВ
elif st.session_state.current_page == "❄️ Неликвиды":
    dead_stock_view.show()

# 5. СТРАНИЦА ОБОРАЧИВАЕМОСТИ
elif st.session_state.current_page == "📈 Оборачиваемость":
    velocity_view.show()

elif st.session_state.current_page == "🔥 Задачи":
    tasks_view.show()

elif st.session_state.current_page == "📥 Приемка":
    receiving_view.show()

elif st.session_state.current_page == "⚖️ A/B Тест: AI vs Человек":
    ab_test_view.show()