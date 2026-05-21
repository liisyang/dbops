from app.models.dbops_assets import BusinessSystemContact, Contact
from app.services.dbops_contact_service import DbopsContactService


class _FakeQuery:
    def __init__(self, session, model):
        self.session = session
        self.model = model
        self.filters = {}

    def filter_by(self, **kwargs):
        self.filters.update(kwargs)
        return self

    def filter(self, *conditions):
        for condition in conditions:
            if hasattr(condition, "left") and hasattr(condition, "right") and getattr(condition.operator, "__name__", "") == "eq":
                key = getattr(condition.left, "key", None)
                value = getattr(condition.right, "value", None)
                if key is not None:
                    self.filters[key] = value
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def _rows(self):
        rows = self.session.store.get(self.model, [])
        for key, value in self.filters.items():
            rows = [row for row in rows if getattr(row, key) == value]
        return rows

    def first(self):
        rows = self._rows()
        return rows[0] if rows else None

    def all(self):
        return list(self._rows())

    def count(self):
        return len(self._rows())


class _FakeSession:
    def __init__(self):
        self.store = {}
        self._next_ids = {}

    def seed(self, *objects):
        for obj in objects:
            self._ensure_identity(obj)
            self.store.setdefault(type(obj), []).append(obj)

    def query(self, model):
        return _FakeQuery(self, model)

    def add(self, obj):
        self._ensure_identity(obj)
        self.store.setdefault(type(obj), []).append(obj)

    def flush(self):
        return None

    def commit(self):
        return None

    def delete(self, obj):
        rows = self.store.get(type(obj), [])
        if obj in rows:
            rows.remove(obj)

    def _ensure_identity(self, obj):
        if getattr(obj, "id", None) is None:
            model = type(obj)
            next_id = self._next_ids.get(model, 1)
            obj.id = next_id
            self._next_ids[model] = next_id + 1


def test_list_contacts_returns_sorted_master_data():
    db = _FakeSession()
    db.seed(
        Contact(
            id=2,
            employee_no="E002",
            contact_code="CT-002",
            contact_name="王五",
            phone="13900000002",
            email="wangwu@example.com",
            dept="DBA",
        ),
        Contact(
            id=1,
            employee_no="E001",
            contact_code="CT-001",
            contact_name="张三",
            phone="13900000001",
            email="zhangsan@example.com",
            dept="应用部",
        ),
    )

    rows = DbopsContactService.list_contacts(db)

    assert [row["contact_name"] for row in rows] == ["张三", "王五"]


def test_upsert_contact_creates_updates_and_deletes():
    db = _FakeSession()

    created = DbopsContactService.upsert_contact(
        db,
        {
            "employee_no": "E001",
            "contact_name": "张三",
            "phone": "13800000000",
            "email": "zhangsan@example.com",
            "dept": "DBA",
            "remark": "core owner",
        },
    )

    assert created.id == 1
    assert created.contact_code.startswith("CT-")
    assert created.contact_name == "张三"

    updated = DbopsContactService.upsert_contact(
        db,
        {
            "employee_no": "E001",
            "contact_name": "张三",
            "phone": "13900000000",
            "email": "zhangsan@example.com",
            "dept": "平台部",
            "remark": "updated",
        },
        contact_id=created.id,
    )

    assert updated.id == created.id
    assert updated.phone == "13900000000"
    assert updated.dept == "平台部"
    assert updated.remark == "updated"

    deleted = DbopsContactService.delete_contact(db, created.id)
    assert deleted is True
    assert db.store.get(Contact, []) == []


def test_delete_contact_rejects_bound_master_data():
    db = _FakeSession()
    contact = Contact(
        id=1,
        employee_no="E001",
        contact_code="CT-001",
        contact_name="张三",
        phone="13800000000",
        email="zhangsan@example.com",
        dept="DBA",
    )
    link = BusinessSystemContact(id=2, business_system_id=10, contact_id=1, role_code="DBA_OWNER")
    db.seed(contact, link)

    try:
        DbopsContactService.delete_contact(db, contact.id)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "linked to business systems" in str(exc)
