"""Timezone-aware datetime helpers.

All service / task code that needs "now" should use `now_local()` so that
ORM writes and DB-side `now()` / triggers stay in the same naive local
timezone (Asia/Shanghai in prod).

Why naive local and not UTC?
- All datetime columns are `TIMESTAMP WITHOUT TIME ZONE`.
- DB triggers (`set_updated_at`, `NOW()` defaults) write naive local.
- Mixing naive UTC writes (Python) with naive local reads (DB triggers) is
  exactly the M14 bug class. M14 v2/v3 aligned everything to local; this
  helper is the single entry point so the next service to be added can't
  regress it.
"""
from __future__ import annotations

from datetime import datetime


def now_local() -> datetime:
    """Return the current local datetime (naive).

    Matches PostgreSQL's session-timezone `now()` for naive columns, so a
    fresh INSERT from this function and an UPDATE from a `set_updated_at`
    trigger resolve to the same wall clock.
    """
    return datetime.now()
