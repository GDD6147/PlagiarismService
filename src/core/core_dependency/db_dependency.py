from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  
import sys
import os

from src.core.settings import settings


class DBDependency:  
    def __init__(self) -> None:  
        self._engine = create_async_engine(url=settings.db_settings.db_url, echo=settings.db_settings.db_echo)  
        self._session_factory = async_sessionmaker(
            bind=self._engine, 
            expire_on_commit=False, 
            autocommit=False
        )  

    @property  
    def db_session(self) -> async_sessionmaker[AsyncSession]:  
        return self._session_factory