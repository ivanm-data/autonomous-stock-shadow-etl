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

class _SuppressWinReset(logging.Filter):
    """Фильтрует бесполезный WinError 10054 из asyncio на Windows."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return 'WinError 10054' not in msg and 'ConnectionResetError' not in msg

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_PATH, encoding='utf-8', mode='w'),
        logging.StreamHandler(sys.stdout),
    ]
)

# Заглушаем шум asyncio/uvicorn на Windows
for _noisy in ('asyncio', 'uvicorn.error', 'uvicorn.access'):
    logging.getLogger(_noisy).addFilter(_SuppressWinReset())

logger = logging.getLogger('shadow_stock')
logger.info('=== Autonomous Stock Shadow ETL starting ===')
logger.info(f'Log file: {LOG_PATH}')

from nicegui import ui, app
import db
from nice_views import stock_view, anomalies_view, receiving_view, tasks_view, efficiency_view, dead_stock_view, velocity_view, ab_test_view, system_view
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
#  Главная — редирект на Склад
# ─────────────────────────────────────────────────────────────────────────────
@ui.page('/')
def index():
    ui.navigate.to('/stock')

# ─────────────────────────────────────────────────────────────────────────────
#  Подключаем все дочерние страницы
# ─────────────────────────────────────────────────────────────────────────────
stock_view.setup_page()
anomalies_view.setup_page()
receiving_view.setup_page()
tasks_view.setup_page()
efficiency_view.setup_page()
dead_stock_view.setup_page()
velocity_view.setup_page()
ab_test_view.setup_page()
system_view.setup_page()


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
