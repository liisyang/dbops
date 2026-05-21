"""
数据库配置 - 使用原生 SQLAlchemy（移除 Flask 依赖）
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool

from app.config import get_settings

settings = get_settings()

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    poolclass=QueuePool,
    pool_pre_ping=True,
    pool_recycle=300,
    echo=False,
    connect_args={"options": "-c search_path=dbops,public"}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """获取数据库会话 - 依赖注入用"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """初始化数据库 - 创建所有表"""
    Base.metadata.create_all(bind=engine)
