"""
Pytest 配置和共享 fixtures
"""
import pytest
import sys
import os

# 确保 app 模块在路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def mock_db():
    """创建模拟数据库会话"""
    from unittest.mock import MagicMock
    return MagicMock()
