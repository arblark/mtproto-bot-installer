import os
import base64
from cryptography.fernet import Fernet

_KEY_ENV = "ENCRYPT_KEY"
_key: bytes | None = None


def _get_key() -> bytes:
    global _key
    if _key:
        return _key

    raw = os.getenv(_KEY_ENV, "")
    if raw:
        _key = raw.encode()
    else:
        _key = Fernet.generate_key()
        _write_key_to_env(_key.decode())

    return _key


def _write_key_to_env(key_str: str) -> None:
    """Append ENCRYPT_KEY to .env if missing."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    try:
        content = ""
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                content = f.read()

        if _KEY_ENV not in content:
            with open(env_path, "a", encoding="utf-8") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write(f"{_KEY_ENV}={key_str}\n")
    except OSError:
        pass


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    f = Fernet(_get_key())
    return f.encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    f = Fernet(_get_key())
    return f.decrypt(token.encode("ascii")).decode("utf-8")
