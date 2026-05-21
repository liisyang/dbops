from werkzeug.security import generate_password_hash

from app.models.user import User


def test_user_model_matches_dbops_users_schema_defaults():
    table = User.__table__

    assert table.c.username.type.length == 100
    assert table.c.email.type.length == 200
    assert table.c.department.type.length == 200
    assert table.c.role.type.length == 50
    assert table.c.role.default.arg == "admin"
    assert table.c.language.type.length == 20
    assert table.c.language.default.arg == "zh-CN"


def test_verify_password_supports_werkzeug_hash():
    pwd = "Unixadm88"
    user = User(password_hash=generate_password_hash(pwd))

    assert user.verify_password(pwd) is True
    assert user.verify_password("wrong-password") is False


def test_verify_password_supports_bcrypt_hash():
    import bcrypt

    pwd = "Unixadm88"
    hashed = bcrypt.hashpw(pwd.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = User(password_hash=hashed)

    assert user.verify_password(pwd) is True
    assert user.verify_password("wrong-password") is False


def test_verify_password_handles_invalid_hash_without_500():
    user = User(password_hash="$2b$broken-hash")

    assert user.verify_password("any") is False
