"""
main.py — точка входа нового приложения на NiceGUI.
Запуск: python src/main.py
"""
import sys
import os

# Добавляем src/ в путь поиска модулей, чтобы работали импорты db, nice_views и т.д.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nicegui import ui
import db
from nice_views import stock_view

# --- Инициализация: прогреваем кэш БД при старте ---
try:
    db.get_db_stats()
except Exception as e:
    print(f"[WARN] Не удалось получить статистику БД при старте: {e}")


# ─────────────────────────────────────────────
#  ГЛАВНАЯ СТРАНИЦА — Дашборд / Приветствие
# ─────────────────────────────────────────────
@ui.page('/')
def index():
    # Drawer создаём первым, чтобы header мог его переключать
    with ui.left_drawer(elevated=True, value=True).classes('bg-blue-50 pt-4') as left_drawer:
        ui.label('Навигация').classes('text-lg font-bold q-px-md q-mb-sm')
        ui.separator()

        with ui.column().classes('gap-1 q-px-sm q-pt-sm'):
            ui.button('📦  Склад',      on_click=lambda: ui.navigate.to('/stock')).props('flat align=left').classes('w-full text-left')
            ui.button('⚠️  Аномалии',   on_click=lambda: ui.notify('В разработке…', type='info')).props('flat align=left').classes('w-full text-left')
            ui.button('📥  Приёмка',    on_click=lambda: ui.notify('В разработке…', type='info')).props('flat align=left').classes('w-full text-left')
            ui.button('📊  Аналитика',  on_click=lambda: ui.notify('В разработке…', type='info')).props('flat align=left').classes('w-full text-left')

    # Шапка
    with ui.header(elevated=True).classes('bg-primary text-white items-center justify-between'):
        ui.button(on_click=lambda: left_drawer.toggle(), icon='menu').props('flat color=white')
        ui.label('🏭 Shadow Stock ERP').classes('text-xl font-bold')
        ui.space()

    # Контент главной страницы
    with ui.column().classes('w-full items-center justify-center q-pa-xl gap-6'):
        ui.icon('inventory_2', size='80px').classes('text-primary')
        ui.label('Добро пожаловать!').classes('text-3xl font-bold')
        ui.label('Shadow Stock ERP — новый интерфейс на базе NiceGUI').classes('text-xl text-gray-500')
        ui.separator().classes('w-64')

        with ui.row().classes('gap-4 flex-wrap justify-center'):
            with ui.card().classes('cursor-pointer hover:shadow-lg transition-shadow p-6 items-center gap-2').on('click', lambda: ui.navigate.to('/stock')):
                ui.icon('warehouse', size='48px').classes('text-blue-500')
                ui.label('📦 Склад').classes('text-lg font-semibold')
                ui.label('Актуальные остатки').classes('text-gray-500 text-sm')

            with ui.card().classes('cursor-pointer hover:shadow-lg transition-shadow p-6 items-center gap-2').on('click', lambda: ui.notify('В разработке…', type='info')):
                ui.icon('warning_amber', size='48px').classes('text-orange-500')
                ui.label('⚠️ Аномалии').classes('text-lg font-semibold')
                ui.label('Скачки остатков').classes('text-gray-500 text-sm')

            with ui.card().classes('cursor-pointer hover:shadow-lg transition-shadow p-6 items-center gap-2').on('click', lambda: ui.notify('В разработке…', type='info')):
                ui.icon('move_to_inbox', size='48px').classes('text-green-500')
                ui.label('📥 Приёмка').classes('text-lg font-semibold')
                ui.label('Входящие поставки').classes('text-gray-500 text-sm')


# ─────────────────────────────────────────────
#  Подключаем все дочерние страницы
# ─────────────────────────────────────────────
stock_view.setup_page()


# ─────────────────────────────────────────────
#  Запуск сервера
# ─────────────────────────────────────────────
if __name__ in {'__main__', '__mp_main__'}:
    ui.run(
        title='Shadow Stock ERP',
        port=8080,
        language='ru',
        favicon='🏭',
        reload=False,        # отключаем авто-перезапуск в продакшне
    )
