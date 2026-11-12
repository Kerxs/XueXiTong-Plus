"""AI 答题的服务商列表：首选（`[tiku] endpoint / key / model`）加上按顺序排列的备用服务商。

答题时先用首选；它出错（连不上、超时、Key 无效、没有权限、额度不足、服务端故障）就按顺序换下一个
（`api/answer.AI`）。备用服务商存在 `[tiku] backup_providers`：JSON 列表 `[{"endpoint", "key",
"model"}]`，整个字段和其他密钥一样加密保存（`core/secret.SECRET_KEYS`）。

两端共用，不依赖 Qt / 安卓。
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

FIELD = "tiku.backup_providers"
CONFIG_KEY = "backup_providers"
MAX_BACKUPS = 8


def _clean(entry) -> dict | None:
    if not isinstance(entry, dict):
        return None
    endpoint = str(entry.get("endpoint", "") or "").strip().rstrip("/")
    model = str(entry.get("model", "") or "").strip()
    key = str(entry.get("key", "") or "").strip()
    if not endpoint:
        return None
    return {"endpoint": endpoint, "key": key, "model": model}


def parse(text) -> list[dict]:
    """The stored list; anything unreadable is left out (never raises)."""
    if isinstance(text, list):
        raw = text
    else:
        try:
            raw = json.loads(str(text or "").strip() or "[]")
        except (TypeError, ValueError):
            return []
    if not isinstance(raw, list):
        return []
    found = []
    for entry in raw:
        item = _clean(entry)
        if item is not None:
            found.append(item)
    return found[:MAX_BACKUPS]


def dump(entries: list[dict]) -> str:
    clean = [e for e in (_clean(x) for x in entries) if e is not None][:MAX_BACKUPS]
    return json.dumps(clean, ensure_ascii=False, separators=(",", ":")) if clean else ""


def is_local(endpoint: str) -> bool:
    try:
        host = (urlsplit(str(endpoint).strip()).hostname or "").lower()
    except ValueError:
        return False
    return host in ("localhost", "::1") or host.startswith("127.")


def problem(endpoint: str, key: str, model: str, cloud_only: bool = False) -> str:
    """Why one service entry cannot work ("" when it looks usable). ``cloud_only``: the phone, which
    only talks to the model companies' cloud services (https, not this device)."""
    endpoint = str(endpoint or "").strip()
    if not endpoint:
        return "还没选择服务商（接口地址）"
    if not endpoint.lower().startswith(("http://", "https://")):
        return "接口地址要以 http:// 或 https:// 开头"
    if endpoint.rstrip("/").lower().endswith("/chat/completions"):
        return "接口地址不要带 /chat/completions，填到 /v1 即可"
    if cloud_only and (not endpoint.lower().startswith("https://") or is_local(endpoint)):
        return "手机上只能使用 https 开头的云端服务"
    if not str(model or "").strip():
        return "还没填写模型名称"
    if not str(key or "").strip() and not is_local(endpoint):
        return "还没填写 API Key"
    return ""


def list_problem(text, cloud_only: bool = False) -> str:
    """The first unusable backup, as a sentence for the settings check ("" when all are usable)."""
    for n, entry in enumerate(parse(text), 1):
        reason = problem(entry["endpoint"], entry["key"], entry["model"], cloud_only)
        if reason:
            return f"备用服务商 {n}：{reason}"
    return ""


def profiles(conf) -> list[dict]:
    """Every service in the order it is tried: the primary first, then the backups. ``conf`` is the
    ``[tiku]`` section (any mapping). Duplicates (same address and model) are left out."""
    primary = {"endpoint": str(conf.get("endpoint", "") or "").strip(),
               "key": str(conf.get("key", "") or "").strip(),
               "model": str(conf.get("model", "") or "").strip()}
    found, seen = [], set()
    for entry in [primary, *parse(conf.get(CONFIG_KEY, ""))]:
        mark = (entry["endpoint"].rstrip("/").lower(), entry["model"])
        if not entry["endpoint"] or mark in seen:
            continue
        seen.add(mark)
        found.append(entry)
    return found or [primary]


# ---------------------------------------------------------------- editing (settings screens)

def save(text, index: int, endpoint: str, key: str, model: str) -> list[dict]:
    """Add (index < 0 or past the end) or replace one backup."""
    entries = parse(text)
    item = {"endpoint": str(endpoint or "").strip().rstrip("/"), "key": str(key or "").strip(),
            "model": str(model or "").strip()}
    if 0 <= index < len(entries):
        entries[index] = item
    elif len(entries) < MAX_BACKUPS:
        entries.append(item)
    return entries


def remove(text, index: int) -> list[dict]:
    entries = parse(text)
    if 0 <= index < len(entries):
        del entries[index]
    return entries


def move(text, index: int, delta: int) -> list[dict]:
    entries = parse(text)
    target = index + delta
    if 0 <= index < len(entries) and 0 <= target < len(entries):
        entries[index], entries[target] = entries[target], entries[index]
    return entries


def promote(text, index: int, primary: dict) -> tuple[dict, list[dict]]:
    """Make a backup the primary: it and the current primary swap places. Returns (new primary,
    new backups)."""
    entries = parse(text)
    if not 0 <= index < len(entries):
        return primary, entries
    chosen = entries[index]
    old = _clean(primary)
    if old is not None:
        entries[index] = old
    else:
        del entries[index]
    return chosen, entries
