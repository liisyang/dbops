"""
密码服务 - 哈希和随机密码生成。
使用 sha512_crypt（等价 openssl passwd -6），兼容 chpasswd -e。
"""
import random
import secrets
import string

from passlib.hash import sha512_crypt


def hash_password(plaintext: str) -> str:
    """
    使用 SHA512 crypt 哈希密码（等价 openssl passwd -6）。

    Args:
        plaintext: 明文密码

    Returns:
        哈希后的密码字符串
    """
    return sha512_crypt.hash(plaintext)


def verify_password(plaintext: str, hash_str: str) -> bool:
    """
    验证密码是否匹配哈希。

    Args:
        plaintext: 明文密码
        hash_str: 哈希字符串

    Returns:
        True if match, False otherwise
    """
    return sha512_crypt.verify(plaintext, hash_str)


def generate_password(length: int = 12) -> str:
    """
    生成随机密码（字母+数字）。

    Args:
        length: 密码长度，默认 12

    Returns:
        随机密码字符串
    """
    if length < 12:
        raise ValueError("密码长度至少为 12")

    # 确保至少包含一个字母和一个数字
    letters = string.ascii_letters
    digits = string.digits
    chars = letters + digits

    # 先生成必填字符，剩余随机填充
    password = [
        secrets.choice(letters),
        secrets.choice(digits),
    ]
    password += [secrets.choice(chars) for _ in range(length - 2)]

    # 随机打乱顺序
    random.shuffle(password)
    return ''.join(password)
