import sqlite3
from pathlib import Path

# Вычисляем корень проекта: поднимаемся на два уровня вверх от самого скрипта
BASE_DIR = Path(__file__).resolve().parent.parent 
DB_PATH = BASE_DIR / "data" / "stock_history.sqlite"

def migrate_forecasts_schema():
    """Добавляет новые колонки в таблицу ai_forecasts для поддержки математических прогнозов"""
    # Проверяем, существует ли база данных
    if not DB_PATH.exists():
        print(f"[ERROR] База данных не найдена по пути:\n{DB_PATH}")
        return False

    print(f"[INFO] Подключаемся к базе:\n{DB_PATH}")
    
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Проверяем, существуют ли уже новые колонки
        cursor.execute("PRAGMA table_info(ai_forecasts)")
        columns = [row[1] for row in cursor.fetchall()]
        
        new_columns = ['lead_time_days', 'safety_stock', 'base_demand']
        existing_columns = [col for col in new_columns if col in columns]
        
        if existing_columns:
            print(f"[WARN] Колонки уже существуют: {', '.join(existing_columns)}")
            return True
        
        # Добавляем новые колонки
        try:
            cursor.execute("ALTER TABLE ai_forecasts ADD COLUMN lead_time_days INTEGER DEFAULT 14")
            print("[OK] Добавлена колонка: lead_time_days")
        except sqlite3.OperationalError as e:
            print(f"[WARN] Колонка lead_time_days уже существует: {e}")
        
        try:
            cursor.execute("ALTER TABLE ai_forecasts ADD COLUMN safety_stock INTEGER DEFAULT 0")
            print("[OK] Добавлена колонка: safety_stock")
        except sqlite3.OperationalError as e:
            print(f"[WARN] Колонка safety_stock уже существует: {e}")
        
        try:
            cursor.execute("ALTER TABLE ai_forecasts ADD COLUMN base_demand INTEGER DEFAULT 0")
            print("[OK] Добавлена колонка: base_demand")
        except sqlite3.OperationalError as e:
            print(f"[WARN] Колонка base_demand уже существует: {e}")
        
        try:
            cursor.execute("ALTER TABLE ai_forecasts ADD COLUMN needs_recalc INTEGER DEFAULT 0")
            print("[OK] Добавлена колонка: needs_recalc")
        except sqlite3.OperationalError as e:
            print(f"[WARN] Колонка needs_recalc уже существует: {e}")
        
        conn.commit()
        
        # Сбрасываем флаг пересчёта для всех существующих прогнозов
        cursor.execute("UPDATE ai_forecasts SET needs_recalc = 0")
        print("[OK] Сброшен флаг needs_recalc для всех прогнозов")
        
        # Проверяем результат
        cursor.execute("PRAGMA table_info(ai_forecasts)")
        columns = [row[1] for row in cursor.fetchall()]
        print(f"\n[INFO] Текущие колонки ai_forecasts: {', '.join(columns)}")
        
        print("\n[OK] Миграция завершена! Новые колонки добавлены.")
        return True

if __name__ == "__main__":
    migrate_forecasts_schema()
