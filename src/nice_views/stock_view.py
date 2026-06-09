from nicegui import ui
import sys
import os

# Гарантируем, что src/ в sys.path при импорте модуля напрямую
_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import db
from nice_views.shared_layout import build_shell


def setup_page():
    @ui.page('/stock')
    def stock_page():
        build_shell('/stock')

        # --- ОСНОВНОЙ КОНТЕНТ ---
        with ui.column().classes('w-full p-4 gap-4'):
            ui.label('Актуальные остатки').classes('text-2xl font-bold')

            # Загружаем данные (из lru_cache — мгновенно при повторном визите)
            df = db.load_inventory()

            if df.empty:
                ui.label('⚠️ База данных пуста или файл не найден.').classes('text-red-500 text-lg')
                return

            # Статистика строкой
            latest_date = df['last_seen_date'].max() if 'last_seen_date' in df.columns else '—'
            actual_count = int(df['actual'].sum()) if 'actual' in df.columns else len(df)
            total_count = len(df)

            with ui.row().classes('gap-6 mb-2'):
                with ui.card().classes('p-3 bg-blue-50'):
                    ui.label(f'Всего позиций: {total_count}').classes('font-semibold')
                with ui.card().classes('p-3 bg-green-50'):
                    ui.label(f'Актуальных: {actual_count}').classes('font-semibold text-green-700')
                with ui.card().classes('p-3 bg-gray-50'):
                    ui.label(f'Дата обновления: {latest_date}').classes('font-semibold text-gray-600')

            # Колонки для AgGrid (исключаем технические поля)
            exclude_cols = {'_search_index', 'actual'}
            columns = [
                {
                    'field': col,
                    'headerName': col,
                    'sortable': True,
                    'filter': True,
                    'resizable': True,
                    'floatingFilter': True,
                }
                for col in df.columns if col not in exclude_cols
            ]

            # Конвертируем DataFrame → список словарей (AgGrid требует JSON-сериализуемые данные)
            rows = df.drop(columns=[c for c in exclude_cols if c in df.columns]).to_dict('records')

            # Супер-быстрая таблица AgGrid
            ui.aggrid({
                'columnDefs': columns,
                'rowData': rows,
                'rowSelection': 'single',
                'pagination': True,
                'paginationPageSize': 100,
                'defaultColDef': {
                    'minWidth': 80,
                    'flex': 1,
                },
                'domLayout': 'autoHeight',
            }).classes('w-full')
