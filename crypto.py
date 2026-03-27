from __future__ import annotations

import logging
import os
from cryptography.fernet import Fernet

from config import ENV_PATH

logger = logging.getLogger(__name__)

_KEY_ENV = "ENCRYPT_KEY"
_fernet: Fernet | None = None


def init_encryption() -> None:
    """Must be called once at startup, after load_dotenv()."""
    global _fernet
    raw = os.getenv(_KEY_ENV, "")

    if raw:
        _fernet = Fernet(raw.encode())
        logger.info("ENCRYPT_KEY загружен из .env")
        return

    key = Fernet.generate_key()
    _fernet = Fernet(key)
    key_str = key.decode()

    os.environ[_KEY_ENV] = key_str

    try:
        content = ""
        if ENV_PATH.exists():
            content = ENV_PATH.read_text(encoding="utf-8")
        if _KEY_ENV not in content:
            with ENV_PATH.open("a", encoding="utf-8") as f:
                if content and not content.endswith("\n"):
                    f.write("\n")
                f.write(f"{_KEY_ENV}={key_str}\n")
            logger.info("ENCRYPT_KEY сгенерирован и записан в %s", ENV_PATH)
        else:
            logger.info("ENCRYPT_KEY уже есть в файле")
    except OSError as e:
        logger.error("Не удалось записать ENCRYPT_KEY в %s: %s", ENV_PATH, e)


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
