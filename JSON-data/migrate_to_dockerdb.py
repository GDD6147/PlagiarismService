import json
import hashlib
import asyncio
import asyncpg
import os
from datetime import datetime, timezone

def to_datetime(date_str):
    """Надежное преобразование строки в datetime"""
    if not date_str:
        return datetime.now(timezone.utc)
    
    # Заменяем Z на +00:00 для ISO формата
    if isinstance(date_str, str):
        date_str = date_str.replace('Z', '+00:00')
        # Парсим ISO формат
        return datetime.fromisoformat(date_str)
    elif isinstance(date_str, datetime):
        return date_str
    else:
        return datetime.now(timezone.utc)

async def migrate():
    conn = await asyncpg.connect(
        host=os.getenv("DB_HOST", "postgres"),
        database=os.getenv("DB_NAME", "antiplagiat_db"),
        user=os.getenv("DB_USER", "app"),
        password=os.getenv("DB_PASSWORD", "app"),
        port=os.getenv("DB_PORT", "5432")
    )
    
    with open('submissions.json', 'r', encoding='utf-8') as f:
        solutions = json.load(f)
    
    print(f"Загружено {len(solutions)} записей из JSON")
    
    # Подготавливаем все данные заранее
    records = []
    seen = set()
    
    for sol in solutions:
        code_hash = hashlib.sha256(sol['code'].encode('utf-8')).hexdigest()
        task_id = sol['taskId']
        key = f"{task_id}_{code_hash}"
        
        if key in seen:
            continue
        seen.add(key)
        
        # Проверяем существование
        existing = await conn.fetchval(
            "SELECT id FROM code_submissions WHERE task_id=$1 AND code_hash=$2",
            task_id, code_hash
        )
        
        if existing:
            continue
        
        # Преобразуем дату ДО добавления в список
        submission_date = to_datetime(sol.get('submissionDate'))
        
        records.append((
            sol['language'],
            task_id,
            submission_date,  # datetime объект
            sol['code'],
            code_hash
        ))
    
    # Вставка записей
    if records:
        async with conn.transaction():
            for record in records:
                await conn.execute("""
                    INSERT INTO code_submissions 
                    (language, task_id, "submissionDate", code, code_hash)
                    VALUES ($1, $2, $3, $4, $5)
                """, *record)
        
        print(f"✓ Мигрировано {len(records)} записей")
    else:
        print("Нет новых записей для миграции")
    
    await conn.close()

if __name__ == "__main__":
    asyncio.run(migrate())