"""Account data at rest: secrets in config.ini and the saved cookies are stored encrypted.

Stored form: ``enc:v1:<base64>``. Anything without that prefix is read as plain text (configs
from older versions, values typed into config.ini by hand) and is encrypted the next time the
file is written.

Backends:
* Windows - DPAPI (CryptProtectData, current user): only this Windows account on this computer
  can read the values back. The desktop GUI and its worker run as the same user.
* Android - a random data key kept wrapped by the Android Keystore; the app passes it to Python
  through ``XXTPLUS_DATA_KEY`` (hex). AES-256-CTR + HMAC-SHA256 (encrypt-then-MAC).
* Neither available (the command line on Linux / macOS) - values stay plain text, as before.

A value that cannot be decrypted (config copied from another computer or account) reads as
empty, so the user is asked to fill it in again instead of logging in with garbage.
"""

from __future__ import annotations

import base64
import configparser
import hashlib
import hmac
import os
import sys
import tempfile

PREFIX = "enc:v1:"
KEY_ENV = "XXTPLUS_DATA_KEY"
_ENTROPY = b"XueXiTongPlus/config"

# Account and service credentials in config.ini.
SECRET_KEYS: dict[str, tuple[str, ...]] = {
    "common": ("username", "password"),
    "tiku": ("tokens", "key", "siliconflow_key", "vision_key", "backup_providers"),
    "notification": ("url", "tg_chat_id"),
}


class SecretError(Exception):
    """A stored value could not be decrypted (other computer / account, or damaged)."""


# ------------------------------------------------------------------ backends

def _dpapi(data: bytes, protect: bool) -> bytes:
    import ctypes
    from ctypes import wintypes

    class Blob(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    def blob(raw: bytes) -> Blob:
        buf = ctypes.create_string_buffer(raw, len(raw))
        return Blob(len(raw), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    source, entropy, out = blob(data), blob(_ENTROPY), Blob()
    flags = 0x1  # CRYPTPROTECT_UI_FORBIDDEN
    fn = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(source), None, ctypes.byref(entropy), None, None, flags, ctypes.byref(out))
    if not ok:
        raise SecretError(f"DPAPI error {ctypes.GetLastError()}")
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel32.LocalFree(out.pbData)


def _env_key() -> bytes | None:
    raw = os.environ.get(KEY_ENV, "").strip()
    if not raw:
        return None
    try:
        key = bytes.fromhex(raw)
    except ValueError:
        return None
    return key if len(key) == 32 else None


def _ctr(key: bytes, nonce: bytes, data: bytes) -> bytes:
    import pyaes

    counter = pyaes.Counter(initial_value=int.from_bytes(nonce, "big"))
    return pyaes.AESModeOfOperationCTR(key, counter=counter).encrypt(data)


def _keyed_protect(key: bytes, data: bytes) -> bytes:
    enc_key, mac_key = hashlib.sha256(key + b"enc").digest(), hashlib.sha256(key + b"mac").digest()
    nonce = os.urandom(16)
    body = nonce + _ctr(enc_key, nonce, data)
    return body + hmac.new(mac_key, body, hashlib.sha256).digest()


def _keyed_unprotect(key: bytes, data: bytes) -> bytes:
    enc_key, mac_key = hashlib.sha256(key + b"enc").digest(), hashlib.sha256(key + b"mac").digest()
    if len(data) < 48:
        raise SecretError("too short")
    body, tag = data[:-32], data[-32:]
    if not hmac.compare_digest(tag, hmac.new(mac_key, body, hashlib.sha256).digest()):
        raise SecretError("wrong key or damaged value")
    return _ctr(enc_key, body[:16], body[16:])


def backend() -> str:
    """"key" (Android data key), "dpapi" (Windows) or "" (plain text)."""
    if _env_key() is not None:
        return "key"
    if sys.platform == "win32":
        return "dpapi"
    return ""


def available() -> bool:
    return backend() != ""


# ------------------------------------------------------------------ values

def is_protected(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def protect(value: str) -> str:
    """Encrypt one value (empty stays empty; no backend = unchanged)."""
    if not value or is_protected(value):
        return value
    kind = backend()
    data = value.encode("utf-8")
    if kind == "key":
        raw = _keyed_protect(_env_key(), data)  # type: ignore[arg-type]
    elif kind == "dpapi":
        raw = _dpapi(data, True)
    else:
        return value
    return PREFIX + base64.b64encode(raw).decode("ascii")


def unprotect(value: str) -> str:
    """Decrypt one value; plain text is returned as is. Raises SecretError if it cannot be read."""
    if not is_protected(value):
        return value
    try:
        raw = base64.b64decode(value[len(PREFIX):], validate=True)
    except ValueError as exc:
        raise SecretError("damaged value") from exc
    kind = backend()
    if kind == "key":
        data = _keyed_unprotect(_env_key(), raw)  # type: ignore[arg-type]
    elif kind == "dpapi":
        data = _dpapi(raw, False)
    else:
        raise SecretError("no key on this system")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SecretError("damaged value") from exc


def reveal(value: str) -> str:
    """unprotect(), but a value that cannot be read becomes "" (asks the user to fill it in again)."""
    try:
        return unprotect(value)
    except SecretError:
        return ""


# ------------------------------------------------------------------ config.ini

def is_secret(section: str, key: str) -> bool:
    return key.lower() in SECRET_KEYS.get(section, ())


def decrypt_config(config: configparser.ConfigParser) -> list[str]:
    """Decrypt the secret fields in place. Returns "section.key" of values that could not be read."""
    unreadable = []
    for section, keys in SECRET_KEYS.items():
        if not config.has_section(section):
            continue
        for key in keys:
            value = config.get(section, key, raw=True, fallback=None)
            if value is None or not is_protected(value):
                continue
            try:
                config.set(section, key, unprotect(value))
            except SecretError:
                config.set(section, key, "")
                unreadable.append(f"{section}.{key}")
    return unreadable


def read_config(path) -> configparser.ConfigParser:
    """ConfigParser.read() with the secret fields decrypted.

    No interpolation: a "%" in a password or API key is just a character (with the default
    interpolation such a value used to make reading the config fail).
    """
    config = configparser.ConfigParser(interpolation=None)
    config.read(path, encoding="utf-8")
    decrypt_config(config)
    return config


def encrypted_copy(config: configparser.ConfigParser) -> configparser.ConfigParser:
    out = configparser.ConfigParser(interpolation=None)
    for section in config.sections():
        out.add_section(section)
        for key, value in config.items(section, raw=True):
            out.set(section, key, protect(value) if is_secret(section, key) else value)
    return out


def write_config(config: configparser.ConfigParser, path) -> None:
    """Write config.ini with the secret fields encrypted (atomic: temp file + replace)."""
    path = os.fspath(path)
    folder = os.path.dirname(path) or "."
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".tmp", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            encrypted_copy(config).write(fh)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


def needs_migration(path) -> bool:
    """True when config.ini still has plain-text secrets that this system could encrypt."""
    if not available() or not os.path.exists(path):
        return False
    raw = configparser.ConfigParser(interpolation=None)
    try:
        raw.read(path, encoding="utf-8")
    except configparser.Error:
        return False
    for section, keys in SECRET_KEYS.items():
        for key in keys:
            value = raw.get(section, key, raw=True, fallback="") if raw.has_section(section) else ""
            if value and value.strip().lower() not in ("xxx", "xxxxxx") and not is_protected(value):
                return True
    return False


def migrate(path) -> bool:
    """Encrypt the plain-text secrets of an existing config.ini (keeps every other line's value)."""
    if not needs_migration(path):
        return False
    config = configparser.ConfigParser(interpolation=None)
    config.read(path, encoding="utf-8")
    decrypt_config(config)
    write_config(config, path)
    return True


# ------------------------------------------------------------------ files (cookies)

def write_text(path, text: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(protect(text) if text else text)


def read_text(path) -> str:
    """File content, decrypted if it was stored encrypted ("" if it cannot be read)."""
    with open(path, "r", encoding="utf-8") as fh:
        content = fh.read().strip()
    return reveal(content)
