"""从本机 Chrome / Edge 读取智慧树登录 Cookie。

只读取 zhihuishu.com。浏览器正在占用数据库、或使用了读不出来的新加密时，返回空字符串，
交给软件里的登录窗口处理。
"""

import base64
import json
import os
import shutil
import sqlite3
import tempfile
from ctypes import (
    POINTER,
    Structure,
    WinDLL,
    byref,
    c_char,
    c_longlong,
    cast,
    create_string_buffer,
    string_at,
    windll,
    wintypes,
)
from pathlib import Path

from Crypto.Cipher import AES

AUTH_NAMES = {"CASTGC", "jt-cas"}


class DATA_BLOB(Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", POINTER(c_char))]


def _dpapi_decrypt(data):
    buffer = create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), cast(buffer, POINTER(c_char)))
    blob_out = DATA_BLOB()
    if not windll.crypt32.CryptUnprotectData(byref(blob_in), None, None, None, None, 0, byref(blob_out)):
        return None
    try:
        return string_at(blob_out.pbData, blob_out.cbData)
    finally:
        windll.kernel32.LocalFree(blob_out.pbData)


def _copy_db(src):
    kernel = WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel.CreateFileW.restype = wintypes.HANDLE
    handle = kernel.CreateFileW(str(src), 0x80000000, 0x1 | 0x2 | 0x4, None, 3, 0, None)
    if not handle or handle == wintypes.HANDLE(-1).value:
        return None
    file_size = c_longlong()
    if not kernel.GetFileSizeEx(handle, byref(file_size)) or file_size.value <= 0:
        kernel.CloseHandle(handle)
        return None
    buf = create_string_buffer(file_size.value)
    read = wintypes.DWORD()
    ok = kernel.ReadFile(handle, buf, file_size.value, byref(read), None)
    kernel.CloseHandle(handle)
    if not ok or read.value <= 0:
        return None
    tmp = Path(tempfile.mkdtemp()) / "Cookies"
    tmp.write_bytes(buf.raw[: read.value])
    return tmp


def _decrypt_value(encrypted, key):
    if not encrypted:
        return ""
    prefix = encrypted[:3]
    if prefix in (b"v10", b"v11"):
        nonce = encrypted[3:15]
        body = encrypted[15:]
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(body[:-16], body[-16:]).decode("utf-8", "replace")
    if prefix == b"v20":
        return None
    plain = _dpapi_decrypt(encrypted)
    if plain is None:
        return None
    return plain.decode("utf-8", "replace")


def _aes_key(user_data):
    state_path = user_data / "Local State"
    if not state_path.exists():
        return None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    raw = base64.b64decode(state["os_crypt"]["encrypted_key"])
    if raw.startswith(b"DPAPI"):
        raw = raw[5:]
    return _dpapi_decrypt(raw)


def _profiles(user_data):
    if not user_data.exists():
        return
    for profile in user_data.iterdir():
        if not profile.is_dir():
            continue
        for name in ("Network/Cookies", "Cookies"):
            path = profile / name
            if path.is_file():
                yield path


def _read_db(db_path, key):
    copied = _copy_db(db_path)
    if copied is None:
        return {}
    try:
        con = sqlite3.connect(copied)
        rows = con.execute(
            "select host_key, name, encrypted_value from cookies where host_key like ?",
            ("%zhihuishu%",),
        ).fetchall()
    finally:
        shutil.rmtree(copied.parent, ignore_errors=True)
    found = {}
    for _host, name, encrypted in rows:
        value = _decrypt_value(encrypted, key)
        if not value:
            continue
        found[name] = value
    return found


def _from_rookie():
    try:
        import rookiepy
    except ImportError:
        return {}
    found = {}
    for func in (getattr(rookiepy, "chrome", None), getattr(rookiepy, "edge", None)):
        if func is None:
            continue
        try:
            cookies = func(["zhihuishu.com"])
        except Exception:
            continue
        for item in cookies or []:
            name = item.get("name")
            value = item.get("value")
            if name and value:
                found[name] = value
    return found


def read_browser_cookie():
    merged = _from_rookie()
    if not AUTH_NAMES.intersection(merged):
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        roots = [
            local / "Google/Chrome/User Data",
            local / "Microsoft/Edge/User Data",
        ]
        for root in roots:
            key = _aes_key(root)
            if not key:
                continue
            for db_path in _profiles(root):
                try:
                    merged.update(_read_db(db_path, key))
                except Exception:
                    continue
    if not AUTH_NAMES.intersection(merged):
        return ""
    return "; ".join(f"{name}={value}" for name, value in merged.items())
