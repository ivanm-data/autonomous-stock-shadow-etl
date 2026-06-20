"""
velocity_view.py — NiceGUI-версия вкладки «Оборачиваемость».
Полный перенос функционала из src/views/velocity_view.py.

Открывается двумя способами:
  1. /velocity?item=<name>&sku=<sku>  — drill-down из вкладки Склад
  2. /velocity                         — standalone: форма поиска товара
"""
from nicegui import ui, run as ng_run
from starlette.requests import Request
import sys
import os
import logging
from urllib.parse import quote, unquote
import pandas as pd

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import db
from nice_views.shared_layout import build_shell

logger = logging.getLogger('shadow_stock.velocity')


# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательные рендеры
# ─────────────────────────────────────────────────────────────────────────────

def _render_empty_state():
    """Показывается когда товар не выбран."""
    with ui.card().classes('w-full p-8 items-center').style(
        'background:#111111; border:1px solid #2a2a2a; text-align:center;'
    ):
        ui.icon('show_chart', size='64px').style('color:#374151;')
        ui.label(
            '👈 Перейдите во вкладку «📦 Склад», '
            'найдите нужный товар через поиск и нажмите «📈 График».'
        ).classes('text-gray-400 text-sm mt-3')
        ui.label(
            'Или введите наименование товара ниже:'
        ).style('color:#6b7280; font-size:0.8rem; margin-top:8px;')


def _render_search_form():
    """Поле ручного поиска для standalone-режима."""
    with ui.card().classes('w-full p-4').style(
        'background:#111111; border:1px solid #2a2a2a;'
    ):
        ui.label('Поиск по наименованию').style(
            'color:#9ca3af; font-size:0.82rem; margin-bottom:4px;'
        )
        with ui.row().classes('w-full gap-2'):
            inp = ui.input(placeholder='Введите название товара…').classes('flex-1').style(
                'background:#1a1a1a; color:white;'
            )

            def go():
                v = inp.value.strip()
                if v:
                    ui.navigate.to(f'/velocity?item={quote(v)}')
                else:
                    ui.notify('Введите название товара', type='warning')

            inp.on('keydown.enter', lambda: go())
            ui.button('🔍 Найти', on_click=go).props('color=primary no-caps')


def _render_velocity(item_name: str, sku: str, history=None):
    """Рисует всю карточку оборачиваемости для конкретного товара."""
    # history передаётся снаружи (загружается через run.io_bound в page handler)
    if history is None:
        history = db.load_velocity_history(item_name, sku)

    # ── Заголовок + кнопка «Назад» ─────────────────────────────────────────
    with ui.row().classes('w-full items-center gap-3 flex-wrap'):
        ui.button('🔙 Назад на склад', on_click=lambda: ui.navigate.to('/stock')) \
          .props('flat no-caps').style('color:#9ca3af;')
        ui.label(item_name).classes('text-white text-xl font-bold flex-1')
        if sku and sku != 'nan':
            ui.label(f'🏷 {sku}').classes('font-mono').style('color:#6b7280;')

    ui.separator().style('background:#2a2a2a;')

    # ── Мало данных ─────────────────────────────────────────────────────────
    if len(history) < 2:
        with ui.card().classes('w-full p-4').style(
            'background:#1e3a5f; border:1px solid #1e40af;'
        ):
            ui.label(
                '⚠️ Мало данных для графика. '
                'Нужно накопить хотя бы 2 среза базы данных.'
            ).classes('text-blue-200 text-sm')
        return

    # ── Метрики ─────────────────────────────────────────────────────────────
    curr_qty  = int(history['Остаток'].iloc[-1])
    prev_qty  = int(history['Остаток'].iloc[-2])
    delta     = curr_qty - prev_qty
    delta_col = '#22c55e' if delta >= 0 else '#ef4444'
    delta_pfx = '+' if delta > 0 else ''

    with ui.row().classes('gap-4 flex-wrap'):
        with ui.card().classes('p-4').style(
            'background:#171717; border-left:3px solid #34d399;'
        ):
            ui.label(f'{curr_qty} шт.').classes('text-white text-2xl font-bold')
            ui.label('Текущий остаток').style('color:#9ca3af; font-size:0.8rem;')

        with ui.card().classes('p-4').style(
            f'background:#171717; border-left:3px solid {delta_col};'
        ):
            ui.label(f'{delta_pfx}{delta} шт.').classes('text-white text-2xl font-bold') \
              .style(f'color:{delta_col};')
            ui.label('Сдвиг (к прошлой записи)').style(
                'color:#9ca3af; font-size:0.8rem;'
            )

    # ── График оборачиваемости ───────────────────────────────────────────────
    dates  = history.index.strftime('%Y-%m-%d').tolist()
    values = history['Остаток'].tolist()

    ui.echart({
        'backgroundColor': 'transparent',
        'tooltip': {'trigger': 'axis'},
        'xAxis': {
            'type': 'category',
            'data': dates,
            'axisLabel': {'color': '#6b7280', 'rotate': 20, 'fontSize': 11},
            'axisLine': {'lineStyle': {'color': '#2a2a2a'}},
        },
        'yAxis': {
            'type': 'value',
            'axisLabel': {'color': '#6b7280'},
            'splitLine': {'lineStyle': {'color': '#1f1f1f'}},
        },
        'series': [{
            'type': 'line',
            'data': values,
            'smooth': True,
            'symbol': 'circle',
            'symbolSize': 6,
            'lineStyle': {'color': '#34d399', 'width': 2},
            'itemStyle': {'color': '#34d399'},
            'areaStyle': {
                'color': {
                    'type': 'linear',
                    'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                    'colorStops': [
                        {'offset': 0, 'color': 'rgba(52,211,153,0.3)'},
                        {'offset': 1, 'color': 'rgba(52,211,153,0.02)'},
                    ],
                }
            },
            'markLine': {
                'silent': True,
                'lineStyle': {'color': '#6b7280', 'type': 'dashed'},
                'data': [{'type': 'average', 'name': 'Среднее'}],
                'label': {'color': '#9ca3af', 'fontSize': 11},
            },
        }],
        'grid': {'left': '3%', 'right': '4%', 'bottom': '15%', 'containLabel': True},
    }).classes('w-full').style('height:320px;')

    ui.separator().style('background:#2a2a2a;')

    # ── Журнал движений ─────────────────────────────────────────────────────
    ui.label('📋 Журнал движений товара').classes('text-white text-lg font-semibold')

    movements = history.copy().reset_index()
    movements['Дельта'] = movements['Остаток'].diff()
    movements = movements.dropna(subset=['Дельта'])
    movements = movements[movements['Дельта'] != 0].copy()

    if movements.empty:
        ui.label('Движений по данному товару не зафиксировано.').style(
            'color:#6b7280;'
        )
        return

    movements['Событие']          = movements['Дельта'].apply(
        lambda x: '📦 Приход (или излишек)' if x > 0 else '🛒 Расход (или утеря)'
    )
    movements['Кол-во']           = movements['Дельта'].abs().astype(int)
    movements['Остаток']          = movements['Остаток'].astype(int)
    movements['Дата фиксации']    = movements['Дата'].dt.strftime('%Y-%m-%d')
    movements['Фактическое время'] = (
        movements['Дата'] - pd.Timedelta(days=1)
    ).dt.strftime('%Y-%m-%d') + ' (вчера/ночь)'

    display_df = movements[
        ['Дата фиксации', 'Фактическое время', 'Событие', 'Кол-во', 'Остаток']
    ].sort_values('Дата фиксации', ascending=False)

    col_defs = [
        {'field': 'Дата фиксации',    'headerName': 'Дата фиксации',    'flex': 1, 'sortable': True},
        {'field': 'Фактическое время', 'headerName': 'Фактическое время', 'flex': 1, 'sortable': True},
        {
            'field': 'Событие', 'headerName': 'Событие', 'flex': 2,
            'cellStyle': {
                'function': (
                    'params.value.includes("Приход") ? '
                    '{"color":"#22c55e"} : {"color":"#ef4444"}'
                )
            },
        },
        {'field': 'Кол-во',  'headerName': 'Кол-во',  'flex': 1, 'type': 'numericColumn',
         'cellStyle': {
             'function': (
                 'params.data["Событие"].includes("Приход") ? '
                 '{"color":"#22c55e","fontWeight":"600"} : {"color":"#ef4444","fontWeight":"600"}'
             )
         }},
        {'field': 'Остаток', 'headerName': 'Остаток', 'flex': 1, 'type': 'numericColumn',
         'cellStyle': {'color': '#9ca3af'}},
    ]

    ui.aggrid({
        'columnDefs':         col_defs,
        'rowData':            display_df.to_dict('records'),
        'domLayout':          'autoHeight',
        'defaultColDef':      {'resizable': True},
        'pagination':         True,
        'paginationPageSize': 20,
    }).classes('w-full ag-theme-balham-dark')


# ─────────────────────────────────────────────────────────────────────────────
#  Страница
# ─────────────────────────────────────────────────────────────────────────────

def setup_page():

    @ui.page('/velocity')
    async def velocity_page(request: Request):
        logger.info('velocity_page() handler entered')
        build_shell('/velocity')

        item_name = unquote(request.query_params.get('item', ''))
        sku       = unquote(request.query_params.get('sku', ''))

        with ui.column().classes('w-full p-4 gap-6').style(
            'background:#0d0d0d; min-height:100vh;'
        ):
            ui.label('📈 Оборачиваемость').classes('text-white text-2xl font-bold')
            ui.separator().style('background:#2a2a2a;')

            if not item_name:
                _render_empty_state()
                _render_search_form()
            else:
                _history = await ng_run.io_bound(db.load_velocity_history, item_name, sku)
                _render_velocity(item_name, sku, history=_history)
