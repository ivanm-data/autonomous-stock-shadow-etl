import streamlit as st
import pandas as pd
import db
import ai_services


def show():
    st.subheader("📸 Оцифровка накладной (Нейро-приемка)")
    st.caption("Загрузите фото таблицы с товарами. Цены и контрагентов в кадр брать не нужно.")
    
    # Оставляем только загрузку из галереи по твоей просьбе
    file_photo = st.file_uploader("📂 Выберите фото из галереи (накладная):", type=["jpg", "jpeg", "png"])
    
    if file_photo:
        st.image(file_photo, caption="📸 Фото загружено", width=400)
        
        if st.button("🚀 Отправить на оцифровку", type="primary", width="stretch"):
            with st.spinner("🧠 Нейросеть Gemini читает таблицу..."):
                try:
                    items_list = ai_services.digitize_invoice(file_photo)
                    
                    st.success(f"✅ Распознано позиций: {len(items_list)}")
                    st.session_state.temp_invoice = items_list
                    
                except Exception as e:
                    st.error(f"❌ Ошибка распознавания: {e}")
            
    
        # Блок сохранения результата
        if 'temp_invoice' in st.session_state:
            st.write("---")
            st.write("**Результат оцифровки:**")
            df_result = pd.DataFrame(st.session_state.temp_invoice)
            
            st.dataframe(df_result, width="stretch", hide_index=True)
            
            if st.button("💾 Подтвердить и сохранить в Ожидаемые приходы", type="primary"):
                with db.get_connection() as conn:
                    for item in st.session_state.temp_invoice:
                        try:
                            qty = int(item.get('количество', 0))
                        except (ValueError, TypeError):
                            qty = 0
                            
                        conn.execute("""
                            INSERT INTO expected_deliveries (item_name, sku, qty_expected) 
                            VALUES (?, ?, ?)
                        """, (str(item.get('название', '')), str(item.get('артикул', '')), qty))
                    conn.commit()
                
                del st.session_state.temp_invoice
                st.success("🎉 Данные успешно добавлены в список ожидания!")
                st.rerun()
            
    st.divider()
    st.subheader("📋 Список ожидаемых товаров")
    st.caption("Эти позиции были оцифрованы и ждут появления на сайте для авто-легализации аномалий.")
    
    with db.get_connection() as conn:
        # Вытаскиваем только те товары, которые еще не были легализованы
        expected_df = pd.read_sql_query(
            "SELECT id, created_at, sku, item_name, qty_expected FROM expected_deliveries WHERE status = 'Ожидает' ORDER BY created_at DESC", 
            conn
        )
        
    if expected_df.empty:
        st.info("В листе ожидания пока ничего нет.")
    else:
        # Рисуем шапку таблицы
        hc = st.columns([2, 2, 4, 2, 1])
        for col, title in zip(hc, ["Дата сканирования", "Артикул", "Наименование", "Ожидаем", "Действие"]):
            col.write(f"**{title}**")
        st.divider()
        
        # Построчный вывод каждого ожидаемого товара
        for _, row in expected_df.iterrows():
            c = st.columns([2, 2, 4, 2, 1])
            
            # 1. Дата (обрезаем до минут для красоты)
            c[0].caption(str(row['created_at'])[:16])
            
            # 2. Артикул
            sku_text = row['sku'] if pd.notna(row['sku']) and row['sku'] else "—"
            c[1].write(sku_text)
            
            # 3. Название
            c[2].write(row['item_name'])
            
            # 4. Количество
            c[3].write(f"{row['qty_expected']} шт.")
            
            # 5. Кнопка удаления (полностью удаляет строку из БД)
            if c[4].button("❌", key=f"del_exp_{row['id']}", help="Удалить позицию из листа ожидания"):
                with db.get_connection() as conn:
                    conn.execute("DELETE FROM expected_deliveries WHERE id = ?", (row['id'],))
                    conn.commit()
                st.toast(f"🗑️ Товар удален из ожидания: {row['item_name']}")
                st.rerun()
            
            st.divider()
