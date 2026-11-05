# -*- coding: utf-8 -*-
"""看图答题: images in a question (title and options) for AI models that can see images.

Question text keeps images as ``<img src="…">`` tokens (api/decode.py, api/homework.py). For the
AI answer source they are downloaded through the logged-in 学习通 session (the image server wants
the 学习通 Referer), shrunk when large (Pillow, when present — not on the phone), and attached in the
standard OpenAI multimodal format: ``{"type": "image_url", "image_url": {"url": "data:…"}}``.

Which models can see images is not hard-coded: the images are sent, and if the model refuses the
request (HTTP 400 / 422 …) the question is asked again as text and images stay off for that model
for the rest of the run (api/answer.AI).
"""

from __future__ import annotations

import base64
import io
import re

from api.logger import logger

IMG_TAG = re.compile(r'<img\s+src="([^"]+)"\s*/?>', re.IGNORECASE)
MAX_IMAGES = 4                 # per question
MAX_BYTES = 4 * 1024 * 1024    # downloaded size
MAX_SIDE = 1280                # longest side after shrinking
REFERER = "https://mooc1.chaoxing.com/"


def image_urls(q_info: dict) -> list[str]:
    """Image addresses in the question title and options, in order, without repeats."""
    text = f"{q_info.get('title', '')}\n{q_info.get('options', '')}"
    urls = []
    for url in IMG_TAG.findall(text):
        url = url.strip()
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith(("http://", "https://", "data:image/")) and url not in urls:
            urls.append(url)
    return urls[:MAX_IMAGES]


def text_only(text: str, marker: str = "[图片]") -> str:
    """The question text with image tags replaced by a short marker (for text-only models)."""
    return IMG_TAG.sub(marker, text or "")


def _shrink(data: bytes) -> tuple[bytes, str]:
    try:
        from PIL import Image
    except ImportError:
        return data, ""
    try:
        img = Image.open(io.BytesIO(data))
        fmt = (img.format or "").lower()
        if max(img.size) <= MAX_SIDE and len(data) <= 512 * 1024 and fmt in ("png", "jpeg", "gif", "webp"):
            return data, "image/jpeg" if fmt == "jpeg" else f"image/{fmt}"
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        if img.mode not in ("RGB", "L"):
            background = Image.new("RGB", img.size, "white")
            background.paste(img, mask=img.convert("RGBA").split()[-1])
            img = background
        out = io.BytesIO()
        img.save(out, "JPEG", quality=85)
        return out.getvalue(), "image/jpeg"
    except Exception:  # not an image Pillow understands: send it as it is
        return data, ""


def _guess_type(data: bytes, header: str) -> str:
    if header.startswith("image/"):
        return header.split(";")[0]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"GIF8":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


def data_url(url: str, session=None) -> str | None:
    """Download one image as a data: URL ("" / None when it cannot be used)."""
    if url.startswith("data:image/"):
        return url
    try:
        if session is None:
            from api.base import SessionManager

            session = SessionManager.get_session()
        resp = session.get(url, headers={"Referer": REFERER}, timeout=(8, 15))
        if resp.status_code != 200:
            logger.debug(f"题目图片下载失败 HTTP {resp.status_code}: {url[:80]}")
            return None
        data = resp.content or b""
        if len(data) > MAX_BYTES:
            logger.debug(f"题目图片太大，已跳过: {url[:80]}")
            return None
    except Exception as exc:
        logger.debug(f"题目图片下载失败: {exc}")
        return None
    shrunk, mime = _shrink(data)
    mime = mime or _guess_type(shrunk, str(getattr(resp, "headers", {}).get("Content-Type", "")))
    if not mime:
        return None
    return f"data:{mime};base64,{base64.b64encode(shrunk).decode('ascii')}"


TRANSCRIBE_PROMPT = (
    "请把这张图片里的内容完整转写成文字，供另一个只能读文字的模型答题使用：\n"
    "1. 文字逐字照抄，不要总结、不要作答；\n"
    "2. 数学公式、化学式用 LaTeX，行内写成 $...$；\n"
    "3. 表格用 Markdown 表格；\n"
    "4. 图表、示意图、电路图、几何图形等，用简洁的文字说明其中的关键元素、数值、标注和关系；\n"
    "5. 只输出转写结果，不要任何前后说明。"
)

# image address -> its text, for this run (the same picture is often in several questions)
_transcribed: dict[str, str] = {}


def transcribe(url: str, ask, session=None) -> str:
    """One image → text (LaTeX formulas, Markdown tables) by an image-reading model.

    ``ask(content) -> str`` sends one user message to that model. "" when it cannot be done.
    """
    if url in _transcribed:
        return _transcribed[url]
    image = data_url(url, session)
    if not image:
        return ""
    try:
        text = (ask([{"type": "text", "text": TRANSCRIBE_PROMPT},
                     {"type": "image_url", "image_url": {"url": image}}]) or "").strip()
    except Exception as exc:
        logger.warning(f"图片转文字失败: {exc}")
        return ""
    if text:
        _transcribed[url] = text
    return text


def with_transcriptions(text: str, ask, session=None) -> tuple[str, int]:
    """The question text with every image replaced by 【图片内容：…】. Returns (text, converted)."""
    done = 0

    def replace(match):
        nonlocal done
        content = transcribe(match.group(1), ask, session)
        if not content:
            return "[图片]"
        done += 1
        return f"【图片内容：{content}】"

    return IMG_TAG.sub(replace, text or ""), done


def user_content(text: str, q_info: dict, session=None):
    """The user message content: plain text, or [text, image…] parts when the question has images
    that could be downloaded. Returns (content, image_count)."""
    urls = image_urls(q_info)
    if not urls:
        return text, 0
    images = [d for d in (data_url(u, session) for u in urls) if d]
    if not images:
        return text_only(text), 0
    parts = [{"type": "text", "text": text_only(text, "[见图]")
              + f"\n（题目中有 {len(images)} 张图片，已按出现顺序附在后面，请结合图片作答）"}]
    parts += [{"type": "image_url", "image_url": {"url": d}} for d in images]
    return parts, len(images)
