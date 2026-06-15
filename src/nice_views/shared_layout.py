"""
shared_layout.py — Общая тёмная шапка и боковая навигация для всех страниц.
Вызывай build_shell(current_route) в начале каждого @ui.page хендлера.
"""
import logging
from nicegui import ui
import db

logger = logging.getLogger('shadow_stock.layout')

DARK_CSS = """
    body,
    .q-page-container,
    .q-page,
    .nicegui-content {
        background-color: #0d0d0d !important;
        color: #f4f4f5 !important;
    }
    .q-drawer .q-drawer__content {
        background-color: #111111 !important;
    }
    /* Секционные заголовки */
    .nav-section {
        color: #6b7280;
        font-size: 0.65rem;
        font-weight: 700;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        padding: 12px 16px 4px 16px;
        display: block;
    }
    /* Кнопки навигации */
    .nav-btn .q-btn__content {
        justify-content: flex-start !important;
        font-size: 0.85rem;
    }
    .nav-btn {
        color: #d1d5db !important;
        border-radius: 6px !important;
        margin: 1px 6px !important;
        transition: background-color 0.15s !important;
    }
    .nav-btn:hover {
        background-color: #1f1f1f !important;
        color: #ffffff !important;
    }
    .nav-btn-active {
        background-color: #1e3a5f !important;
        color: #93c5fd !important;
    }
    /* Карточки на главной (тёмные) */
    .dark-card {
        background-color: #171717 !important;
        border: 1px solid #2a2a2a;
        color: #f4f4f5 !important;
    }
    .dark-card:hover {
        background-color: #1f1f1f !important;
        border-color: #3b82f6;
        box-shadow: 0 0 0 1px #3b82f6;
    }
"""


def build_shell(current_route: str = '/'):
    """
    Строит общую тёмную шапку + полный сайдбар.
    Возвращает (drawer, header).
    """
    ui.add_css(DARK_CSS)

    # Статистика БД для низа сайдбара
    try:
        stats = db.get_db_stats()
    except Exception:
        stats = None

    # ── САЙДБАР ──────────────────────────────────────────────────────────
    with ui.left_drawer(elevated=True, value=True).style(
        'background-color: #111111;'
    ) as drawer:

        # Бренд
        with ui.row().classes('items-center px-4 py-4 gap-2'):
            ui.icon('diamond', size='22px').style('color: #60a5fa;')
            with ui.column().classes('gap-0'):
                ui.label('Autonomous Stock').classes('text-white font-bold leading-tight').style('font-size:0.85rem;')
                ui.label('Shadow ETL').style('color: #9ca3af; font-size: 0.72rem;')

        ui.separator().style('background-color: #2a2a2a; margin: 0;')

        # ── Секция: ОПЕРАЦИИ ─────────────────────────────────────────────
        ui.html('<span class="nav-section">🛠&nbsp; Операции</span>')

        def _nav(label: str, route: str | None, wip: bool = False):
            is_active = (route is not None and route == current_route)

            def on_click(r=route, w=wip):
                if w or r is None:
                    ui.notify('🚧 В разработке…', type='info')
                else:
                    ui.navigate.to(r)

            extra = 'nav-btn-active' if is_active else ''
            ui.button(label, on_click=on_click) \
              .props('flat align=left no-caps') \
              .classes(f'nav-btn w-full {extra}')

        _nav('📦  Склад',    '/stock')
        _nav('⚠️  Аномалии', '/anomalies')
        _nav('🔥  Задачи',   '/tasks')
        _nav('📥  Приёмка',  '/receiving')

        ui.separator().style('background-color: #2a2a2a; margin: 4px 0;')

        # ── Секция: АНАЛИТИКА И KPI ──────────────────────────────────────
        ui.html('<span class="nav-section">📊&nbsp; Аналитика и KPI</span>')

        _nav('🎯  Эффективность',           '/efficiency')
        _nav('❄️  Неликвиды',               '/deadstock')
        _nav('📈  Оборачиваемость',          '/velocity',   wip=True)
        _nav('⚖️  A/B Тест: AI vs Человек',  '/abtest',     wip=True)

        # ── Низ сайдбара ─────────────────────────────────────────────────
        ui.separator().style('background-color: #2a2a2a; margin: 4px 0;')

        if stats:
            with ui.column().classes('px-4 py-2 gap-0'):
                ui.html('<span class="nav-section" style="padding:0;">📂&nbsp; База данных</span>')
                ui.label(f"Дней в базе: {stats['days_count']}").style('color:#9ca3af;font-size:0.75rem;')
                ui.label(f"{stats['start']} → {stats['end']}").style('color:#6b7280;font-size:0.7rem;')

        def _refresh():
            try:
                db.load_anomalies.cache_clear()
            except Exception:
                pass
            try:
                db.load_inventory.cache_clear()
            except Exception:
                pass
            try:
                db.get_db_stats.cache_clear()
            except Exception:
                pass
            ui.notify('✅ Кэш очищен. Перезайдите на страницу.', type='positive')

        ui.button('🔄 Обновить данные', on_click=_refresh) \
          .props('flat no-caps') \
          .classes('nav-btn w-full')

    # ── ШАПКА ────────────────────────────────────────────────────────────
    with ui.header(elevated=True).style(
        'background-color: #171717; border-bottom: 1px solid #2a2a2a;'
    ) as header:
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=white')
        ui.label('💎 Autonomous Stock Shadow ETL').classes('text-white font-bold ml-2').style('font-size:1.1rem;')
        ui.space()

    return drawer, header
