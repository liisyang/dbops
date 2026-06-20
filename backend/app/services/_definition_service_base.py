"""BaseDefinitionService — shared list + _to_dict template for 1:1 lookup services.

I9 (PR review 2026-06-20): port_profile_service and collector_check_definition_service
share an identical query → filter → order_by → list-comprehension pattern. Extract here
so both inherit the boilerplate and only supply model + serialization.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session


class BaseDefinitionService:
    """Shared base for definition-lookup services with a list(**filters) method.

    Subclasses must set:
      - model: the SQLAlchemy model class
      - _to_dict(row) -> dict[str, Any]: row serialization

    Optional overrides:
      - _default_order_by: column expression for order_by (default: model.id.asc())
    """

    model: type

    @classmethod
    def _to_dict(cls, row: Any) -> dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def _default_order_by(cls):
        return (cls.model.id.asc(),)

    @classmethod
    def list_definitions(
        cls,
        db: Session,
        **filters: Any,
    ) -> list[dict[str, Any]]:
        """Generic list with optional keyword filters.

        Each filter kwarg maps to a column on cls.model; if the value is not
        None, a `WHERE col == value` clause is added.
        """
        query = db.query(cls.model)
        for col_name, val in filters.items():
            if val is not None:
                col = getattr(cls.model, col_name)
                query = query.filter(col == val)
        rows = query.order_by(*cls._default_order_by()).all()
        return [cls._to_dict(row) for row in rows]
