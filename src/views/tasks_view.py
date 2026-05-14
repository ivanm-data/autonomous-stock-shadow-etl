import streamlit as st
import db


def show():
    df_tasks = db.load_anomaly_report("Открыта")  #

    if df_tasks.empty:
        st.success("Все задачи выполнены!")
    else:
        latest_inv = db.load_inventory()  #

        for idx, row in df_tasks.iterrows():
            with st.expander(f"📌 {row['item_name']} ({row['anomaly_type']})"):
                # 1. Получаем текущее значение с сайта
                current_site_qty_list = latest_inv[latest_inv['Наименование'] == row['item_name']]['Остаток'].values
                current_site_qty = int(current_site_qty_list[0]) if len(current_site_qty_list) > 0 else 0

                # 2. Показываем динамику процесса
                m1, m2, m3 = st.columns(3)
                m1.metric("Было в 1С (при фиксации)", f"{row['qty_system']} шт.")
                m2.metric("Твой замер (факт/оценка)", f"{row['qty_physical']} шт.")
                # Дельта показывает, сколько офис "вернул" в систему
                m3.metric("Сейчас на сайте", f"{current_site_qty} шт.",
                          delta=int(current_site_qty - row['qty_system']))

                # 3. Финальное решение
                st.write("---")

                # Выбор причины закрытия, чтобы не портить MTTR склада
                close_reason = st.radio(
                    "Что это было?",
                    ["Обычное расхождение (ошибка склада/1С)", "Просто лаг сайта (Догруз данных)"],
                    key=f"reason_{row['id']}"
                )

                final_note = st.text_input("Заметка при закрытии (опционально):",
                                           placeholder="Напр: Данные в 1С обновлены, остаток корректен",
                                           key=f"note_{row['id']}")

                bc1, bc2 = st.columns(2)
                if bc1.button("✅ Вопрос решен", key=f"close_{row['id']}", type="primary", width="stretch"):

                    # Если это вина сайта, принудительно меняем тип аномалии
                    # Это исключит задачу из расчета MTTR
                    if close_reason == "Просто лаг сайта (Догруз данных)":
                        with db.get_connection() as conn:
                            conn.execute("UPDATE anomaly_log SET anomaly_type = '⏳ Догруз с сайта' WHERE id = ?", (row['id'],))
                            conn.commit()

                    db.close_anomaly_in_db(row['id'], final_note)
                    st.rerun()

                if bc2.button("🗑️ Отменить запись", key=f"cancel_{row['id']}", width="stretch"):
                    db.cancel_anomaly_in_db(row['id'], final_note)
                    st.rerun()
