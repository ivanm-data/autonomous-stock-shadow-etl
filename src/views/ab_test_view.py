import streamlit as st
import pandas as pd
import sqlite3
from pathlib import Path
import db
import ai_services


def show():
    st.subheader("⚖️ A/B Тест: AI-прогноз vs Человеческие решения")
    st.caption("Теневой режим работы: алгоритм делает прогнозы закупок и сверяет их с реальными действиями менеджеров. Это позволяет оценить упущенную выгоду без вмешательства в текущие бизнес-процессы.")
    
    # --- ИНДИКАТОР ПРОГРЕВА МОДЕЛИ (COLD START) ---
    with db.get_connection() as conn:
        # Считаем, сколько дней истории у нас есть
        days_in_db_query = "SELECT COUNT(DISTINCT SUBSTR(report_timestamp, 1, 10)) FROM stocks"
        days_in_db = conn.execute(days_in_db_query).fetchone()[0]
        
    if days_in_db < 30:
        st.warning(f"⚠️ **Модель в стадии 'прогрева' (Cold Start):** Накоплено данных за {days_in_db} из 30 необходимых дней. До завершения сбора полной базы, ИИ экстраполирует короткие тренды, что может приводить к повышенной погрешности (ложным срабатываниям Перезатарки).")
    else:
        st.success(f"✅ **Модель обучена:** Накоплено данных за {days_in_db} дней. Точность прогнозов оптимальна.")

    # 1. Запускаем фоновую проверку прогнозов при входе на вкладку
    verify_shadow_forecasts()
    
    with db.get_connection() as conn:
        # Подтягиваем прогнозы + актуальный остаток прямо из таблицы stocks
        df_forecasts = pd.read_sql_query("""
            SELECT 
                f.*,
                (SELECT quantity FROM stocks s WHERE s.item_name = f.item_name ORDER BY report_timestamp DESC LIMIT 1) as current_qty
            FROM ai_forecasts f 
            ORDER BY f.created_at DESC
        """, conn)

    if df_forecasts.empty:
        st.info("Пока нет активных прогнозов. Сгенерируйте их с помощью кнопки ниже.")
    else:
        # 2. Считаем продуктовые метрики (Shadow ROI)
        total_lost = df_forecasts['lost_sales_value'].sum()
        total_overstock = df_forecasts['overstock_value'].sum()
        
        m1, m2 = st.columns(2)
        m1.metric("📉 Упущенная выгода (Prevented Lost Sales)", f"{total_lost:,.0f} ₽".replace(',', ' '), help="Сколько компания потеряла из-за того, что товар кончился, а закупка не была сделана вовремя.")
        m2.metric("🧊 Замороженный капитал за последние 30 дней (Cost of Overstock)", f"{total_overstock:,.0f} ₽".replace(',', ' '), help="Сумма излишков, купленных сверх рекомендаций ИИ.")
        
        st.write("---")
        st.write("**Детализация (Журнал прогнозов и финансовых последствий):**")
        
        # Берем нужные колонки (добавлен current_qty)
        display_df = df_forecasts[['created_at', 'item_name', 'current_qty', 'predicted_zero_date', 'recommended_qty', 'reason', 'status', 'lost_sales_value', 'overstock_value']].copy()
        
        # Делаем остаток красивым целым числом
        display_df['current_qty'] = display_df['current_qty'].fillna(0).astype(int)
        
        display_df['Упущенная выручка (₽)'] = display_df['lost_sales_value'].apply(lambda x: f"{x:,.0f} ₽".replace(',', ' ') if x > 0 else "")
        display_df['Заморожено (₽)'] = display_df['overstock_value'].apply(lambda x: f"{x:,.0f} ₽".replace(',', ' ') if x > 0 else "")
        
        display_df.rename(columns={
            'created_at': 'Дата прогноза',
            'item_name': 'Товар',
            'current_qty': 'Остаток (шт)',  # <--- ВОТ ЭТА НОВАЯ СТРОЧКА
            'predicted_zero_date': 'ИИ: Обнулится',
            'recommended_qty': 'ИИ: Заказать (шт)',
            'reason': 'Обоснование',
            'status': 'Статус / Результат'
        }, inplace=True)
        
        # Отрезаем секунды у даты
        display_df['Дата прогноза'] = display_df['Дата прогноза'].str[:10]
        
        # Отрисовываем таблицу, убрав сырые технические колонки с нулями
        st.dataframe(
            display_df.drop(columns=['lost_sales_value', 'overstock_value']), 
            use_container_width=True, 
            hide_index=True
        )

    st.divider()
    
    pending_flag = Path("logs/ai_pending.flag")
    
    # 1. Считаем прогнозы за сегодня для понимания статуса
    with sqlite3.connect(db.DB_PATH) as conn:
         forecasts_today = conn.execute("SELECT COUNT(*) FROM ai_forecasts WHERE date(created_at) = date('now', 'localtime')").fetchone()[0]

    # 2. Информационные уведомления
    if pending_flag.exists():
        st.warning("⚠️ **Есть необработанные данные:** Парсер собрал свежую информацию, но ИИ-анализ ещё не запущен. Нажмите кнопку ниже.")
        btn_text = "🚀 Запустить анализ свежих данных"
        btn_type = "primary"
    elif forecasts_today > 0:
        st.info(f"✅ **План на сегодня выполнен.** В базе уже есть {forecasts_today} прогнозов за текущие сутки.")
        btn_text = "🔄 Принудительный пересчет"
        btn_type = "secondary"
    else:
        btn_text = "🚀 Запустить первичный анализ"
        btn_type = "primary"

    # 3. Кнопка запуска (Всегда активна, чтобы пользователь мог сам проверить связь)
    if st.button(btn_text, type=btn_type, use_container_width=True):
        with st.spinner("🤖 ИИ анализирует графики продаж..."):
            try:
                status = ai_services.run_batch_forecast()
                
                if status == "no_key":
                    st.error("❌ Не найден API ключ Gemini!")
                elif status == "empty":
                    st.warning("⚠️ Не найдено товаров для анализа.")
                    if pending_flag.exists(): pending_flag.unlink()
                elif status and status.startswith("error_"):
                    # Вот здесь пользователь увидит реальную ошибку прокси/связи, если она есть
                    err_text = status.split('_', 1)[1]
                    st.error(f"❌ Ошибка связи с ИИ: {err_text}")
                elif status and status.startswith("ok_"):
                    count = status.split('_')[1]
                    st.success(f"✅ Готово! Сгенерировано прогнозов: {count}.")
                    if pending_flag.exists(): pending_flag.unlink()
                         
            except Exception as e:
                st.error(f"❌ Критическая ошибка: {e}")
