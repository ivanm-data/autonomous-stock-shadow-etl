"""
main.py — точка входа нового приложения на NiceGUI.
Запуск: python src/main.py
"""
import sys
import os
import logging
import traceback
from pathlib import Path

# Добавляем src/ в путь поиска модулей
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ─── Логирование ──────────────────────────────────────────────────────────────
LOG_PATH = Path(__file__).resolve().parent.parent / 'logs' / 'nicegui.log'
LOG_PATH.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)
logger = logging.getLogger('shadow_stock')
logger.info('=== Autonomous Stock Shadow ETL starting ===')
logger.info(f'Log file: {LOG_PATH}')

from nicegui import ui, app
import db
from nice_views import stock_view, anomalies_view
from nice_views.shared_layout import build_shell, DARK_CSS

# ─── Перехватчик необработанных исключений NiceGUI ────────────────────────────
def on_unhandled_exception(e: Exception) -> None:
    logger.error('=== UNHANDLED EXCEPTION IN NICEGUI ===')
    logger.error(traceback.format_exc())

app.on_exception(on_unhandled_exception)

# ─── Прогрев кэша при старте ──────────────────────────────────────────────────
try:
    db.get_db_stats()
    logger.info('DB stats loaded OK')
except Exception as e:
    logger.warning(f'Could not load DB stats: {e}')


# ─────────────────────────────────────────────────────────────────────────────
#  ГЛАВНАЯ СТРАНИЦА — Дашборд
# ─────────────────────────────────────────────────────────────────────────────
@ui.page('/')
def index():
    build_shell('/')
    ui.add_css(DARK_CSS)

    with ui.column().classes('w-full items-center q-pa-xl gap-8').style('background-color:#0d0d0d; min-height:100vh;'):

        # ── Приветствие ───────────────────────────────────────────────────
        with ui.column().classes('items-center gap-2 pt-8'):
            ui.icon('diamond', size='64px').style('color: #60a5fa;')
            ui.label('Autonomous Stock Shadow ETL').classes('text-white font-bold').style('font-size:2rem;')
            ui.label('Система теневого контроля складских остатков').style('color:#9ca3af; font-size:1rem;')

        ui.separator().style('background-color:#2a2a2a; width:400px;')

        # ── Карточки навигации: ОПЕРАЦИИ ─────────────────────────────────
        ui.label('🛠 ОПЕРАЦИИ').style('color:#6b7280; font-size:0.7rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase;')

        with ui.row().classes('gap-4 flex-wrap justify-center'):

            def _card(icon: str, icon_color: str, title: str, subtitle: str,
                      route: str | None = None, wip: bool = False):
                def click(r=route, w=wip):
                    if w or r is None:
                        ui.notify('🚧 В разработке…', type='info')
                    else:
                        ui.navigate.to(r)
                with ui.card() \
                        .classes('cursor-pointer dark-card p-6 items-center gap-2 transition-all') \
                        .style('min-width:160px;') \
                        .on('click', click):
                    ui.icon(icon, size='48px').style(f'color: {icon_color};')
                    ui.label(title).classes('text-white font-semibold text-base')
                    ui.label(subtitle).style('color:#9ca3af; font-size:0.8rem;')

            _card('warehouse',     '#60a5fa', '📦 Склад',    'Актуальные остатки',   '/stock')
            _card('warning_amber', '#f97316', '⚠️ Аномалии', 'Скачки остатков',      '/anomalies')
            _card('task_alt',      '#ef4444', '🔥 Задачи',   'Открытые инциденты',   wip=True)
            _card('move_to_inbox', '#22c55e', '📥 Приёмка',  'Входящие поставки',    wip=True)

        # ── Карточки навигации: АНАЛИТИКА ────────────────────────────────
        ui.label('📊 АНАЛИТИКА И KPI').style('color:#6b7280; font-size:0.7rem; font-weight:700; letter-spacing:0.1em; text-transform:uppercase; margin-top:8px;')

        with ui.row().classes('gap-4 flex-wrap justify-center'):
            _card('leaderboard',   '#a78bfa', '🎯 Эффективность',  'KPI и SLA',            wip=True)
            _card('severe_cold',   '#38bdf8', '❄️ Неликвиды',      'Мёртвый сток',          wip=True)
            _card('trending_up',   '#34d399', '📈 Оборачиваемость', 'Скорость продаж',       wip=True)
            _card('science',       '#fb923c', '⚖️ A/B Тест',        'AI vs Человек',         wip=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Подключаем все дочерние страницы
# ─────────────────────────────────────────────────────────────────────────────
stock_view.setup_page()
anomalies_view.setup_page()


# ─────────────────────────────────────────────────────────────────────────────
#  Запуск сервера
# ─────────────────────────────────────────────────────────────────────────────
if __name__ in {'__main__', '__mp_main__'}:
    logger.info('Starting NiceGUI on port 8080')
    ui.run(
        title='Autonomous Stock Shadow ETL',
        port=8080,
        language='ru',
        favicon='💎',
        reload=False,
    )
