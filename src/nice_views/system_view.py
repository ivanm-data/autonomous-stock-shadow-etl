"""
system_view.py — Вкладка «Система» для административных задач.
Позволяет выявлять и удалять «битые» дни парсинга (неполные данные).

Паттерн: shell + ui.timer(once=True) — страница отвечает мгновенно,
данные загружаются в фоне после отправки shell браузеру.
"""
from nicegui import ui, run as ng_run
import sys
import os
import logging

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import db
from nice_views.shared_layout import build_shell

logger = logging.getLogger('shadow_stock.system')


# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательные функции
# ─────────────────────────────────────────────────────────────────────────────

def _compute_threshold(stats: list) -> tuple[float, float]:
    """
    Вычисляет 90-й перцентиль и порог (80% от него)
    по последним 30 дням (или всей истории, если меньше).

    Возвращает (p90, threshold).
    SQLite не поддерживает PERCENTILE_CONT — считаем в Python.
    """
    window = stats[:30]           # stats уже отсортированы DESC по дате
    counts = sorted(row["items_count"] for row in window)
    if not counts:
        return 0.0, 0.0
    idx = max(0, int(len(counts) * 0.90) - 1)
    p90 = counts[idx]
    return float(p90), float(p90 * 0.80)


def _do_delete(date: str) -> None:
    """Выполняет удаление дня — вызывается из io_bound."""
    logger.info(f'system: deleting day {date}')
    db.delete_day_data(date)
    logger.info(f'system: day {date} deleted OK')


# ─────────────────────────────────────────────────────────────────────────────
#  Страница
# ─────────────────────────────────────────────────────────────────────────────

def setup_page():

    @ui.page('/system')
    async def system_page():
        logger.info('system_page() handler entered')
        build_shell('/system')

        # ── Outer shell — возвращается браузеру немедленно ───────────────
        with ui.column().classes('w-full p-4 gap-4').style(
            'background:#0d0d0d; min-height:100vh;'
        ):
            # Заголовок
            with ui.row().classes('w-full items-center gap-3'):
                ui.label('⚙️ Системные настройки').classes(
                    'text-white text-xl font-bold'
                )
            ui.label(
                'Административные инструменты. Операции здесь необратимы.'
            ).style('color:#6b7280; font-size:0.85rem;')
            ui.separator().style('background:#2a2a2a;')

            # Спиннер загрузки
            spinner_row = ui.row().classes(
                'w-full items-center justify-center p-12 gap-4'
            )
            with spinner_row:
                ui.spinner(size='xl').props('color=warning')
                ui.label('Загрузка статистики...').style(
                    'color:#9ca3af; font-size:1rem;'
                )

            # Контейнер контента — скрыт до загрузки данных
            content_col = ui.column().classes('w-full gap-4')
            content_col.set_visibility(False)

        # ── Отложенный загрузчик ─────────────────────────────────────────
        async def _load_and_render():
            stats = await ng_run.io_bound(db.get_parse_days_stats)
            spinner_row.set_visibility(False)

            p90, threshold = _compute_threshold(stats)

            with content_col:
                # ── Секция: История парсинга ──────────────────────────────
                with ui.row().classes('w-full items-center justify-between flex-wrap gap-2'):
                    ui.label('🗑️ Управление историей парсинга').classes(
                        'text-white text-lg font-bold'
                    )

                # Информационный баннер с порогом
                if p90 > 0:
                    with ui.card().classes('w-full p-3').style(
                        'background:#111827; border:1px solid #374151;'
                    ):
                        with ui.row().classes('gap-6 flex-wrap'):
                            with ui.column().classes('gap-0'):
                                ui.label(f'{int(p90):,}'.replace(',', '\u00a0') + ' тов.').classes(
                                    'text-white font-bold text-lg'
                                )
                                ui.label('90-й перцентиль (норма)').style(
                                    'color:#9ca3af; font-size:0.75rem;'
                                )
                            with ui.column().classes('gap-0'):
                                ui.label(f'{int(threshold):,}'.replace(',', '\u00a0') + ' тов.').classes(
                                    'text-amber-300 font-bold text-lg'
                                )
                                ui.label('Порог сбойного дня (−20%)').style(
                                    'color:#9ca3af; font-size:0.75rem;'
                                )
                            with ui.column().classes('gap-0'):
                                ui.label(f'{len(stats)} дней').classes(
                                    'text-blue-300 font-bold text-lg'
                                )
                                ui.label('Всего в базе').style(
                                    'color:#9ca3af; font-size:0.75rem;'
                                )

                if not stats:
                    with ui.card().classes('w-full p-4').style(
                        'background:#171717; border:1px solid #2a2a2a;'
                    ):
                        ui.label('ℹ️ База данных пуста.').classes('text-gray-400')
                    content_col.set_visibility(True)
                    return

                # ── Список дней (refreshable) ─────────────────────────────
                # Храним состояние в списке чтобы refreshable мог его видеть
                _stats_holder = [stats]
                _p90_holder = [p90]
                _thr_holder = [threshold]

                @ui.refreshable
                def render_days():
                    cur_stats = _stats_holder[0]
                    cur_thr   = _thr_holder[0]

                    if not cur_stats:
                        with ui.card().classes('w-full p-4').style(
                            'background:#052e16; border:1px solid #22c55e;'
                        ):
                            ui.label('✅ История очищена.').classes('text-green-400')
                        return

                    for row in cur_stats:
                        date_str   = row['parse_date']
                        count      = row['items_count']
                        is_broken  = (cur_thr > 0) and (count < cur_thr)

                        card_style = (
                            'background:#2d0000; border:1px solid #ef4444;'
                            if is_broken else
                            'background:#171717; border:1px solid #2a2a2a;'
                        )

                        with ui.card().classes('w-full p-3').style(card_style):
                            with ui.row().classes(
                                'w-full items-center justify-between flex-wrap gap-2'
                            ):
                                # Дата и счётчик
                                with ui.row().classes('items-center gap-4'):
                                    ui.label(date_str).classes(
                                        'text-white font-mono font-semibold'
                                    )
                                    ui.label(
                                        f'{count:,}'.replace(',', '\u00a0') + ' товаров'
                                    ).classes(
                                        'text-red-300 font-bold'
                                        if is_broken else
                                        'text-green-300 font-bold'
                                    )
                                    if is_broken:
                                        ui.badge('⚠ Сбойный день', color='red').style(
                                            'font-size:0.7rem;'
                                        )
                                    else:
                                        ui.badge('✓ Норма', color='green').style(
                                            'font-size:0.7rem;'
                                        )

                                # Кнопка удаления с диалогом
                                def _make_delete_handler(d=date_str):
                                    async def _on_confirm():
                                        confirm_dialog.close()
                                        await ng_run.io_bound(_do_delete, d)
                                        # Обновляем список
                                        fresh = await ng_run.io_bound(
                                            db.get_parse_days_stats
                                        )
                                        _stats_holder[0] = fresh
                                        new_p90, new_thr = _compute_threshold(fresh)
                                        _p90_holder[0] = new_p90
                                        _thr_holder[0] = new_thr
                                        render_days.refresh()
                                        ui.notify(
                                            f'✅ День {d} удалён.',
                                            type='positive', timeout=4000
                                        )

                                    with ui.dialog() as confirm_dialog:
                                        with ui.card().classes('p-6').style(
                                            'background:#1a1a1a; border:1px solid #ef4444;'
                                            'min-width:340px;'
                                        ):
                                            ui.label('⚠️ Подтвердите удаление').classes(
                                                'text-white font-bold text-lg mb-2'
                                            )
                                            ui.label(
                                                f'Все данные за {d} будут безвозвратно удалены:'
                                            ).classes('text-gray-300 text-sm')
                                            ui.label(
                                                '• Записи из таблицы склада (stocks)\n'
                                                '• Inbox-аномалии за этот день\n'
                                                '• Автоматически закрытые инциденты'
                                            ).style(
                                                'color:#9ca3af; font-size:0.8rem;'
                                                'white-space:pre-line; margin:8px 0;'
                                            )
                                            with ui.row().classes('gap-3 mt-4 justify-end w-full'):
                                                ui.button(
                                                    'Отмена',
                                                    on_click=confirm_dialog.close
                                                ).props('flat color=grey')
                                                ui.button(
                                                    '🗑 Удалить безвозвратно',
                                                    on_click=_on_confirm
                                                ).props('color=negative')

                                    def _open_dialog():
                                        confirm_dialog.open()

                                    return _open_dialog

                                ui.button(
                                    '🗑 Удалить',
                                    on_click=_make_delete_handler()
                                ).props('outline color=negative size=sm')

                render_days()

            content_col.set_visibility(True)

        ui.timer(0.1, _load_and_render, once=True)
