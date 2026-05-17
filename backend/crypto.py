import hashlib
import hmac
import secrets
import base64

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .config import settings


def _derive(info: str) -> bytes:
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=None,
        info=info.encode(),
    )
    return hkdf.derive(bytes.fromhex(settings.secret_key))


_AES_KEY: bytes = _derive("aes-gcm-v1")
_HMAC_KEY: bytes = _derive("hmac-lookup-v1")

_argon2 = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

# Pre-computed hash used to keep login-miss timing indistinguishable from a hit (P2-12).
DUMMY_HASH: str = _argon2.hash("__dummy__")


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def verify_token(token: str, stored: str) -> bool:
    return secrets.compare_digest(hash_token(token), stored)


def hash_passphrase(passphrase: str) -> str:
    return _argon2.hash(passphrase)


def verify_passphrase(passphrase: str, stored: str) -> bool:
    try:
        return _argon2.verify(stored, passphrase)
    except VerifyMismatchError:
        return False


def hmac_username(username: str) -> str:
    msg = ("username:" + username.strip().lower()).encode()
    return hmac.new(_HMAC_KEY, msg, hashlib.sha256).hexdigest()


def hmac_name_in_event(name: str, event_id: str) -> str:
    msg = f"event:{event_id}:{name.strip().lower()}".encode()
    return hmac.new(_HMAC_KEY, msg, hashlib.sha256).hexdigest()


def encrypt(plaintext: str) -> str:
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(_AES_KEY)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt(blob: str) -> str:
    raw = base64.urlsafe_b64decode(blob.encode())
    nonce, ciphertext = raw[:12], raw[12:]
    aesgcm = AESGCM(_AES_KEY)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
