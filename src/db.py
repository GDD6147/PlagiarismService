from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import Column, Integer, BigInteger, String, Text, TIMESTAMP, Index
from datetime import datetime


class Base(DeclarativeBase):
    pass


class CodeSubmission(Base):
    __tablename__ = "code_submissions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    language = Column(String(50), nullable=False)
    task_id = Column(Integer, nullable=False, index=True)
    code_hash = Column(String(64), nullable=False, index=True)
    code = Column(Text, nullable=False)
    submissionDate = Column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )
    
    __table_args__ = (
        Index('idx_task_hash', 'task_id', 'code_hash'),
    )