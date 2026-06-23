from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class CheckRequest(BaseModel):
    taskId: int
    code: str


class Match(BaseModel):
    existing_id: int
    similarity: float
    submissionDate: datetime


class MethodResult(BaseModel):
    methodName: str
    similarity: float
    details: Optional[Dict[str, Any]] = None


class CheckResponse(BaseModel):
    maxSimilarity: float
    matches: List[Match]
    accepted: bool
    methodsResults: List[MethodResult] = []

class WeightsUpdateRequest(BaseModel):
    ast: float = Field(..., ge=0, le=1, description="Вес AST-анализа (0-1)")
    shingling: float = Field(..., ge=0, le=1, description="Вес метода шинглов (0-1)")
    hashing: float = Field(..., ge=0, le=1, description="Вес метода хеширования (0-1)")
    cosine: float = Field(..., ge=0, le=1, description="Вес косинусного сходства (0-1)")
    
    @validator('ast', 'shingling', 'hashing', 'cosine')
    def validate_sum(cls, v, values, **kwargs):
        """Проверка, что сумма весов равна 1"""
        # Собираем все значения
        all_values = [v] + [values.get(field) for field in ['shingling', 'hashing', 'cosine'] 
                           if field in values]
        # Если все поля заполнены, проверяем сумму
        if len(all_values) == 4:
            total = sum(all_values)
            if abs(total - 1.0) > 0.01:  # Допустимая погрешность 0.01
                raise ValueError(f"Сумма весов должна быть равна 1.0 (текущая: {total})")
        return v