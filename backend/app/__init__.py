"""
Legacy Flask app package.

WARNING: This module is kept for backward compatibility with existing imports.
The main FastAPI application is in app.main.create_app().
RQ tasks use app.main.create_app() directly.

To start the FastAPI server, use run.py which imports from app.main.
"""
# Re-export db for backward compatibility
from app.models import db

__all__ = ["db"]
