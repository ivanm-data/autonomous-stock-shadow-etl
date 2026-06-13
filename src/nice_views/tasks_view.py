"""
tasks_view.py — NiceGUI-версия вкладки Задачи.
Полный перенос функционала из src/views/tasks_view.py.
"""
from nicegui import ui
import sys
import os
import logging

_src_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

import db
from nice_views.shared_layout import build_shell

logger = logging.getLogger('shadow_stock.tasks')


# ─────────────────────────────────────────────────────────────────────────────
#  Вспомогательный компонент: метрика
# ─────────────────────────────────────────────────────────────────────────────

def _metric(label: str, value: str, color: str, delta: int | None = None):
    """Тёмная карточка-метрика с опциональной дельтой."""
    with ui.card().classes('p-4').style(
        f'background:#171717; border-left:3px solid {color}; min-width:160px;'
    ):
        ui.label(value).classes('text-white text-2xl font-bold')
        ui.label(label).style('color:#9ca3af; font-size:0.78rem;')
        if delta is not None:
            if delta > 0:
                delta_text  = f'+{delta} шт.'
                delta_color = '#34d399'
            elif delta < 0:
                delta_text  = f'{delta} шт.'
                delta_color = '#f87171'
            else:
                delta_text  = '± 0 шт.'
                delta_color = '#6b7280'
            ui.label(delta_text).style(f'color:{delta_color}; font-size:0.78rem; font-weight:600;')


# ─────────────────────────────────────────────────────────────────────────────
#  Страница задач
# ─────────────────────────────────────────────────────────────────────────────

def setup_page():

    @ui.page('/tasks')
    def tasks_page():
        logger.info('tasks_page() handler entered')
        build_shell('/tasks')

        with ui.column().classes('w-full p-4 gap-4').style(
            'background:#0d0d0d; min-height:100vh;'
        ):
            with ui.row().classes('w-full items-center justify-between flex-wrap gap-2'):
                ui.label('🔥 Задачи').classes('text-white text-2xl font-bold')
                ui.label(
                    'Открытые расхождения, требующие физической проверки на полке.'
                ).style('color:#9ca3af; font-size:0.85rem;')

            ui.separator().style('background:#2a2a2a;')

            @ui.refreshable
            def render_tasks():
                df_tasks = db.load_anomaly_report('Открыта')

                # ── Нет задач ─────────────────────────────────────────────
                if df_tasks.empty:
                    with ui.card().classes('w-full p-6 items-center gap-3').style(
                        'background:#052e16; border:1px solid #22c55e;'
                    ):
                        ui.icon('check_circle', size='48px').style('color:#22c55e;')
                        ui.label('Все задачи выполнены!').classes(
                            'text-green-400 text-xl font-bold'
                        )
                        ui.label('Новых расхождений нет.').style('color:#6b7280;')
                    return

                # Загружаем текущие остатки для сравнения
                latest_inv = db.load_inventory()

                ui.label(f'Открытых задач: {len(df_tasks)}').style(
                    'color:#f97316; font-size:0.85rem; font-weight:600;'
                )

                # ── Карточка на каждую задачу ─────────────────────────────
                for _, row in df_tasks.iterrows():
                    row_id   = int(row['id'])
                    item     = str(row['item_name'])
                    anom_t   = str(row['anomaly_type'])
                    qty_sys  = int(row.get('qty_system',   0) or 0)
                    qty_phys = int(row.get('qty_physical', 0) or 0)
                    detected = str(row.get('detected_at', ''))[:16]
                    source   = str(row.get('source', '—'))
                    impact   = float(row.get('financial_impact', 0) or 0)
                    note_old = str(row.get('comment', '') or '')

                    # Текущий остаток на сайте
                    match = latest_inv[latest_inv['Наименование'] == item]['Остаток'].values
                    current_site_qty = int(match[0]) if len(match) > 0 else 0
                    delta_qty = current_site_qty - qty_sys

                    # Цвет карточки по типу аномалии
                    border_color = '#ef4444'
                    if 'лаг' in anom_t.lower() or 'догруз' in anom_t.lower():
                        border_color = '#f59e0b'
                    elif 'пересорт' in anom_t.lower():
                        border_color = '#a78bfa'

                    with ui.expansion(
                        f'📌 {item}  ·  {anom_t}'
                    ).classes('w-full').style(
                        f'background:#111111; border:1px solid {border_color}; '
                        f'border-radius:8px; margin-bottom:8px;'
                    ):
                        with ui.column().classes('w-full gap-4 p-2'):

                            # ── Мета-строка ───────────────────────────────
                            with ui.row().classes('gap-4 flex-wrap'):
                                ui.label(f'🕐 {detected}').style('color:#6b7280; font-size:0.8rem;')
                                ui.label(f'📍 Источник: {source}').style('color:#6b7280; font-size:0.8rem;')
                                if impact:
                                    ui.label(f'💰 Ущерб: {impact:,.0f} ₽').style(
                                        'color:#f87171; font-size:0.8rem; font-weight:600;'
                                    )
                                if note_old:
                                    ui.label(f'📝 {note_old}').style(
                                        'color:#9ca3af; font-size:0.8rem; font-style:italic;'
                                    )

                            # ── Метрики: было / факт / сейчас ────────────
                            with ui.row().classes('gap-4 flex-wrap'):
                                _metric('Было в 1С (при фиксации)', f'{qty_sys} шт.',  '#60a5fa')
                                _metric('Твой замер (факт/оценка)',  f'{qty_phys} шт.', '#a78bfa')
                                _metric('Сейчас на сайте',           f'{current_site_qty} шт.',
                                        '#34d399', delta=delta_qty)

                            ui.separator().style('background:#2a2a2a;')

                            # ── Причина закрытия ──────────────────────────
                            ui.label('Что это было?').style(
                                'color:#d1d5db; font-size:0.9rem; font-weight:600;'
                            )
                            close_reason = ui.radio(
                                options=[
                                    'Обычное расхождение (ошибка склада/1С)',
                                    'Просто лаг сайта (Догруз данных)',
                                ],
                                value='Обычное расхождение (ошибка склада/1С)',
                            ).style('color:#d1d5db;')

                            final_note = ui.input(
                                label='Заметка при закрытии (опционально):',
                                placeholder='Напр: Данные в 1С обновлены, остаток корректен',
                            ).classes('w-full').style('color:white;')

                            # ── Кнопки действий ───────────────────────────
                            with ui.row().classes('gap-3'):

                                def _close(
                                    _id=row_id,
                                    _reason=close_reason,
                                    _note=final_note,
                                ):
                                    if _reason.value == 'Просто лаг сайта (Догруз данных)':
                                        with db.get_connection() as conn:
                                            conn.execute(
                                                "UPDATE anomaly_log "
                                                "SET anomaly_type = '⏳ Догруз с сайта' "
                                                "WHERE id = ?",
                                                (_id,)
                                            )
                                            conn.commit()
                                    db.close_anomaly_in_db(_id, _note.value or '')
                                    ui.notify('✅ Задача закрыта!', type='positive')
                                    render_tasks.refresh()

                                def _cancel(
                                    _id=row_id,
                                    _note=final_note,
                                ):
                                    db.cancel_anomaly_in_db(_id, _note.value or '')
                                    ui.notify('🗑️ Запись отменена.', type='info')
                                    render_tasks.refresh()

                                ui.button('✅ Вопрос решён', on_click=_close) \
                                  .props('color=primary no-caps')
                                ui.button('🗑️ Отменить запись', on_click=_cancel) \
                                  .props('flat color=negative no-caps')

            render_tasks()
