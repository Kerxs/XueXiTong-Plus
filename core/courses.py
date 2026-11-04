"""识别课程: log in with the saved account and read the course list (no question bank, no tasks)."""

from __future__ import annotations

from core.settings import ACCOUNT_MISSING

COURSE_KEYS = ("courseId", "clazzId", "title", "teacher", "desc")


def list_courses(config_path) -> dict:
    """{"ok": True, "courses": [...]} or {"ok": False, "error": "...", "code": n}.

    code: 3 = account not filled in, 1 = login / network failure (worker.py exit codes).
    Runs in the current working directory (cookies.txt and logs live there).
    """
    from main import load_config_from_file
    from api.base import Account, Chaoxing

    try:
        common, _tiku, _notify = load_config_from_file(str(config_path))
    except Exception as exc:
        return {"ok": False, "error": f"配置文件无法读取：{exc}", "code": 1}
    use_cookies = bool(common.get("use_cookies", False))
    username, password = common.get("username", ""), common.get("password", "")
    if not use_cookies and (not username or not password or username.lower() == "xxx"):
        return {"ok": False, "error": ACCOUNT_MISSING, "code": 3}
    try:
        chaoxing = Chaoxing(account=Account(username, password))
        state = chaoxing.login(login_with_cookies=use_cookies)
        if not state.get("status"):
            return {"ok": False, "error": f"登录失败：{state.get('msg') or '未知原因'}", "code": 1}
        courses = chaoxing.get_course_list()
    except Exception as exc:  # network / parsing problems are reported, not raised
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "code": 1}
    return {"ok": True, "courses": [{k: str(c.get(k, "") or "") for k in COURSE_KEYS} for c in courses]}
