# -*- coding: utf-8 -*-
import os.path
import threading

import requests

from api.config import GlobalConst as gc

# 定义全局 Cookie 文件锁，保证读写绝对安全
cookie_lock = threading.RLock()


def save_cookies(session: requests.Session):
    """登录后的 cookies 加密保存（core/secret.py），只有本机当前用户 / 本应用能读回。"""
    from core import secret

    with cookie_lock:
        buffer = ""
        for k, v in session.cookies.items():
            buffer += f"{k}={v};"
        buffer = buffer.removesuffix(";")
        secret.write_text(gc.COOKIES_PATH, buffer)


def use_cookies() -> dict:
    with cookie_lock:
        if not os.path.exists(gc.COOKIES_PATH):
            return {}

        from core import secret

        cookies = {}
        try:
            with open(gc.COOKIES_PATH, "r", encoding="utf-8") as f:
                stored = f.read().strip()
            buffer = secret.read_text(gc.COOKIES_PATH)
            if not buffer:
                return {}
            if stored and not secret.is_protected(stored) and secret.available():
                # 用户放入 / 导入的明文 cookies.txt：读到后改为加密保存
                secret.write_text(gc.COOKIES_PATH, buffer)
            for item in buffer.split(";"):
                item = item.strip()
                if not item:
                    continue
                parts = item.split("=", 1)
                if len(parts) == 2:
                    cookies[parts[0]] = parts[1]
        except Exception:
            return {}

        return cookies
