"""
anomalies_view.py — NiceGUI-версия вкладки аномалий.
"""
import logging
logger = logging.getLogger('shadow_stock.anomalies')

from nicegui import ui, run as ng_run
import pandas as pd
import re
import difflib
import traceback
import db
from nice_views.shared_layout import build_shell


# ─────────────────────────────────────────────────────────────────────────────
#  Утилиты
# ─────────────────────────────────────────────────────────────────────────────

def find_best_invoice_match(anomaly_name: str, expected_df: pd.DataFrame):
    if expected_df.empty:
        return None, 0.0
    best_row, max_ratio = None, 0.0
    for _, exp_row in expected_df.iterrows():
        ratio = difflib.SequenceMatcher(
            None,
            str(anomaly_name).lower(),
            str(exp_row['item_name']).lower()
        ).ratio()
        if ratio > max_ratio:
            max_ratio = ratio
            best_row = exp_row
    return best_row, max_ratio


def _get_status_tag(row):
    qty_old    = row.get('Было', 0)
    hist_count = row.get('history_count', 0)
    old_alias  = row.get('old_name_alias', None)
    old_sku    = row.get('old_sku_alias', None)

    if qty_old > 0:
        return '📦 ДОВОЗ',            'Обычное пополнение активного товара.',          'gray'
    elif pd.notna(old_alias) and old_alias:
        return '📝 СМЕНИЛОСЬ ИМЯ',    f'Раньше назывался: {old_alias}.',               'orange'
    elif pd.notna(old_sku) and old_sku:
        return '📝 СМЕНИЛСЯ АРТИКУЛ', f'Старый артикул: {old_sku}.',                   'orange'
    elif hist_count > 0:
        return '🔄 ВОЗВРАТ',          'Товар уже был в базе. Жми «Плановый приход».',  'blue'
    else:
        return '✨ НОВИНКА',           'Абсолютно новый товар.',                        'green'


_TAG_COLORS = {
    'gray':   'text-gray-500',
    'orange': 'text-orange-500',
    'blue':   'text-blue-500',
    'green':  'text-green-600',
}


# ─────────────────────────────────────────────────────────────────────────────
#  Инициализация страницы
# ─────────────────────────────────────────────────────────────────────────────

def setup_page():
    logger.info('anomalies_view.setup_page() called')

    @ui.page('/anomalies')
    async def anomalies_page():
        logger.info('anomalies_page() handler entered')

        dismissed: list[str] = []

        # ── Шапка + сайдбар (общая тёмная разметка) ──────────────────────────
        build_shell('/anomalies')

        # ── refreshable внутри страницы — per-client ─────────────────────────
        @ui.refreshable
        async def render_anomalies():
            logger.info('render_anomalies() called')
            try:
                # A1: выносим всю загрузку данных вне event loop
                expected_df, df_anomalies, df_inv = await ng_run.io_bound(
                    _load_anomaly_data
                )
                _render_content(
                    expected_df, df_anomalies, df_inv,
                    dismissed, render_anomalies,
                )
                logger.info('render_anomalies() completed OK')
            except Exception as e:
                logger.exception('EXCEPTION inside render_anomalies')
                # Показываем traceback в браузере вместо разрыва соединения
                import traceback as tb_mod
                with ui.card().classes('w-full p-4 bg-red-50 border border-red-300'):
                    ui.label('💥 Ошибка при загрузке страницы').classes('text-red-700 font-bold text-lg mb-2')
                    ui.label(str(e)).classes('text-red-600 mb-2')
                    ui.label(tb_mod.format_exc()).classes('text-xs font-mono whitespace-pre bg-red-100 p-2 w-full')
                    ui.button('🔄 Попробовать снова', on_click=render_anomalies.refresh).props('color=primary')

        logger.info('anomalies_page: calling render_anomalies()')
        with ui.column().classes('w-full max-w-5xl mx-auto p-4'):
            render_anomalies()
        logger.info('anomalies_page: setup complete')


# ─────────────────────────────────────────────────────────────────────────────
#  Основной контент (вызывается из render_anomalies через try/except)
# ─────────────────────────────────────────────────────────────────────────────

def _load_anomaly_data() -> tuple:
    """A1: загружает все данные. Вызывается через run.io_bound, не создаёт UI-элементов."""
    with db.get_connection() as conn:
        try:
            expected_df = pd.read_sql_query(
                "SELECT * FROM expected_deliveries WHERE status = 'Ожидает'", conn
            )
        except Exception:
            expected_df = pd.DataFrame()
    df_anomalies = db.load_anomalies()
    df_inv       = db.load_inventory()
    return expected_df, df_anomalies, df_inv


def _render_content(
    expected_df: pd.DataFrame,
    df_anomalies: pd.DataFrame,
    df_inv: pd.DataFrame,
    dismissed: list,
    refresh_fn,
):
    active_anom = (
        df_anomalies[~df_anomalies['Наименование'].isin(dismissed)]
        if not df_anomalies.empty else pd.DataFrame()
    )

    # 2. Строгий авто-матчинг 100 %
    if not active_anom.empty and not expected_df.empty:
        arrivals     = active_anom[active_anom['Дельта'] > 0]
        auto_matched = False
        with db.get_connection() as conn:
            for _, anom_row in arrivals.iterrows():
                match = expected_df[
                    (
                        (expected_df['item_name'] == anom_row['Наименование']) |
                        (expected_df['sku']       == anom_row['Артикул'])
                    ) &
                    (expected_df['qty_expected'] == anom_row['Дельта'])
                ]
                if not match.empty:
                    match_id = int(match.iloc[0]['id'])
                    db.save_anomaly_to_db({
                        'item_name':        anom_row['Наименование'],
                        'anomaly_type':     '📦 Плановый приход',
                        'qty_system':       anom_row['Стало'],
                        'qty_physical':     anom_row['Было'],
                        'financial_impact': 0,
                        'source':           'Автоматически (Нейро-приемка)',
                        'status':           'Закрыта',
                        'comment':          f'Авто-матчинг с накладной #{match_id}',
                    })
                    conn.execute(
                        "UPDATE expected_deliveries SET status = 'Принято' WHERE id = ?",
                        (match_id,)
                    )
                    conn.commit()
                    if anom_row['Наименование'] not in dismissed:
                        dismissed.append(anom_row['Наименование'])
                    ui.notify(f"🤖 Авто-приемка: {anom_row['Наименование']}", type='positive')
                    auto_matched = True

        if auto_matched:
            refresh_fn.refresh()
            return

    # 3. Пересчитываем после авто-матчинга
    active_anom = (
        df_anomalies[~df_anomalies['Наименование'].isin(dismissed)]
        if not df_anomalies.empty else pd.DataFrame()
    )

    # 4. Нет аномалий — успех
    if active_anom.empty:
        with ui.card().classes('w-full p-6 bg-green-50 items-center gap-3'):
            ui.icon('check_circle', size='48px').classes('text-green-500')
            ui.label('Аномалий нет. 🎉').classes('text-xl font-semibold text-green-700')
        return

    # 5. Пагинация — рисуем не более PAGE_SIZE карточек за раз
    PAGE_SIZE = 50
    total = len(active_anom)
    page_anom = active_anom.head(PAGE_SIZE)

    if total > PAGE_SIZE:
        with ui.card().classes('w-full p-3 bg-amber-50 border border-amber-200 mb-2'):
            ui.label(
                f'⚠️ Показаны первые {PAGE_SIZE} из {total} аномалий. '
                f'Обработайте их — остальные появятся автоматически.'
            ).classes('text-amber-800 text-sm')
    else:
        ui.label(f'Найдено аномалий: {total}').classes('text-sm text-gray-500 mb-2')

    # 6. Рисуем карточки
    for idx, row in page_anom.iterrows():
        _render_card(idx, row, df_inv, df_anomalies, expected_df, dismissed, refresh_fn)


# ─────────────────────────────────────────────────────────────────────────────
#  Карточка одной аномалии
# ─────────────────────────────────────────────────────────────────────────────

def _render_card(idx, row, df_inv, df_anomalies, expected_df, dismissed: list, refresh_fn):
    status_tag, help_text, color = _get_status_tag(row)
    color_cls = _TAG_COLORS.get(color, 'text-gray-500')

    with ui.card().classes('w-full p-4 mb-4 shadow-md'):

        # ── Заголовок ─────────────────────────────────────────────────────────
        with ui.row().classes('w-full items-start gap-4 mb-2 flex-wrap'):
            with ui.column().classes('min-w-[80px]'):
                ui.label('Артикул').classes('text-xs text-gray-400 uppercase')
                ui.label(str(row.get('Артикул', '—'))).classes('font-mono text-sm font-semibold')

            with ui.column().classes('flex-1'):
                ui.label(str(row['Наименование'])).classes('font-semibold text-base')
                ui.label(f'{status_tag}  {help_text}').classes(f'text-xs {color_cls}')

            with ui.row().classes('gap-6 items-center ml-auto'):
                for lbl, val in [('Было', row['Было']), ('Стало', row['Стало'])]:
                    with ui.column().classes('items-center'):
                        ui.label(lbl).classes('text-xs text-gray-400 uppercase')
                        ui.label(str(val)).classes('text-sm font-semibold')
                with ui.column().classes('items-center'):
                    ui.label('Δ').classes('text-xs text-gray-400 uppercase')
                    dv  = row['Дельта']
                    cls = 'text-green-600 font-bold' if dv > 0 else 'text-red-600 font-bold'
                    ui.label(f"{'+'if dv>0 else ''}{dv}").classes(f'text-sm {cls}')

        ui.separator()

        # ── Fuzzy Match ───────────────────────────────────────────────────────
        best_match, ratio = find_best_invoice_match(row['Наименование'], expected_df)
        if best_match is not None and ratio > 0.4:
            bg = 'bg-green-50 border border-green-200' if ratio >= 0.7 else 'bg-blue-50 border border-blue-200'
            with ui.card().classes(f'w-full p-3 my-2 {bg}'):
                ui.label(
                    f"💡 Найдено в накладной ({ratio:.0%}): "
                    f"{best_match['item_name']} ({best_match['qty_expected']} шт.)"
                ).classes('text-sm mb-1')

                def _fuzzy_link(r=row, bm=best_match):
                    db.save_anomaly_to_db({
                        'item_name':        r['Наименование'],
                        'anomaly_type':     '📦 Плановый приход',
                        'qty_system':       r['Стало'],
                        'qty_physical':     r['Было'],
                        'financial_impact': 0,
                        'source':           'Вручную (Умная склейка накладной)',
                        'status':           'Закрыта',
                        'comment':          f"Привязка: {bm['item_name']} (id #{bm['id']})",
                    })
                    with db.get_connection() as conn:
                        conn.execute(
                            "UPDATE expected_deliveries SET status = 'Принято' WHERE id = ?",
                            (int(bm['id']),)
                        )
                        conn.commit()
                    if r['Наименование'] not in dismissed:
                        dismissed.append(r['Наименование'])
                    ui.notify('🎉 Аномалия закрыта!', type='positive')
                    refresh_fn.refresh()

                ui.button('🔗 Принять по накладной (Склеить)', on_click=_fuzzy_link).props('color=primary')

        # ── Сетка кнопок 3×3 ──────────────────────────────────────────────────
        button_grid = [
            ['Утеря',              'Тихая отмена',       'Системная ошибка'],
            ['Пересорт (Склад)',   'Пересорт (1С)',       'Излишек'],
            ['📦 Плановый приход', '⏳ Догруз с сайта',   '🔄 Обновление карточки'],
        ]
        NO_IMPACT = {'Системная ошибка', '📦 Плановый приход', '⏳ Догруз с сайта'}

        link_panel_ref: dict = {}

        def _make_handler(label, r=row, di=df_inv, lpr=link_panel_ref):
            def handler():
                if label == '🔄 Обновление карточки':
                    panel = lpr.get('panel')
                    if panel:
                        panel.set_visibility(True)
                    return
                price = 0
                if not di.empty:
                    vals = di[di['Наименование'] == r['Наименование']]['Цена'].values
                    if len(vals):
                        try:
                            price = float(vals[0])
                        except Exception:
                            pass
                auto_comment = ''
                if label == '📦 Плановый приход':
                    auto_comment = 'Штатное поступление товара'
                elif label == '⏳ Догруз с сайта':
                    auto_comment = 'Запоздалая выгрузка остатков витрины'
                db.save_anomaly_to_db({
                    'item_name':        r['Наименование'],
                    'anomaly_type':     label,
                    'qty_system':       r['Стало'],
                    'qty_physical':     r['Было'],
                    'financial_impact': abs(r['Дельта'] * price) if label not in NO_IMPACT else 0,
                    'source':           'Автоматически',
                    'status':           'Закрыта' if label in NO_IMPACT else 'Открыта',
                    'comment':          auto_comment,
                })
                if r['Наименование'] not in dismissed:
                    dismissed.append(r['Наименование'])
                ui.notify(f'Зафиксировано: {label}', type='positive')
                refresh_fn.refresh()
            return handler

        with ui.column().classes('w-full gap-2 mt-3'):
            for btn_row in button_grid:
                with ui.row().classes('w-full gap-2'):
                    for label in btn_row:
                        ui.button(label, on_click=_make_handler(label)).classes('flex-1').props('outline')

        # ── Панель склейки ─────────────────────────────────────────────────────
        with ui.card().classes('w-full p-4 bg-gray-50 mt-3') as link_panel:
            link_panel.set_visibility(False)
            link_panel_ref['panel'] = link_panel

            ui.label('🔗 Привязка к старой карточке').classes('font-semibold mb-2')

            with ui.row().classes('gap-2 mb-3'):
                def _skip(r=row):
                    db.save_anomaly_to_db({
                        'item_name':        r['Наименование'],
                        'anomaly_type':     '🔄 Обновление карточки',
                        'qty_system':       r['Стало'],
                        'qty_physical':     r['Было'],
                        'financial_impact': 0,
                        'source':           'Автоматически',
                        'status':           'Закрыта',
                        'comment':          'Изменилось название на сайте',
                    })
                    if r['Наименование'] not in dismissed:
                        dismissed.append(r['Наименование'])
                    ui.notify('Карточка обновлена без склейки', type='positive')
                    refresh_fn.refresh()

                ui.button('⏭️ Просто обновить (БЕЗ склейки)', on_click=_skip).props('color=primary outline')
                ui.button('❌ Отмена', on_click=lambda lp=link_panel: lp.set_visibility(False)).props('flat color=negative')

            search_input = ui.input(placeholder='🔍 Артикул или название...').classes('w-full')
            results_col  = ui.column().classes('w-full')

            def _do_search(value: str, r=row, da=df_anomalies, di=df_inv):
                results_col.clear()
                with results_col:
                    query = (value or '').strip()

                    if not query:
                        today_lost = (
                            da[(da['Дельта'] < 0) & (~da['Наименование'].isin(dismissed))]['Наименование'].tolist()
                            if not da.empty else []
                        )
                        if not di.empty:
                            mask = di['Наименование'].isin(today_lost) | ~di['actual']
                            matched_df = di[mask].sort_values('actual').head(10).copy()
                        else:
                            matched_df = pd.DataFrame()
                        ui.label('Показаны недавно пропавшие товары.').classes('text-xs text-gray-500 mb-1')
                    else:
                        clean = re.sub(r'\(снят с сайта.*?\)', '', query, flags=re.IGNORECASE)
                        clean = clean.replace('🔘', '').replace('❌', '').strip()
                        words = clean.lower().replace('ё', 'е').split()
                        if words and not di.empty and '_search_index' in di.columns:
                            mask = pd.Series(True, index=di.index)
                            for w in words:
                                mask &= di['_search_index'].str.contains(w, regex=False)
                            matched_df = di[mask].sort_values('actual').head(30).copy()
                            ui.label(f'🔍 Найдено: {int(mask.sum())}.').classes('text-xs text-gray-500 mb-1')
                        else:
                            matched_df = pd.DataFrame()

                    if matched_df.empty:
                        ui.label('Ничего не найдено.').classes('text-gray-400 italic')
                        return

                    with ui.row().classes('w-full text-xs text-gray-400 uppercase font-semibold px-1 mb-1'):
                        ui.label('Артикул').classes('w-24')
                        ui.label('Наименование').classes('flex-1')
                        ui.label('Статус').classes('w-32')
                        ui.label('').classes('w-28')
                    ui.separator()

                    for _, m_row in matched_df.iterrows():
                        with ui.row().classes('w-full items-center gap-2 py-1'):
                            ui.label(str(m_row.get('Артикул', '—'))).classes('font-mono text-xs w-24 truncate')
                            name_txt = str(m_row['Наименование'])
                            if not m_row.get('actual', True):
                                ui.label(f'🔘 {name_txt}').classes('flex-1 text-sm text-gray-500 truncate')
                                ui.label(f"❌ Снят ({m_row.get('last_seen_date','?')})").classes('text-xs text-red-400 w-32')
                            else:
                                ui.label(name_txt).classes('flex-1 text-sm truncate')
                                ui.label('✅ Активен').classes('text-xs text-green-600 w-32')

                            def _do_link(new_r=r, old_r=m_row):
                                old_name = old_r['Наименование']
                                with db.get_connection() as conn:
                                    conn.execute(
                                        'INSERT OR IGNORE INTO item_aliases (new_name, old_name) VALUES (?, ?)',
                                        (new_r['Наименование'], old_name)
                                    )
                                    conn.execute("""
                                        INSERT INTO anomaly_log
                                            (detected_at, item_name, anomaly_type, qty_system,
                                             qty_physical, financial_impact, source, status, comment)
                                        VALUES (datetime('now','localtime'), ?,
                                                '🔄 Обновление карточки', 0, 0, 0,
                                                'Автоматически', 'Закрыта', ?)
                                    """, (old_name, f"🔗 Склеено. Новое: {new_r['Наименование']}"))
                                    conn.commit()
                                if old_name not in dismissed:
                                    dismissed.append(old_name)
                                db.save_anomaly_to_db({
                                    'item_name':        new_r['Наименование'],
                                    'anomaly_type':     '🔄 Обновление карточки',
                                    'qty_system':       new_r['Стало'],
                                    'qty_physical':     new_r['Было'],
                                    'financial_impact': 0,
                                    'source':           'Автоматически',
                                    'status':           'Закрыта',
                                    'comment':          f'Склейка: {old_name}',
                                })
                                if new_r['Наименование'] not in dismissed:
                                    dismissed.append(new_r['Наименование'])
                                ui.notify('🔗 Карточки склеены!', type='positive')
                                refresh_fn.refresh()

                            ui.button('🔗 Склеить', on_click=_do_link).props('color=primary size=sm').classes('w-28')
                        ui.separator()

            search_input.on_value_change(lambda e: _do_search(e.value))
            # НЕ вызываем _do_search('') при рендере — только по запросу пользователя
            # чтобы не создавать тысячи UI-элементов при открытии страницы

        ui.separator().classes('mt-2')
