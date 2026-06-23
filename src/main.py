import os
import time
import random
import asyncio
import math
import uvicorn
import hashlib
import json
from dotenv import load_dotenv

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select, and_
from typing import AsyncGenerator, List, Tuple
from datetime import datetime, timezone

from src.db import CodeSubmission
from src.models import CheckRequest, CheckResponse, Match, MethodResult, WeightsUpdateRequest
from src.plagiarism import compare_codes_with_methods
from src.core.core_dependency.db_dependency import DBDependency

SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", 0.7))
MAX_CONCURRENT_CHECKS = int(os.getenv("MAX_CONCURRENT_CHECKS", 10))
EARLY_STOP_THRESHOLD = float(os.getenv("EARLY_STOP_THRESHOLD", 0.95))
CHECK_TIMEOUT_SECONDS = int(os.getenv("CHECK_TIMEOUT_SECONDS", 30))
MAX_MATCHES_RETURNED = int(os.getenv("MAX_MATCHES_RETURNED", 20))
METHOD_NAMES = json.loads(os.getenv("METHOD_NAMES", \
                                    '["AST Structural Analysis", ' \
                                    '"Shingling (n-grams)", ' \
                                    '"Hashing (MD5 blocks)", ' \
                                    '"Cosine Similarity"]'))
DEFAULT_WEIGHTS = json.loads(os.getenv("DEFAULT_WEIGHTS", 
                                       '{"ast": 0.30, ' \
                                        '"shingling": 0.25, ' \
                                        '"hashing": 0.20, ' \
                                        '"cosine": 0.25}'))
current_weights = DEFAULT_WEIGHTS.copy()

db_dependency = DBDependency()
app = FastAPI(title="Antiplagiat module")
check_semaphore = asyncio.Semaphore(MAX_CONCURRENT_CHECKS)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with db_dependency.db_session() as session:
        yield session

def compute_code_hash(code: str) -> str:
    return hashlib.sha256(code.encode()).hexdigest()

def detect_language(code: str) -> str:
    csharp_markers = ["using ", "namespace ", "public class", ";"]
    python_markers = ["def ", "import ", ":"]

    cs_score = sum(m in code for m in csharp_markers)
    py_score = sum(m in code for m in python_markers)

    return "csharp" if cs_score > py_score else "python"

async def check_single_solution(
    payload_code: str,
    submission,
    language: str,
    semaphore: asyncio.Semaphore
) -> Tuple[float, List[MethodResult], object]:
    async with semaphore:
        loop = asyncio.get_event_loop()
        similarity, methods_results = await loop.run_in_executor(
            None,
            compare_codes_with_methods,
            payload_code,
            submission.code,
            language,
            current_weights
        )
        if math.isnan(similarity):
            similarity = 0.0
        return similarity, methods_results, submission


async def check_single_solution_with_timeout(
    payload_code: str,
    submission,
    language: str,
    semaphore: asyncio.Semaphore,
    timeout_seconds: int = 30
) -> Tuple[float, List[MethodResult], object]:
    try:
        return await asyncio.wait_for(
            check_single_solution(payload_code, submission, language, semaphore),
            timeout=timeout_seconds
        )
    except asyncio.TimeoutError:
        print(f"Таймаут для {submission.id}")
        return 0.0, [], submission

def init_methods_results() -> List[MethodResult]:
    return [MethodResult(
        methodName=name,
        similarity=0.0,
        details={}
    ) for name in METHOD_NAMES]

def create_check_response(
    max_similarity: float,
    matches: List[Match],
    accepted: bool,
    methods_results: List[MethodResult]
) -> CheckResponse:
    return CheckResponse(
        maxSimilarity=round(max_similarity, 4),
        matches=matches,
        accepted=accepted,
        methodsResults=methods_results
    )

@app.post("/check-solution", response_model=CheckResponse)
async def check_solution(
    payload: CheckRequest,
    db: AsyncSession = Depends(get_db)
):
    "Основной эндпоинт для проверки нового решения с базой решений."
    start_time = time.time()
    print(f"Начало проверки для taskId={payload.taskId}")
    
    matches: List[Match] = []
    max_similarity = 0.0
    all_methods_results = init_methods_results()

    language = detect_language(payload.code)
    code_hash = compute_code_hash(payload.code)
    print(f"Обнаружен ЯП: {language}, code_hash: {code_hash[:16]}...")

    # Поиск дупликата
    selected = select(CodeSubmission).where(
        and_(
            CodeSubmission.task_id == payload.taskId,
            CodeSubmission.code_hash == code_hash,
            CodeSubmission.language == language
        )
    )
    selected_result = await db.execute(selected)
    submissions = selected_result.scalar_one_or_none()

    if submissions is not None:
        print(f"Дупликат обнаружен: id={submissions.id}, обозначение как 100% схожести.")
        matches = [Match(existing_id=submissions.id,
                        similarity=1.0,
                        submissionDate=submissions.submissionDate)]
        max_similarity = 0.0
        all_methods_results = []
        total_time = time.time() - start_time
        print(f"Поиск дупликата завершен за {total_time:.2f} секунд.")
        print(f"Результаты: max_similarity=100.00%, accepted=False, matches=1")
        return create_check_response(
            max_similarity, 
            matches,
            False, 
            all_methods_results)

    # Если дупликатов не найдено, продолжаем проверку
    selected = select(CodeSubmission).where(
        and_(
            CodeSubmission.task_id == payload.taskId,
            CodeSubmission.language == language,
        )
    )
    selected_result = await db.execute(selected)
    submissions = selected_result.scalars().all()
    
    total_submissions = len(submissions)
    print(f"Найдено {total_submissions} оригинальных решений для сравнения.")
    
    if total_submissions > 0:
        print(f"Начало параллельной проверки {total_submissions} решений.")
        check_start = time.time()
        
        tasks = [
            check_single_solution_with_timeout(
                payload.code,
                submission,
                language,
                check_semaphore,
                timeout_seconds=30
            )
            for submission in submissions
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        check_time = time.time() - check_start
        print(f"Параллельная проверка завершена за {check_time:.2f} секунд.")
        
        successful_results = []
        
        for res in results:
            if isinstance(res, Exception):
                print(f"Ошибка: {res}")
                continue
            
            similarity, methods_results, submission = res
            if math.isnan(similarity):
                similarity = 0.0
                
            successful_results.append((similarity, methods_results, submission))
            
            if similarity > 0:
                matches.append(
                    Match(
                        existing_id=submission.id,
                        similarity=round(similarity, 4),
                        submissionDate=submission.submissionDate
                    )
                )
                
                max_similarity = max(max_similarity, similarity)
                
                for mr in methods_results:
                    for existing in all_methods_results:
                        if existing.methodName == mr.methodName:
                            if mr.similarity > existing.similarity:
                                existing.similarity = mr.similarity
                                existing.details = mr.details
                            break
                
                if max_similarity >= EARLY_STOP_THRESHOLD:
                    print(f"Ранняя остановка проверки: {max_similarity:.2%}")
                    break
        
        matches.sort(key=lambda m: m.similarity, reverse=True)
        matches = matches[:20]
    
    if math.isnan(max_similarity):
        max_similarity = 0.0
    
    accepted = max_similarity <= SIMILARITY_THRESHOLD

    if accepted:
        timestamp = int(time.time() * 1000)
        random_part = random.randint(1000, 9999)
        unique_id = timestamp * 10000 + random_part

        new_submission = CodeSubmission(
            id=unique_id,
            task_id=payload.taskId,
            code=payload.code,
            code_hash=code_hash,
            language=language,
            submissionDate=datetime.now(timezone.utc)
        )
        db.add(new_submission)
        await db.commit()
        print(f"Новое решение сохранено: id={unique_id}, task_id={payload.taskId}")
    
    total_time = time.time() - start_time
    print(f"Проверка завершена в {total_time:.2f} секунд")
    print(f"Результаты: max_similarity={max_similarity:.2%}, accepted={accepted}, matches={len(matches)}")
    
    return create_check_response(
        max_similarity, 
        matches,
        accepted, 
        all_methods_results)

@app.get("/weights")
async def get_weights():
    "Получение текущих весов алгоритмов проверки плагиата"
    return {
        "Текущие веса": current_weights,
        "Веса по-умолчанию": DEFAULT_WEIGHTS,
    }

@app.post("/weights")
async def update_weights(request: WeightsUpdateRequest):
    "Обновление весов алгоритмов проверки плагиата"
    global current_weights
    new_weights = {
        'AST': request.ast,
        'shingling': request.shingling,
        'hashing': request.hashing,
        'cosine': request.cosine,
    }
    
    # Проверяем сумму
    total = sum(new_weights.values())
    if abs(total - 1.0) > 0.01:
        raise HTTPException(
            status_code=400, 
            detail=f"Сумма весов должна быть равна 1.0 (текущая: {total})"
        )
    current_weights = new_weights
    print(f"Веса обновлены: {current_weights}")
    
    return {
        "Сообщение": "Веса успешно обновлены",
        "Веса": current_weights,
    }

@app.post("/weights/reset")
async def reset_weights():
    "Сброс весов к значениям по умолчанию"
    global current_weights
    current_weights = DEFAULT_WEIGHTS.copy()
    
    return {
        "Сообщение": "Весы сброшены к значениям по умолчанию",
        "Текущие веса": current_weights,
        "Веса по-умолчанию": DEFAULT_WEIGHTS
    }

@app.get("/submissions/{submission_id}")
async def get_submission_by_id(
    submission_id: int,
    db: AsyncSession = Depends(get_db)
):
    "Получение решения по его id"
    stmt = select(CodeSubmission).where(CodeSubmission.id == submission_id)
    result = await db.execute(stmt)
    submission = result.scalar_one_or_none()
    
    if not submission:
        raise HTTPException(status_code=404, detail=f"Решение с id {submission_id} не найдено")
    
    return {
        "id": submission.id,
        "language": submission.language,
        "task_id": submission.task_id,
        "code_hash": submission.code_hash,
        "code": submission.code,
        "submission_date": submission.submissionDate.isoformat() if submission.submissionDate else None
    }

@app.get("/submissions/by-task/{task_id}")
async def get_submissions_by_task(
    task_id: int,
    limit: int = 100,
    offset: int = 0,
    include_code: bool = False,
    db: AsyncSession = Depends(get_db)
):
    "Получение всех решений по идентификатору задания"
    
    count_stmt = select(func.count()).where(
        CodeSubmission.task_id == task_id
    )
    total_count = await db.scalar(count_stmt)
    
    stmt = select(CodeSubmission).where(
        CodeSubmission.task_id == task_id
    ).order_by(
        CodeSubmission.submissionDate.desc()
    ).offset(offset).limit(limit)
    
    result = await db.execute(stmt)
    submissions = result.scalars().all()
    
    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "items": [{
            "id": s.id,
            "code_hash": s.code_hash,
            "code": s.code if include_code else None,
            "language": s.language,
            "task_id": s.task_id,
            "submission_date": s.submissionDate.isoformat() if s.submissionDate else None
        } for s in submissions]
    }

@app.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    "Статистика базы кода"
    
    
    total_count = await db.scalar(select(func.count()).select_from(CodeSubmission))
    unique_hashes = await db.scalar(select(func.count(CodeSubmission.code_hash.distinct())))
    unique_tasks = await db.scalar(select(func.count(CodeSubmission.task_id.distinct())))
    
    return {
        "total_submissions": total_count,
        "unique_code_hashes": unique_hashes,
        "unique_tasks": unique_tasks,
        "threshold": SIMILARITY_THRESHOLD
    }

@app.get("/status")
async def get_service_status(db: AsyncSession = Depends(get_db)):
    "Проверка обработки запросов сервиса"
    return {
        "status": "healthy",
    }

load_dotenv()

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", 8000)),
        reload=True
    )