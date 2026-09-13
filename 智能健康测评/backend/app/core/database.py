"""SQLAlchemy 统一入口：engine / SessionLocal / Base / get_db"""
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from app.core.config import settings

logger = logging.getLogger("app.db")

engine = create_engine(
    settings.db_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_recycle=3600,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

Base = declarative_base()


def get_db():
    """FastAPI 依赖：每个请求一个 Session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（若不存在则创建）"""
    # 导入模型确保注册
    from app.models import assessment, knowledge_file, assistant, meal, social, auth, tongue, plan, privacy  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("数据库表结构初始化完成")
