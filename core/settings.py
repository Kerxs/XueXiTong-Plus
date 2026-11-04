"""Checks before 开始运行 and in the first-run guide, with the same wording on both apps.

``values`` uses the settings ids of ui/advanced.py ("section.key"), plus
common.username / common.password / common.use_cookies.
"""

from __future__ import annotations

from pathlib import Path

from ui import advanced, cloudmodels

ACCOUNT_MISSING = "还没有填写账号和密码"
ACCOUNT_HINT = "请在设置中填写账号和密码，或开启 cookies 登录"
COOKIES_MISSING = "开启了 cookies 登录，但还没有 cookies.txt"
CLOUD_PROVIDER_MISSING = "答题方式用到了 AI，请先选择模型服务商"
AI_KEY_MISSING = "答题方式用到了 AI，但还没填写 API Key"


def _on(value) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes", "on")


def account_problem(values: dict, data_dir: Path | None = None) -> str:
    """"" when the account (or cookies login) is usable."""
    if _on(values.get("common.use_cookies", "")):
        if data_dir is not None and not (Path(data_dir) / "cookies.txt").exists():
            return COOKIES_MISSING
        return ""
    if not str(values.get("common.username", "")).strip() or not values.get("common.password"):
        return f"{ACCOUNT_MISSING}。{ACCOUNT_HINT}"
    return ""


def _cloud_problem(values: dict) -> str:
    picked = [p.strip() for p in str(values.get("tiku.provider", "")).split(",")]
    if "AI" not in picked:
        return ""
    endpoints = [p["endpoint"] for p in cloudmodels.PROVIDERS]
    if str(values.get("tiku.endpoint", "")).strip() not in endpoints:
        return CLOUD_PROVIDER_MISSING
    if not str(values.get("tiku.key", "")).strip():
        return AI_KEY_MISSING
    return ""


def start_problem(values: dict, data_dir: Path | None = None, cloud_only: bool = False) -> str:
    """Why 开始运行 cannot start yet ("" = can start). cloud_only: the phone (no local models)."""
    problem = account_problem(values, data_dir)
    if problem:
        return problem
    if cloud_only:
        problem = _cloud_problem(values)
        if problem:
            return problem
    return advanced.ai_config_problem(values)


def guide_problem(values: dict, cloud_only: bool = False) -> str:
    """The guide's 答题来源 step: also requires the 题库 token / address (desktop answerSetupProblem)."""
    if cloud_only:
        problem = _cloud_problem(values)
        if problem:
            return problem
    return advanced.answer_setup_problem(values)
