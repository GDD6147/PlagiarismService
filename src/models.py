from pydantic import BaseModel
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