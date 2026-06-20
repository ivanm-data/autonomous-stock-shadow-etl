"""
dead_stock_view.py — NiceGUI-версия вкладки «Неликвиды».
Полный перенос функционала из src/views/dead_stock_view.py.
"""
from nicegui import ui, run as ng_run
import sys
import os
import base64
import logging
import pandas as pd

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import db
from nice_views.shared_layout import build_shell

logger = logging.getLogger('shadow_stock.deadstock')


# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _frozen_df() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Возвращает (all_df, only_frozen_with_losses)."""
    df_all = db.load_dead_stock_analysis()
    if df_all.empty:
        return pd.DataFrame(), pd.DataFrame()

    frozen = df_all[df_all['Заморожен']].copy()
    frozen['Потери'] = frozen['Цена'] * frozen['Остаток']
    frozen = frozen.sort_values('Потери', ascending=False)
    return df_all, frozen


def _download_csv(df: pd.DataFrame) -> None:
    """Инициирует скачивание CSV через JavaScript data-URL."""
    csv_bytes = df.to_csv(index=False).encode('utf-8')
    b64       = base64.b64encode(csv_bytes).decode()
    ui.run_javascript(f"""
        var a = document.createElement('a');
        a.href = 'data:text/csv;charset=utf-8;base64,{b64}';
        a.download = 'dead_stock_report.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    """)


# ─────────────────────────────────────────────────────────────────────────────
#  Страница
# ─────────────────────────────────────────────────────────────────────────────

def setup_page():

    @ui.page('/deadstock')
    async def deadstock_page():
        logger.info('deadstock_page() handler entered')
        build_shell('/deadstock')

        with ui.column().classes('w-full p-4 gap-6').style(
            'background:#0d0d0d; min-height:100vh;'
        ):
            ui.label('❄️ Анализ замороженного капитала (Dead Stock)').classes(
                'text-white text-2xl font-bold'
            )
            ui.separator().style('background:#2a2a2a;')

            df_all, frozen = await ng_run.io_bound(_frozen_df)

            # ── Нет данных ────────────────────────────────────────────────
            if df_all.empty or frozen.empty:
                with ui.card().classes('w-full p-6').style(
                    'background:#111111; border:1px solid #2a2a2a;'
                ):
                    ui.icon('bar_chart', size='48px').style('color:#374151;')
                    ui.label(
                        '📊 Нужно больше данных. Алгоритм выявления неликвидов '
                        'заработает, когда накопится история изменений остатков.'
                    ).classes('text-gray-400 text-sm mt-2')
                return

            total_frozen = float(frozen['Потери'].sum())

            # ══════════════════════════════════════════════════════════════
            # СЕКЦИЯ 1: Метрика + Кнопка скачать + График по категориям
            # ══════════════════════════════════════════════════════════════
            with ui.row().classes('w-full gap-6 items-start flex-wrap'):

                # ── Левая колонка: Метрика + кнопка ──────────────────────
                with ui.column().classes('gap-4').style('min-width:220px;'):
                    with ui.card().classes('p-6').style(
                        'background:#171717; border-left:3px solid #38bdf8;'
                    ):
                        ui.label(
                            f"{total_frozen:,.0f} ₽".replace(',', '\u202f')
                        ).classes('text-white text-2xl font-bold')
                        ui.label('Заморожено (итого)').style(
                            'color:#9ca3af; font-size:0.82rem;'
                        )
                        ui.label(
                            f'{len(frozen)} позиций без движения'
                        ).style('color:#6b7280; font-size:0.72rem;')

                    ui.label(
                        'Товары, лежащие без движения дольше медианы '
                        'по их категории.'
                    ).style('color:#6b7280; font-size:0.75rem;')

                    ui.button(
                        '📥 Скачать отчёт (для Закупок)',
                        on_click=lambda: _download_csv(frozen),
                    ).props('color=primary no-caps').classes('w-full')

                # ── Правая колонка: График по категориям ─────────────────
                with ui.card().classes('flex-1 p-4').style(
                    'background:#111111; border:1px solid #2a2a2a; min-width:280px;'
                ):
                    ui.label('Где заморожены деньги (по категориям):').style(
                        'color:#d1d5db; font-size:0.9rem; font-weight:600; margin-bottom:8px;'
                    )

                    cat_losses = (
                        frozen.groupby('Категория')['Потери']
                        .sum()
                        .sort_values(ascending=False)
                    )

                    if not cat_losses.empty:
                        ui.echart({
                            'backgroundColor': 'transparent',
                            'tooltip': {
                                'trigger': 'axis',
                                'formatter': '{b}: {c} ₽',
                            },
                            'xAxis': {
                                'type': 'category',
                                'data': cat_losses.index.tolist(),
                                'axisLabel': {
                                    'color': '#6b7280',
                                    'rotate': 20,
                                    'fontSize': 11,
                                },
                                'axisLine': {'lineStyle': {'color': '#2a2a2a'}},
                            },
                            'yAxis': {
                                'type': 'value',
                                'axisLabel': {'color': '#6b7280'},
                                'splitLine': {'lineStyle': {'color': '#1f1f1f'}},
                            },
                            'series': [{
                                'type': 'bar',
                                'data': [round(v) for v in cat_losses.values.tolist()],
                                'itemStyle': {
                                    'color': {
                                        'type': 'linear',
                                        'x': 0, 'y': 0, 'x2': 0, 'y2': 1,
                                        'colorStops': [
                                            {'offset': 0, 'color': '#38bdf8'},
                                            {'offset': 1, 'color': '#1e40af'},
                                        ],
                                    },
                                    'borderRadius': [4, 4, 0, 0],
                                },
                            }],
                            'grid': {
                                'left': '3%', 'right': '4%',
                                'bottom': '20%', 'containLabel': True,
                            },
                        }).classes('w-full').style('height:280px;')

            ui.separator().style('background:#2a2a2a;')

            # ══════════════════════════════════════════════════════════════
            # СЕКЦИЯ 2: Детальная таблица
            # ══════════════════════════════════════════════════════════════
            ui.label('Детализация по товарам (Топ проблемных позиций):').classes(
                'text-white text-lg font-semibold'
            )

            # Готовим данные для таблицы
            table_df = frozen[[
                'Наименование', 'Артикул', 'Категория',
                'Цена', 'Остаток', 'Дней без движения',
                'Медиана категории', 'Потери',
            ]].copy()
            table_df['Медиана категории'] = table_df['Медиана категории'].round(1)
            table_df['Потери'] = table_df['Потери'].round(0).astype(int)

            max_days = int(table_df['Дней без движения'].max()) or 365

            col_defs = [
                {
                    'field': 'Наименование',
                    'headerName': 'Наименование',
                    'flex': 3,
                    'sortable': True,
                    'filter': True,
                    'resizable': True,
                },
                {
                    'field': 'Артикул',
                    'headerName': 'Артикул',
                    'flex': 1,
                    'sortable': True,
                    'resizable': True,
                },
                {
                    'field': 'Категория',
                    'headerName': 'Категория',
                    'flex': 1,
                    'sortable': True,
                    'filter': True,
                    'resizable': True,
                },
                {
                    'field': 'Цена',
                    'headerName': 'Цена, ₽',
                    'flex': 1,
                    'sortable': True,
                    'type': 'numericColumn',
                },
                {
                    'field': 'Остаток',
                    'headerName': 'Остаток',
                    'flex': 1,
                    'sortable': True,
                    'type': 'numericColumn',
                },
                {
                    'field': 'Дней без движения',
                    'headerName': 'Дней без движения',
                    'flex': 1,
                    'sortable': True,
                    'type': 'numericColumn',
                    'cellStyle': {
                        'function': (
                            f'params.value > {max_days * 0.75} ? '
                            '{"color": "#ef4444", "fontWeight": "600"} : '
                            f'params.value > {max_days * 0.4} ? '
                            '{"color": "#f59e0b"} : '
                            '{"color": "#9ca3af"}'
                        )
                    },
                },
                {
                    'field': 'Медиана категории',
                    'headerName': 'Медиана кат., дн.',
                    'flex': 1,
                    'sortable': True,
                    'type': 'numericColumn',
                },
                {
                    'field': 'Потери',
                    'headerName': 'Потери, ₽',
                    'flex': 1,
                    'sortable': True,
                    'type': 'numericColumn',
                    'cellStyle': {'color': '#ef4444', 'fontWeight': '600'},
                    'valueFormatter': {'function': 'params.value.toLocaleString("ru-RU")+" ₽"'},
                },
            ]

            ui.aggrid({
                'columnDefs':          col_defs,
                'rowData':             table_df.to_dict('records'),
                'domLayout':           'autoHeight',
                'defaultColDef': {
                    'resizable': True,
                    'sortable':  True,
                },
                'pagination':          True,
                'paginationPageSize':  25,
            }).classes('w-full ag-theme-balham-dark')
