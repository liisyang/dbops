from __future__ import annotations

import hashlib
from typing import Any

from sqlalchemy.orm import Session

from app.models.dbops_assets import BusinessSystemContact, Contact


def _make_contact_code(seed: str) -> str:
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest().upper()
    return f"CT-{digest[:12]}"


class DbopsContactService:
    @staticmethod
    def list_contacts(db: Session) -> list[dict[str, Any]]:
        contacts = sorted(
            db.query(Contact).all(),
            key=lambda row: (str(getattr(row, "contact_name", "") or ""), getattr(row, "id", 0) or 0),
        )
        return [
            {
                "id": row.id,
                "employee_no": row.employee_no,
                "contact_code": row.contact_code,
                "contact_name": row.contact_name,
                "phone": row.phone,
                "email": row.email,
                "dept": row.dept,
                "remark": row.remark,
            }
            for row in contacts
        ]

    @staticmethod
    def upsert_contact(
        db: Session,
        payload: dict[str, Any],
        contact_id: int | None = None,
    ) -> Contact:
        employee_no = str(payload.get("employee_no") or "").strip() or None
        contact_name = str(payload.get("contact_name") or "").strip()
        phone = str(payload.get("phone") or "").strip() or None
        email = str(payload.get("email") or "").strip().lower() or None
        dept = str(payload.get("dept") or "").strip() or None
        remark = str(payload.get("remark") or "").strip() or None

        if not contact_name:
            raise ValueError("contact_name is required")

        contact = None
        if contact_id is not None:
            contact = db.query(Contact).filter(Contact.id == contact_id).first()
        else:
            if employee_no:
                contact = db.query(Contact).filter_by(employee_no=employee_no).first()
            if not contact and email:
                contact = db.query(Contact).filter_by(email=email).first()
            if not contact and phone:
                contact = db.query(Contact).filter_by(phone=phone).first()
            if not contact:
                contact = db.query(Contact).filter_by(contact_name=contact_name).first()

        if not contact:
            seed = "|".join([employee_no or "", email or "", phone or "", contact_name])
            contact = Contact(
                employee_no=employee_no,
                contact_code=_make_contact_code(seed),
                contact_name=contact_name,
                phone=phone,
                email=email,
                dept=dept,
                remark=remark,
            )
            db.add(contact)
            db.flush()
            db.commit()
            return contact

        contact.employee_no = employee_no
        contact.contact_name = contact_name
        contact.phone = phone
        contact.email = email
        contact.dept = dept
        contact.remark = remark
        db.commit()
        return contact

    @staticmethod
    def delete_contact(db: Session, contact_id: int) -> bool:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            return False
        linked_count = (
            db.query(BusinessSystemContact)
            .filter(BusinessSystemContact.contact_id == contact_id)
            .count()
        )
        if linked_count:
            raise ValueError("contact is still linked to business systems")
        db.delete(contact)
        db.commit()
        return True
