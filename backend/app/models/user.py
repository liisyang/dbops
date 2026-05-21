"""
用户模型 - 对应 PostgreSQL dbops.users 表
"""
from datetime import datetime
import uuid
from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    """平台用户表"""
    __tablename__ = 'users'
    __table_args__ = {'schema': 'dbops'}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(200), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(100))
    department = Column(String(200))
    role = Column(String(50), default='admin')
    is_active = Column(Boolean, default=True)
    timezone = Column(String(50), default='Asia/Shanghai')
    language = Column(String(20), default='zh-CN')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def verify_password(self, password):
        """验证密码"""
        if not self.password_hash:
            return False

        hash_str = self.password_hash

        # 兼容历史 bcrypt 哈希（形如 $2b$...）
        if hash_str.startswith(("$2a$", "$2b$", "$2y$")):
            import bcrypt
            try:
                return bcrypt.checkpw(password.encode("utf-8"), hash_str.encode("utf-8"))
            except (ValueError, TypeError):
                return False

        # 默认走 werkzeug 哈希校验（scrypt/pbkdf2 等）
        from werkzeug.security import check_password_hash
        try:
            return check_password_hash(hash_str, password)
        except (ValueError, TypeError):
            # 异常哈希格式按校验失败处理，避免 500
            return False

    def __repr__(self):
        return f'<User {self.username}>'
