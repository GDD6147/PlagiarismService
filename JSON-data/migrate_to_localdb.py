import json
import hashlib
import psycopg2
from psycopg2.extras import execute_values

DB_CONFIG = {
    "host": "localhost",
    "database": "Antiplagiat",
    "user": "postgres",
    "password": "223",
    "port": 5432
}

JSON_FILE_PATH = "student-solutions-2025-11-29-updated.json"


def compute_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode('utf-8')).hexdigest()


def migrate():
    # Загружаем JSON
    with open(JSON_FILE_PATH, 'r', encoding='utf-8') as f:
        solutions = json.load(f)
    
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # Подготавливаем данные
    values = []
    seen = set()
    
    for sol in solutions:
        code_hash = compute_code_hash(sol['code'])
        task_id = sol['taskId']
        
        # Пропускаем дубликаты
        key = f"{task_id}_{code_hash}"
        if key in seen:
            continue
        seen.add(key)
        
        values.append((
            sol['language'],
            task_id,
            sol.get('submissionDate', 'NOW()'),
            sol['code'],
            code_hash
        ))
    
    # Массовая вставка
    execute_values(cursor, """
        INSERT INTO public.code_submissions
        ("language", "task_id", "submissionDate", "code", "code_hash")
        VALUES %s
    """, values)
    
    conn.commit()
    print(f"Migrated {len(values)} solutions")
    
    cursor.close()
    conn.close()


if __name__ == "__main__":
    migrate()