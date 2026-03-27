from __future__ import annotations

import os
from pathlib import Path
from cryptography.fernet import Fernet

_KEY_ENV = "ENCRYPT_KEY"
_fernet: Fernet | None = None

_BASE_DIR = Path(__file__).resolve().parent
_ENV_PATH = _BASE_DIR / ".env"


def init_encryption() -> None:
    """Must be called once at startup, after load_dotenv()."""
    global _fernet
    raw = os.getenv(_KEY_ENV, "")

    if raw:
        _fernet = Fernet(raw.encode())
        return

    key = Fernet.generate_key()
    _fernet = Fernet(key)

    os.environ[_KEY_ENV] = key.decode()

    try:
        content = ""
        if _ENV_PATH.exists():
            content = _ENV_PATH.read_text(encoding="utf-8")
        if _KEY_ENV not in content:
            with _ENV_PATH.open("a", encoding="utf-8") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write(f"{_KEY_ENV}={key.decode()}\n")
    except OSError:
        pass


def _get_fernet() -> Fernet:
    if _fernet is None:
        init_encryption()
    return _fernet


def encrypt(plaintext: str) -> str:
    if not plaintext:
        return ""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    if not token:
        return ""
    return _get_fernet().decrypt(token.encode("ascii")).decode("utf-8")
