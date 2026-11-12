# -*- coding: utf-8 -*-
"""作业 (the course's 作业 tab) and 课堂活动 (随堂练习 / 任务): found outside the chapters.

作业 (checked against a real account, Nov 2026):
* the course page ``mooc2-ans/mycourse/stu`` (reached through ``visit/stucoursemiddle``) has the
  hidden fields ``workEnc`` and ``cpi``;
* the list is ``mooc1.chaoxing.com/mooc2/work/list?courseId&classId&cpi&ut=s&enc=<workEnc>``;
  every entry is ``<li data="…/mooc-ans/mooc2/work/task?…&workId&answerId&enc">`` with the title in
  ``p.overHidden2`` and the state in ``p.status`` (已完成 / 未交 / …); an empty list says 暂无作业.
* the answer page is read the same way as a 章节检测 page: every question has a hidden
  ``answertype<id>`` field, which is how questions are found whatever the page layout; the
  answers are filled by ``Chaoxing._fill_answers`` and sent by ``Chaoxing._post_work_form``
  (pyFlag "" = submit, "1" = save only), exactly like a 章节检测.

课堂活动 (``mobilelearn …/active/student/activelist``): activeType 42 is a 随堂练习 (open for a few
minutes in class), 35 a 任务 (handing in your own work). Neither can be answered from here yet:
open ones are announced at once (log, push, the app's 需要手动完成 list).
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup

from api import manual, pause
from api.logger import logger

COURSE_PAGE = "https://mooc1.chaoxing.com/visit/stucoursemiddle"
WORK_LIST = "https://mooc1.chaoxing.com/mooc2/work/list"
ACTIVE_LIST = "https://mobilelearn.chaoxing.com/v2/apis/active/student/activelist"

DONE_MARKS = ("已完成", "待批阅", "已批阅", "已交", "已提交", "互评")
CLOSED_MARKS = ("已截止", "已过期", "已结束", "已关闭")

QUIZ_TYPE = 42      # 随堂练习
TASK_TYPE = 35      # 任务（提交作品）

TYPE_CODES = {"0": "single", "1": "multiple", "2": "completion", "3": "judgement", "4": "shortanswer"}
TYPE_NAMES = {"单选": "0", "多选": "1", "填空": "2", "判断": "3"}
_TITLE_TAGS = re.compile(r"[（(]\s*(?:单选题|多选题|判断题|填空题|简答题|论述题|名词解释|计算题|问答题|其它|其他)[^)）]*[)）]")


@dataclass
class Homework:
    title: str
    status: str
    url: str
    params: dict = field(default_factory=dict)

    @property
    def done(self) -> bool:
        return any(mark in self.status for mark in DONE_MARKS)

    @property
    def closed(self) -> bool:
        return any(mark in self.status for mark in CLOSED_MARKS)

    @property
    def todo(self) -> bool:
        return not self.done and not self.closed


# ---------------------------------------------------------------- pages → data

def parse_course_page(html: str) -> dict:
    """Hidden fields of the course page (workEnc, cpi, courseid, clazzid…)."""
    soup = BeautifulSoup(html or "", "lxml")
    found = {}
    for tag in soup.find_all("input"):
        key = tag.get("id") or tag.get("name")
        if key and key not in found:
            found[key] = str(tag.get("value", "") or "")
    return found


def parse_work_list(html: str) -> list[Homework]:
    soup = BeautifulSoup(html or "", "lxml")
    items = []
    for li in soup.find_all("li"):
        url = li.get("data") or ""
        if "/work/" not in url:
            continue
        title_tag = li.find(class_="overHidden2") or li.find("p")
        status_tag = li.find(class_="status")
        label = (li.get("aria-label") or "").split(";")
        title = (title_tag.get_text(strip=True) if title_tag else "") or label[0].strip()
        status = (status_tag.get_text(strip=True) if status_tag else "") or (label[1].strip() if len(label) > 1 else "")
        params = {k: v[0] for k, v in parse_qs(urlsplit(url).query).items()}
        items.append(Homework(title=title, status=status, url=url, params=params))
    return items


def _clean_title(text: str) -> str:
    text = re.sub(r"[\r\n\t]", "", text or "").strip()
    text = re.sub(r"^\d+\s*[.、．]\s*", "", text)
    return _TITLE_TAGS.sub("", text).strip()


def _container(soup, input_tag, qid: str):
    for tag in soup.find_all(attrs={"data": qid}):
        if tag.name in ("div", "li", "section"):
            return tag
    parent = input_tag.find_parent(class_=re.compile(r"questionLi|singleQuesId|TiMu|question"))
    return parent or input_tag.find_parent("div")


def _options(box) -> str:
    lines = []
    for el in box.select(".answerBg, .answer_bg, ul li"):
        letter_tag = el.select_one(".num_option, .num_option_dx, span[data]")
        letter = ""
        if letter_tag is not None:
            letter = (letter_tag.get("data") or letter_tag.get_text(strip=True) or "").strip()[:1]
        text_tag = el.select_one(".answer_p, .after")
        text = (text_tag.get_text(" ", strip=True) if text_tag else el.get_text(" ", strip=True)) or ""
        text = re.sub(r"\s+", " ", text).strip()
        for img in el.find_all("img"):          # 图片选项：保留给看图答题
            if img.get("src"):
                text += f' <img src="{img["src"]}">'
        if letter and text.startswith(letter):
            text = text[1:].lstrip(" .、．")
        if not letter:
            m = re.match(r"^([A-Z])\s*[.、．]?\s*(.*)$", text)
            if not m:
                continue
            letter, text = m.group(1), m.group(2)
        line = f"{letter} {text}".strip()
        if line not in lines:
            lines.append(line)
    return "\n".join(sorted(lines))


def parse_work_page(html: str) -> dict:
    """An 作业 answer page → {"form": {...hidden fields}, "questions": [...]} like decode_questions_info.

    Questions are found by their hidden ``answertype<id>`` fields; a page without them (already
    handed in, closed, error) gives no questions.
    """
    from api.decode import FontDecoder

    soup = BeautifulSoup(html or "", "lxml")
    font = FontDecoder(html) if soup.find("style", id="cxSecretStyle") else None
    decode = (lambda s: font.decode(s)) if font else (lambda s: s)

    type_inputs = [tag for tag in soup.find_all("input") if re.fullmatch(r"answertype\d+", str(tag.get("name", "")))]
    form_tag = type_inputs[0].find_parent("form") if type_inputs else soup.find("form", id="submitForm")
    form = {}
    if form_tag is not None:
        for tag in form_tag.find_all("input"):
            name = str(tag.get("name") or "")
            if not name or name.startswith("answer") or name.startswith("answertype"):
                continue
            form[name] = str(tag.get("value", "") or "")

    questions = []
    for tag in type_inputs:
        qid = tag["name"][len("answertype"):]
        code = str(tag.get("value", "") or "")
        box = _container(soup, tag, qid)
        if box is None:
            continue
        if code not in TYPE_CODES:
            name = str(box.get("typename") or "")
            code = next((c for k, c in TYPE_NAMES.items() if k in name), "4")
        title_tag = box.select_one(".mark_name, .Zy_TItle, .qtContent, h3")
        title = _clean_title(decode(title_tag.get_text(" ", strip=True) if title_tag else box.get_text(" ", strip=True)[:200]))
        for img in (title_tag.find_all("img") if title_tag is not None else []):   # 题干图片
            if img.get("src"):
                title += f' <img src="{img["src"]}">'
        options = decode(_options(box)) if TYPE_CODES[code] in ("single", "multiple") else ""
        blanks = 0
        size = form_tag.find("input", attrs={"name": f"tiankongsize{qid}"}) if form_tag is not None else None
        if size is not None:
            try:
                blanks = int(size.get("value") or 0)
            except ValueError:
                blanks = 0
        questions.append({
            "id": qid,
            "title": title,
            "options": options,
            "type": TYPE_CODES[code],
            "blanks": blanks,
            "answerField": {f"answer{qid}": "", f"answertype{qid}": code},
        })
    return {"form": form, "questions": questions}


def build_form(page: dict, submit: bool) -> dict:
    """The POST body for _post_work_form after _fill_answers filled page["questions"]."""
    form = dict(page["form"])
    ids = []
    for q in page["questions"]:
        qid = q["id"]
        ids.append(qid)
        answer = q["answerField"].get(f"answer{qid}", "")
        form[f"answer{qid}"] = answer
        form[f"answertype{qid}"] = q["answerField"][f"answertype{qid}"]
        if q.get("blanks", 0) > 1 and q["type"] == "completion":
            parts = [p for p in re.split(r"[;；,，\n|]+|\s{2,}", str(answer)) if p.strip()]
            for i in range(q["blanks"]):
                form[f"answerEditor{qid}{i + 1}"] = parts[i] if i < len(parts) else ""
    form["answerwqbid"] = ",".join(ids) + ","
    form["pyFlag"] = "" if submit else "1"
    return form


# ---------------------------------------------------------------- running

def _work_enc(session, course: dict) -> tuple[str, str]:
    resp = session.get(COURSE_PAGE, params={"courseid": course["courseId"], "clazzid": course["clazzId"], "ismooc2": 1})
    fields = parse_course_page(resp.text)
    return fields.get("workEnc", ""), fields.get("cpi", "") or str(course.get("cpi", ""))


def list_homework(chaoxing, course: dict) -> list[Homework]:
    from api.base import SessionManager

    session = SessionManager.get_session()
    enc, cpi = _work_enc(session, course)
    if not enc:
        raise RuntimeError("课程页面上没有找到作业入口参数（workEnc）")
    resp = session.get(WORK_LIST, params={"courseId": course["courseId"], "classId": course["clazzId"],
                                          "cpi": cpi, "ut": "s", "enc": enc})
    if resp.status_code != 200:
        raise RuntimeError(f"读取作业列表失败（HTTP {resp.status_code}）")
    return parse_work_list(resp.text)


def do_homework(chaoxing, course: dict, hw: Homework, submit: bool) -> str:
    """Answer one 作业. Returns "submitted", "saved", "skipped" or raises."""
    from api.base import SessionManager, _emit_work_preview, _work_preview_questions

    session = SessionManager.get_session()
    resp = session.get(hw.url)
    if resp.status_code != 200:
        raise RuntimeError(f"打开作业失败（HTTP {resp.status_code}）")
    from api.base import is_graded_work_page

    if is_graded_work_page(getattr(resp, "url", ""), resp.text):
        logger.info(f"作业已提交并批阅: {hw.title}")
        return "skipped"
    page = parse_work_page(resp.text)
    if not page["questions"]:
        from api.base import classify_empty_work_page

        kind = classify_empty_work_page(resp.status_code, resp.text)
        if kind == "submitted":
            logger.info(f"作业已经提交过: {hw.title}")
            return "skipped"
        raise LookupError("已截止或未到作答时间" if kind == "closed" else "页面上没有读到题目")

    title = f"作业：{hw.title}"
    _emit_work_preview({"phase": "questions", "title": title, "cover_rate": 0, "submit": submit,
                        "questions": _work_preview_questions(page["questions"])})
    found, total = chaoxing._fill_answers(page["questions"], resp.text, chaoxing.kwargs.get("query_delay", 0))
    cover = round(found * 100 / total) if total else 0
    logger.info(f"作业「{hw.title}」：{total} 题，查到答案 {found} 题（{cover}%）")
    _emit_work_preview({"phase": "filled", "title": title, "cover_rate": cover, "submit": submit,
                        "questions": _work_preview_questions(page["questions"])})

    form = build_form(page, submit)
    result = chaoxing._post_work_form(session, form)
    try:
        data = result.json()
    except ValueError:
        data = {"status": False, "msg": f"HTTP {result.status_code}"}
    if not data.get("status"):
        _emit_work_preview({"phase": "failed", "title": title, "msg": data.get("msg", "")})
        raise RuntimeError(f"{'提交' if submit else '保存'}作业失败：{data.get('msg', '')}")
    _emit_work_preview({"phase": "submitted" if submit else "saved", "title": title, "msg": data.get("msg", "")})
    logger.info(f"{'已提交' if submit else '已保存（未提交）'}作业「{hw.title}」")
    return "submitted" if submit else "saved"


def run_homework(chaoxing, course: dict, submit: bool) -> dict:
    """Every unfinished 作业 of one course. Never raises: one failing 作业 is reported and skipped."""
    counts = {"submitted": 0, "saved": 0, "skipped": 0, "failed": 0}
    try:
        items = list_homework(chaoxing, course)
    except Exception as exc:
        logger.warning(f"读取「{course.get('title', '')}」的作业列表失败，已跳过: {exc}")
        counts["failed"] += 1
        return counts
    todo = [hw for hw in items if hw.todo]
    if items:
        logger.info(f"「{course.get('title', '')}」共 {len(items)} 份作业，未完成 {len(todo)} 份")
    for hw in todo:
        pause.wait_if_paused()
        try:
            counts[do_homework(chaoxing, course, hw, submit)] += 1
        except Exception as exc:
            counts["failed"] += 1
            logger.warning(f"作业「{hw.title}」未能自动完成：{exc}")
            manual.report(course, {"id": "homework", "title": "作业"},
                          {"type": "other", "card_type": "homework", "jobid": hw.params.get("workId", hw.title),
                           "name": hw.title}, urgent=True)
        time.sleep(1)
    return counts


def watch_activities(chaoxing, course: dict) -> int:
    """Open 随堂练习 / 任务 in 课堂活动: announced at once (they cannot be answered from here). Returns the count."""
    from api.base import SessionManager

    session = SessionManager.get_session()
    try:
        resp = session.get(ACTIVE_LIST, params={"fid": 0, "courseId": course["courseId"],
                                                "classId": course["clazzId"], "showNotStartedActive": 0})
        active = (resp.json().get("data") or {}).get("activeList") or []
    except Exception as exc:
        logger.debug(f"读取课堂活动失败: {exc}")
        return 0
    found = 0
    for item in active:
        kind = item.get("activeType")
        if kind not in (QUIZ_TYPE, TASK_TYPE) or item.get("status") != 1:
            continue                   # only the open ones (status 1); 2 = ended
        found += 1
        label = "quiz-open" if kind == QUIZ_TYPE else "task-open"
        name = str(item.get("nameOne") or ("随堂练习" if kind == QUIZ_TYPE else "任务"))
        left = str(item.get("nameFour") or "")
        manual.report(course, {"id": "active", "title": "课堂活动"},
                      {"type": "other", "card_type": label, "jobid": str(item.get("id", "")),
                       "name": f"{name}（{left}）" if left else name}, urgent=True)      # open right now
    return found
