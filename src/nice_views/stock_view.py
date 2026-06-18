"""
stock_view.py — NiceGUI-версия вкладки склада.
Полный перенос функционала из src/views/stock_view.py.
"""
from nicegui import ui
import sys
import os
import psutil
import logging
from pathlib import Path
from datetime import datetime
import pandas as pd

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import db
from nice_views.shared_layout import build_shell

logger = logging.getLogger('shadow_stock.stock')

# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _open_tasks_count() -> int:
    try:
        with db.get_connection() as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM anomaly_log WHERE status = 'Открыта'"
            ).fetchone()[0]
    except Exception:
        return 0


def _is_parser_running() -> bool:
    for proc in psutil.process_iter(['cmdline']):
        try:
            cmd = proc.info.get('cmdline') or []
            if any('parser.py' in str(a).lower() for a in cmd):
                return True
        except Exception:
            pass
    return False


def _get_parser_stats() -> pd.DataFrame:
    try:
        with db.get_connection() as conn:
            return pd.read_sql_query("""
                SELECT
                    DATE(report_timestamp)  AS parse_date,
                    COUNT(*)                AS items_count,
                    MIN(report_timestamp)   AS start_time,
                    MAX(report_timestamp)   AS end_time
                FROM stocks
                GROUP BY DATE(report_timestamp)
                ORDER BY parse_date DESC
                LIMIT 3
            """, conn)
    except Exception:
        return pd.DataFrame()


# ─────────────────────────────────────────────────────────────────────────────
#  Компонент: одна строка результата поиска
# ─────────────────────────────────────────────────────────────────────────────

def _render_stock_row(row):
    """Интерактивная строка с кнопками 📈 ⚠️ ✅."""
    name       = row['Наименование']
    is_actual  = bool(row.get('actual', True))
    qty        = int(row.get('Остаток', 0))
    price      = float(row.get('Цена', 0))
    sku        = str(row.get('Артикул', '—'))
    last_seen  = row.get('last_seen_date', '?')

    display_name = (
        f'🔘 {name} ❌ (Снят с сайта {last_seen})'
        if not is_actual else name
    )

    with ui.card().classes('w-full p-3').style(
        'background:#1a1a1a; border:1px solid #2a2a2a;'
    ):
        with ui.row().classes('w-full items-center gap-3 flex-wrap'):

            ui.label(sku).classes('font-mono text-sm').style(
                'color:#9ca3af; min-width:100px; flex-shrink:0;'
            )
            ui.label(display_name).classes(
                'flex-1 text-sm text-gray-400' if not is_actual else 'flex-1 text-sm text-white'
            )
            ui.label(f'{price:.0f} ₽').style(
                'color:#60a5fa; min-width:70px; text-align:right; flex-shrink:0;'
            )
            ui.label(f'{qty} шт.').style(
                'color:#34d399; min-width:60px; text-align:right; flex-shrink:0;'
            )

            # ── Кнопки действий ────────────────────────────────────────────
            with ui.row().classes('gap-1 flex-shrink-0'):

                # 📈 Оборачиваемость
                def _go_velocity(_n=name, _s=sku):
                    from urllib.parse import quote as _q
                    ui.navigate.to(f'/velocity?item={_q(_n)}&sku={_q(_s)}')
                ui.button('📈', on_click=_go_velocity) \
                  .props('flat size=sm').tooltip('График оборачиваемости')

                # ⚠️ Диалог расхождения
                with ui.dialog() as disc_dialog, \
                     ui.card().classes('p-6').style(
                         'min-width:420px; background:#1f1f1f; color:white;'
                     ):
                    ui.label('⚠️ Зафиксировать расхождение').classes(
                        'text-white font-bold text-lg mb-1'
                    )
                    ui.label(name).style('color:#9ca3af; font-size:0.85rem;')
                    ui.separator().style('background:#2a2a2a;')

                    fact_input    = ui.number('Реальный остаток (шт.):', value=qty, min=0)
                    is_planned_cb = ui.checkbox(
                        '⚙️ Плановая проверка (циклическая инвентаризация)', value=True
                    )
                    is_test_cb    = ui.checkbox(
                        '🧪 Тестовая запись (исключить из аналитики)', value=False
                    )
                    comment_inp   = ui.input(
                        label='Заметка (по желанию):',
                        placeholder='Напр: резерв или пересорт'
                    ).classes('w-full')

                    def _confirm(
                        _r=row, _fi=fact_input, _pl=is_planned_cb,
                        _ts=is_test_cb, _ci=comment_inp, _d=disc_dialog
                    ):
                        fact    = int(_fi.value or 0)
                        src     = 'Вручную (План)' if _pl.value else 'Вручную (Инцидент)'
                        a_type  = 'Тестовая запись' if _ts.value else 'Ручная проверка'
                        impact  = 0 if _ts.value else abs(float(_r.get('Остаток', 0)) - fact) * float(_r.get('Цена', 0))
                        db.save_anomaly_to_db({
                            'item_name':        _r['Наименование'],
                            'anomaly_type':     a_type,
                            'qty_system':       int(_r.get('Остаток', 0)),
                            'qty_physical':     fact,
                            'financial_impact': impact,
                            'source':           src,
                            'status':           'Открыта',
                            'comment':          _ci.value or '',
                        })
                        _d.close()
                        ui.notify('✅ Расхождение зафиксировано!', type='positive')

                    with ui.row().classes('gap-2 mt-4'):
                        ui.button('✅ Подтвердить', on_click=_confirm).props('color=primary')
                        ui.button('❌ Отмена', on_click=disc_dialog.close).props('flat color=negative')

                ui.button('⚠️', on_click=disc_dialog.open) \
                  .props('flat size=sm color=orange').tooltip('Зафиксировать расхождение')

                # ✅ Успешная сверка
                def _ok(_r=row):
                    db.save_anomaly_to_db({
                        'item_name':        _r['Наименование'],
                        'anomaly_type':     'Успешная сверка',
                        'qty_system':       int(_r.get('Остаток', 0)),
                        'qty_physical':     int(_r.get('Остаток', 0)),
                        'financial_impact': 0,
                        'source':           'Вручную (План)',
                        'status':           'Закрыта',
                        'comment':          'Сверено с планшета. Всё ок.',
                    })
                    ui.notify('✅ Сверка подтверждена! Экономия зафиксирована.', type='positive')

                ui.button('✅', on_click=_ok) \
                  .props('flat size=sm color=positive').tooltip('Остаток сошёлся')


# ─────────────────────────────────────────────────────────────────────────────
#  Компонент: Data Health Monitor
# ─────────────────────────────────────────────────────────────────────────────

def _render_data_health(df_inv: pd.DataFrame):
    ui.label('🤖 Мониторинг парсера (Data Health)').classes(
        'text-white text-xl font-bold mt-2'
    )

    df_stats = _get_parser_stats()

    if df_stats.empty:
        with ui.card().classes('w-full p-4').style(
            'background:#1f1f00; border:1px solid #f59e0b;'
        ):
            ui.label('⚠️ В базе данных ещё нет записей.').classes('text-amber-400')
        return

    latest = df_stats.iloc[0]

    # Дельта
    delta_text = 'Первый запуск'
    if len(df_stats) > 1:
        dv         = int(latest['items_count'] - df_stats.iloc[1]['items_count'])
        delta_text = f'{dv:+} шт.'

    # Длительность парсинга
    fmt = '%Y-%m-%d %H:%M:%S'
    try:
        secs     = (
            datetime.strptime(latest['end_time'], fmt) -
            datetime.strptime(latest['start_time'], fmt)
        ).total_seconds()
        mins     = round(secs / 60)
        dur_text = f'{mins} мин.' if mins > 0 else f'{int(secs)} сек.'
    except Exception:
        dur_text = 'н/д'

    is_running = _is_parser_running()

    # ── Метрики ──────────────────────────────────────────────────────────
    with ui.row().classes('gap-4 flex-wrap'):
        with ui.card().classes('p-4').style(
            'background:#171717; border-left:3px solid #60a5fa;'
        ):
            ui.label(f"{latest['items_count']} шт.").classes('text-white text-2xl font-bold')
            ui.label('Собрано товаров').style('color:#9ca3af; font-size:0.8rem;')
            ui.label(delta_text).style('color:#34d399; font-size:0.75rem;')

        with ui.card().classes('p-4').style(
            'background:#171717; border-left:3px solid #a78bfa;'
        ):
            ui.label(dur_text).classes('text-white text-2xl font-bold')
            ui.label('Длительность парсинга').style('color:#9ca3af; font-size:0.8rem;')

        with ui.card().classes('p-4').style(
            'background:#171717; border-left:3px solid #34d399;'
        ):
            if is_running:
                ui.label('🔄 В процессе…').classes('text-amber-400 font-bold text-xl')
            else:
                ui.label('✅ Завершён').classes('text-green-400 font-bold text-xl')
            ui.label('Статус парсера').style('color:#9ca3af; font-size:0.8rem;')
            ui.button(
                '🔄 Обновить',
                on_click=lambda: ui.navigate.to('/stock')
            ).props('flat size=sm').classes('text-gray-400')

    # ── Таблица динамики ─────────────────────────────────────────────────
    ui.label(f'📊 Динамика за последние {len(df_stats)} дн.').classes(
        'text-white font-semibold mt-4'
    )

    disp = df_stats.copy()
    disp['Время начала'] = disp['start_time'].str[11:19]
    disp['Время конца']  = disp['end_time'].str[11:19]
    disp = disp[['parse_date', 'items_count', 'Время начала', 'Время конца']]
    disp.columns = ['Дата', 'Всего SKU', 'Время начала', 'Время конца']

    ui.aggrid({
        'columnDefs': [
            {'field': c, 'headerName': c, 'sortable': True}
            for c in disp.columns
        ],
        'rowData':    disp.to_dict('records'),
        'domLayout':  'autoHeight',
    }).classes('w-full ag-theme-balham-dark')

    # ── Исчезнувшие товары ────────────────────────────────────────────────
    if len(df_stats) <= 1 or df_inv.empty:
        return

    # Пока парсер работает — не показываем «снятые с сайта»:
    # товары, до которых он ещё не дошёл, имеют вчерашнюю дату и
    # ошибочно попадают в список (может быть тысячи позиций → зависание).
    if is_running:
        with ui.card().classes('w-full p-3 mt-2').style(
            'background:#1c1917; border:1px solid #a16207;'
        ):
            ui.label(
                '⏳ Парсер работает — список «Снятых с сайта» временно скрыт. '
                'Проверка будет доступна после завершения сбора данных.'
            ).classes('text-amber-300 text-sm')
        return

    yesterday_date = df_stats.iloc[1]['parse_date']
    lost_items     = df_inv[
        (df_inv['last_seen_date'] == yesterday_date) & (~df_inv['actual'])
    ].copy()

    if lost_items.empty:
        with ui.card().classes('w-full p-3 mt-2').style(
            'background:#052e16; border:1px solid #22c55e;'
        ):
            ui.label(
                '✅ С момента прошлого парсинга ни один товар не пропал с сайта, '
                'либо все пропажи уже проверены.'
            ).classes('text-green-400 text-sm')
        return

    dismissed_lost: list[str] = []

    with ui.expansion(
        f'📉 Сняты с сайта (Требует проверки: {len(lost_items)} шт.)',
        value=True
    ).classes('w-full mt-2').style(
        'background:#1a1200; border:1px solid #f59e0b; border-radius:8px;'
    ):
        ui.label(
            '👀 Слепая зона: эти товары исчезли с сайта. '
            'Подтвердите физическое наличие на полке.'
        ).classes('text-amber-300 text-sm mb-3')

        @ui.refreshable
        def render_lost():
            shown = lost_items[~lost_items['Наименование'].isin(dismissed_lost)]
            if shown.empty:
                ui.label('✅ Все позиции обработаны.').classes('text-green-400 text-sm')
                return

            for _, lrow in shown.iterrows():
                with ui.row().classes('w-full items-center gap-3 py-2 flex-wrap'):
                    ui.label(f"🏷️ {lrow.get('Артикул', '—')}").classes(
                        'font-mono text-sm text-gray-400'
                    ).style('min-width:100px; flex-shrink:0;')
                    ui.label(lrow['Наименование']).classes('flex-1 text-sm text-white')
                    ui.label(f"Было: {lrow.get('Остаток', 0)} шт.").classes(
                        'text-sm text-amber-300 flex-shrink-0'
                    )

                    def _sold(_r=lrow):
                        dismissed_lost.append(_r['Наименование'])
                        ui.notify(f"🛒 Продан: {_r['Наименование']}", type='info')
                        render_lost.refresh()

                    def _bug(_r=lrow):
                        db.save_anomaly_to_db({
                            'item_name':        _r['Наименование'],
                            'anomaly_type':     'Скрыт с витрины (Баг)',
                            'qty_system':       0,
                            'qty_physical':     int(_r.get('Остаток', 0)),
                            'financial_impact': float(_r.get('Остаток', 0)) * float(_r.get('Цена', 0)),
                            'source':           'Автоматически',
                            'status':           'Закрыта',
                            'comment':          'Товар физически на складе, но исчез с сайта (Упущенная выручка)',
                        })
                        dismissed_lost.append(_r['Наименование'])
                        ui.notify('✅ Инцидент "Упущенная выручка" записан в KPI!', type='positive')
                        render_lost.refresh()

                    with ui.row().classes('gap-2 flex-shrink-0'):
                        ui.button('🛒 Продан', on_click=_sold).props('outline color=positive size=sm')
                        ui.button('🚨 Баг 1С',  on_click=_bug).props('color=negative size=sm')

                ui.separator().style('background:#2a2a2a;')

        render_lost()


# ─────────────────────────────────────────────────────────────────────────────
#  Страница склада
# ─────────────────────────────────────────────────────────────────────────────

def setup_page():

    @ui.page('/stock')
    def stock_page():
        logger.info('stock_page() handler entered')
        build_shell('/stock')

        df_inv  = db.load_inventory()
        df_anom = db.load_anomalies()

        with ui.column().classes('w-full p-4 gap-4').style(
            'background:#0d0d0d; min-height:100vh;'
        ):

            # ── Умные баннеры ─────────────────────────────────────────────
            active_anom = len(df_anom) if not df_anom.empty else 0
            open_tasks  = _open_tasks_count()

            if active_anom > 0:
                with ui.card().classes('w-full cursor-pointer').style(
                    'background:#450a0a; border:1px solid #ef4444;'
                ).on('click', lambda: ui.navigate.to('/anomalies')):
                    with ui.row().classes('items-center gap-3 p-2'):
                        ui.icon('warning', size='24px').style('color:#ef4444;')
                        ui.label(
                            f'🚨 НОВЫЕ СКАЧКИ ОСТАТКОВ ({active_anom})! '
                            f'Нажмите для распределения'
                        ).classes('text-white font-bold')

            if open_tasks > 0:
                with ui.card().classes('w-full cursor-pointer').style(
                    'background:#422006; border:1px solid #f97316;'
                ).on('click', lambda: ui.notify('🚧 Задачи — в разработке', type='info')):
                    with ui.row().classes('items-center gap-3 p-2'):
                        ui.icon('local_fire_department', size='24px').style('color:#f97316;')
                        ui.label(
                            f'🔥 НЕЗАКРЫТЫЕ ЗАДАЧИ ({open_tasks})! '
                            f'Нажмите для проверки на полке'
                        ).classes('text-white font-bold')

            # ── AI-флаг ───────────────────────────────────────────────────
            pending_flag = (
                Path(__file__).resolve().parent.parent.parent / 'logs' / 'ai_pending.flag'
            )
            if pending_flag.exists():
                with ui.card().classes('w-full p-3').style(
                    'background:#1e1b4b; border:1px solid #818cf8;'
                ):
                    ui.label(
                        '⚠️ ИИ ожидает запуска: есть свежие данные без анализа. '
                        'Перейдите на вкладку A/B Тест.'
                    ).classes('text-indigo-200 text-sm')

            ui.separator().style('background:#2a2a2a;')

            # ── Проверка БД ───────────────────────────────────────────────
            if df_inv.empty:
                with ui.card().classes('w-full p-4').style(
                    'background:#171717; border:1px solid #ef4444;'
                ):
                    ui.label('⚠️ База данных пуста или файл не найден.').classes(
                        'text-red-400 text-lg'
                    )
                return

            # ── Метрики ───────────────────────────────────────────────────
            latest_date   = df_inv['last_seen_date'].max() if 'last_seen_date' in df_inv.columns else '—'
            actual_count  = int(df_inv['actual'].sum()) if 'actual' in df_inv.columns else len(df_inv)
            total_count   = len(df_inv)
            removed_count = total_count - actual_count
            parser_now    = _is_parser_running()

            if parser_now:
                with ui.card().classes('w-full p-3').style(
                    'background:#1c1917; border:1px solid #a16207;'
                ):
                    ui.label(
                        '🔄 Парсер сейчас работает. Данные обновляются в реальном времени. '
                        'Метрика «Снято с сайта» и список исчезнувших товаров будут '
                        'доступны после завершения сбора.'
                    ).classes('text-amber-300 text-sm')

            with ui.row().classes('gap-4 flex-wrap'):
                def _stat(label, value, color):
                    with ui.card().classes('p-4').style(
                        f'background:#171717; border-left:3px solid {color};'
                    ):
                        ui.label(str(value)).classes('text-white text-2xl font-bold')
                        ui.label(label).style('color:#9ca3af; font-size:0.8rem;')

                _stat('Всего позиций',   total_count,                        '#60a5fa')
                _stat('Активных',        actual_count,                       '#34d399')
                _stat('Снято с сайта',   '…' if parser_now else removed_count, '#f87171')
                _stat('Дата обновления', latest_date,                        '#a78bfa')


            ui.separator().style('background:#2a2a2a;')

            # ── Основная таблица ──────────────────────────────────────────
            ui.label('📦 Актуальные остатки').classes('text-white text-xl font-bold')

            exclude_cols = {'_search_index', 'actual', 'ID'}
            col_defs = []
            for col in df_inv.columns:
                if col in exclude_cols:
                    continue
                cdef = {
                    'field': col, 'headerName': col,
                    'sortable': True, 'filter': True,
                    'resizable': True, 'floatingFilter': True,
                }
                if col == 'Артикул':      cdef['width'] = 130
                elif col == 'Наименование': cdef['flex'] = 3
                elif col in ('Цена', 'Остаток'): cdef['width'] = 100
                col_defs.append(cdef)

            rows = df_inv.drop(
                columns=[c for c in exclude_cols if c in df_inv.columns]
            ).to_dict('records')

            ui.aggrid({
                'columnDefs':          col_defs,
                'rowData':             rows,
                'rowSelection':        'single',
                'pagination':          True,
                'paginationPageSize':  100,
                'defaultColDef':       {'minWidth': 80, 'flex': 1},
                'domLayout':           'autoHeight',
            }).classes('w-full ag-theme-balham-dark')

            ui.separator().style('background:#2a2a2a;')

            # ── Быстрый поиск ─────────────────────────────────────────────
            ui.label('🔍 Быстрый поиск').classes('text-white text-xl font-bold')

            search_val = ['']

            @ui.refreshable
            def render_search_results():
                query = search_val[0].strip()
                if not query:
                    ui.label('👆 Введите артикул или название для поиска.').style(
                        'color:#9ca3af;'
                    )
                    return

                words = query.lower().replace('ё', 'е').split()
                mask  = pd.Series(True, index=df_inv.index)
                for w in words:
                    if '_search_index' in df_inv.columns:
                        mask &= df_inv['_search_index'].str.contains(w, regex=False)
                f_df  = df_inv[mask].copy()
                count = len(f_df)

                if count == 0:
                    ui.label('Ничего не найдено.').classes('text-gray-400 italic')
                    return

                ui.label(f'Найдено: {count}').style('color:#9ca3af; font-size:0.85rem;')

                if count > 50:
                    # Много результатов — показываем AgGrid
                    sub_rows = f_df.drop(
                        columns=[c for c in exclude_cols if c in f_df.columns]
                    ).to_dict('records')
                    ui.aggrid({
                        'columnDefs':   col_defs,
                        'rowData':      sub_rows,
                        'pagination':   True,
                        'paginationPageSize': 50,
                        'defaultColDef': {'minWidth': 80, 'flex': 1},
                        'domLayout':    'autoHeight',
                    }).classes('w-full ag-theme-balham-dark')
                    return

                # ≤50 результатов — интерактивные строки с кнопками
                with ui.column().classes('w-full gap-2'):
                    for _, srow in f_df.iterrows():
                        _render_stock_row(srow)

            def _on_search(e):
                search_val[0] = e.value
                render_search_results.refresh()

            ui.input(placeholder='🔍 Артикул или название...').classes('w-full').style(
                'color:white;'
            ).on_value_change(_on_search)

            render_search_results()

            ui.separator().style('background:#2a2a2a;')

            # ── Data Health ───────────────────────────────────────────────
            _render_data_health(df_inv)
