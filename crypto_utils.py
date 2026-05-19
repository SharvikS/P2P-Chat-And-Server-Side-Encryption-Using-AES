from pathlib import Path
from cryptography.fernet import Fernet
import config as cfg


def load_or_generate_key() -> bytes:
    path = Path(cfg.KEY_FILE)
    if path.exists():
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    path.write_bytes(key)
    print(f"[KEY] New encryption key saved → {cfg.KEY_FILE}")
    return key


def get_cipher() -> Fernet:
    return Fernet(load_or_generate_key())


def encrypt_bytes(cipher: Fernet, data: bytes) -> bytes:
    return cipher.encrypt(data)


def decrypt_bytes(cipher: Fernet, data: bytes) -> bytes:
    return cipher.decrypt(data)
