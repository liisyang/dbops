import os
from functools import lru_cache
from pydantic_settings import BaseSettings

# 获取 backend 目录路径
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Settings(BaseSettings):
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    POSTGRES_HOST: str = "10.134.185.85"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "dbops"
    POSTGRES_PASSWORD: str = "root123"
    POSTGRES_DB: str = "dbops"
    SQLALCHEMY_DATABASE_URI: str = ""

    # SSH 凭据
    SSH_USER: str = "dbaacc"
    SSH_PASSWORD: str = ""
    SSH_KEY: str = "~/.ssh/id_ed25519"
    SSH_USER_GROUP: str = "dba"
    SSH_USER_HOME_PREFIX: str = "/home"
    SSH_PROFILE_PATH: str = "/home"
    SSH_TIMEOUT: int = 30
    SSH_PORT: int = 22

    # RQ / Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Ansible 配置
    ANSIBLE_TIMEOUT: int = 10
    ANSIBLE_FORKS: int = 20

    # 主机状态探测
    HOST_CHECK_INTERVAL: int = 600

    # CORS
    CORS_ORIGINS: str = ""

    # Upload
    UPLOAD_FOLDER: str = "uploads"
    ALLOWED_EXTENSIONS: set = {"xlsx", "xls"}

    class Config:
        env_file = os.path.join(BASE_DIR, '.env')
        extra = "allow"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.SQLALCHEMY_DATABASE_URI:
            self.SQLALCHEMY_DATABASE_URI = (
                f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
