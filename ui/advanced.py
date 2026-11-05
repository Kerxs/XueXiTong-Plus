# -*- coding: utf-8 -*-
"""Advanced options: the config.ini keys the worker reads that the basic settings do not cover.

Each field maps one ``[section] key`` to a control on the settings page. Values travel
as strings (exactly what config.ini stores) so unknown formats round-trip unchanged;
the QML side converts for switches, sliders and spin boxes. Pure Python, no Qt.

``show`` makes a field depend on another one:
    {"key": "tiku.provider", "has": "AI"}   comma list contains the value
    {"key": "notification.provider", "eq": "Telegram"}
    {"key": "notification.provider", "ne": ""}
    {"key": "tiku.submit", "on": True}      switch is on
    [cond, cond, ...]                       all of them
"""

from __future__ import annotations

import configparser

TIKU_PROVIDERS = [
    {"value": "TikuYanxi", "kind": "tiku", "label": "言溪题库", "hint": "需要 TOKEN"},
    {"value": "TikuLike", "kind": "tiku", "label": "LIKE 知识库", "hint": "需要 TOKEN，支持联网和识图"},
    {"value": "TikuGo", "kind": "tiku", "label": "GO 题", "hint": "网课小工具题库"},
    {"value": "TikuAdapter", "kind": "tiku", "label": "TikuAdapter", "hint": "自建的开源题库服务"},
    {"value": "AI", "kind": "ai", "label": "OpenAI 兼容接口", "hint": "DeepSeek、通义千问、Kimi 等提供 OpenAI 格式接口的大模型"},
    {"value": "SiliconFlow", "kind": "ai", "label": "硅基流动", "hint": "SiliconFlow 大模型"},
]

# How 章节检测 answers are found. Stored only through tiku.provider: the mode is derived
# from which kinds of providers the list holds (题库 always ahead of AI in "both").
ANSWER_MODES = [
    {"value": "none", "label": "不查找", "hint": "不使用题库或 AI，找不到答案的题目随机作答"},
    {"value": "tiku", "label": "题库", "hint": "在题库中搜索题目，按选择顺序查询"},
    {"value": "ai", "label": "AI 大模型", "hint": "让大模型读题作答，需要接口地址和 API Key"},
    {"value": "both", "label": "题库 + AI", "hint": "先查题库，题库找不到的题再交给 AI"},
]
_KIND = {p["value"]: p["kind"] for p in TIKU_PROVIDERS}
_DEFAULT = {"tiku": "TikuYanxi", "ai": "AI"}


def _split(value: str) -> list[str]:
    return [v.strip() for v in str(value).split(",") if v.strip()]


def answer_mode(provider: str) -> str:
    kinds = {_KIND.get(p, "tiku") for p in _split(provider)}
    if not kinds:
        return "none"
    if kinds == {"tiku"}:
        return "tiku"
    if kinds == {"ai"}:
        return "ai"
    return "both"


def apply_answer_mode(provider: str, mode: str) -> str:
    """New provider list for ``mode``, keeping the picks that still fit (default one if none)."""
    current = _split(provider)
    tiku = [p for p in current if _KIND.get(p, "tiku") == "tiku"]
    ai = [p for p in current if _KIND.get(p) == "ai"]
    if mode == "none":
        return ""
    parts = []
    if mode in ("tiku", "both"):
        parts += tiku or [_DEFAULT["tiku"]]
    if mode in ("ai", "both"):
        parts += ai or [_DEFAULT["ai"]]
    return ",".join(parts)


def order_providers(values: list[str]) -> str:
    """题库 first, then AI, each keeping the order the user picked them in."""
    tiku = [v for v in values if _KIND.get(v, "tiku") == "tiku"]
    ai = [v for v in values if _KIND.get(v) == "ai"]
    return ",".join(tiku + ai)

NOTIFY_PROVIDERS = [
    {"value": "", "label": "不推送"},
    {"value": "ServerChan", "label": "Server酱"},
    {"value": "Qmsg", "label": "Qmsg酱"},
    {"value": "Bark", "label": "Bark"},
    {"value": "Telegram", "label": "Telegram"},
]


def _f(section, key, type_, label, default="", hint="", **extra) -> dict:
    return {"id": f"{section}.{key}", "section": section, "key": key, "type": type_,
            "label": label, "hint": hint, "default": default, **extra}


# type: providers | switch | percent | number | choice | text | secret
#       hidden (stored, no control of its own)
#       display only: heading | localmodels | aiprovider | modelpicker
GROUPS: list[dict] = [
    {
        "id": "auto",
        "title": "自动完成",
        "subtitle": "视频和章节检测总是自动完成；这里决定课件、作业和课堂活动",
        "icon": "",
        "fields": [
            _f("common", "auto_documents", "switch", "课件 / 文档", "true",
               "章节里的课件、教案等打开一次，学习通即记为完成"),
            _f("common", "auto_homework", "switch", "作业", "true",
               "每次运行都会查看每门课的“作业”栏目，未完成的用答题来源自动作答"),
            _f("common", "homework_submit", "switch", "作业自动提交", "true",
               "关闭后只保存答案，到学习通检查后自己提交", show={"key": "common.auto_homework", "on": True}),
            _f("common", "watch_activities", "switch", "提醒随堂练习和课堂任务", "true",
               "发现正在进行的随堂练习或课堂任务时立即推送提醒（这两类需要你自己完成）"),
        ],
    },
    {
        "id": "tiku",
        "title": "答题来源",
        "subtitle": "章节检测用题库还是 AI 找答案",
        "icon": "",
        "fields": [
            _f("tiku", "provider", "providers", "答题方式", "",
               "可多选，数字是查询顺序：前一个找不到再用下一个",
               options=TIKU_PROVIDERS, modes=ANSWER_MODES),
            # Per-provider settings, shown only for the selected providers.
            _f("tiku", "", "heading", "言溪 / LIKE 知识库", show={"key": "tiku.provider", "has": ["TikuYanxi", "TikuLike"]}),
            _f("tiku", "tokens", "secret", "TOKEN", "", "多个用英文逗号隔开，按顺序使用",
               show={"key": "tiku.provider", "has": ["TikuYanxi", "TikuLike"]}),
            _f("tiku", "likeapi_model", "text", "LIKE 模型", "glm-4.5-air", "例如 glm-4.5-air",
               show={"key": "tiku.provider", "has": ["TikuLike"]}),
            _f("tiku", "likeapi_search", "switch", "联网搜索", "false",
               show={"key": "tiku.provider", "has": ["TikuLike"]}),
            _f("tiku", "likeapi_vision", "switch", "识别图片", "true", "能读取题目里的图片",
               show={"key": "tiku.provider", "has": ["TikuLike"]}),
            _f("tiku", "likeapi_retry", "switch", "请求失败时重试", "true",
               show={"key": "tiku.provider", "has": ["TikuLike"]}),
            _f("tiku", "likeapi_retry_times", "number", "最多重试次数", "3",
               min=1, max=10, step=1, decimals=0, suffix="次",
               show=[{"key": "tiku.provider", "has": ["TikuLike"]}, {"key": "tiku.likeapi_retry", "on": True}]),
            _f("tiku", "", "heading", "GO 题", show={"key": "tiku.provider", "has": ["TikuGo"]}),
            _f("tiku", "go_authorization", "secret", "授权码", "", "GO 题提供的 Authorization",
               show={"key": "tiku.provider", "has": ["TikuGo"]}),
            _f("tiku", "go_min_interval", "number", "请求间隔", "1.0", "两次请求之间至少等待多久",
               min=0, max=30, step=0.5, decimals=1, suffix="秒", show={"key": "tiku.provider", "has": ["TikuGo"]}),
            _f("tiku", "go_retry_times", "number", "最多重试次数", "3",
               min=1, max=10, step=1, decimals=0, suffix="次", show={"key": "tiku.provider", "has": ["TikuGo"]}),
            _f("tiku", "go_retry_backoff", "number", "重试等待", "1.2", "每次重试前等待的基准时间，之后逐次增加",
               min=0, max=10, step=0.1, decimals=1, suffix="秒", show={"key": "tiku.provider", "has": ["TikuGo"]}),
            _f("tiku", "", "heading", "TikuAdapter", show={"key": "tiku.provider", "has": ["TikuAdapter"]}),
            _f("tiku", "url", "text", "服务地址", "", "例如 http://127.0.0.1:8060/adapter-service/search",
               show={"key": "tiku.provider", "has": ["TikuAdapter"]}),
            _f("tiku", "", "heading", "OpenAI 兼容接口", show={"key": "tiku.provider", "has": ["AI"]}),
            _f("tiku", "", "localmodels", "本机模型", show={"key": "tiku.provider", "has": ["AI"]}),
            _f("tiku", "", "aiprovider", "服务商", show={"key": "tiku.provider", "has": ["AI"]}),
            # JSON list of {"name", "endpoint"} (ui/cloudmodels.py), edited by the 服务商 field
            _f("tiku", "custom_providers", "hidden", "自定义服务商", ""),
            _f("tiku", "endpoint", "text", "接口地址", "", "通常要带 /v1，例如 https://api.example.com/v1",
               show={"key": "tiku.provider", "has": ["AI"]}),
            _f("tiku", "key", "secret", "API Key", "", "本机运行的模型服务（127.0.0.1 / localhost）可以留空",
               show={"key": "tiku.provider", "has": ["AI"]}),
            _f("tiku", "", "modelpicker", "选择模型", show={"key": "tiku.provider", "has": ["AI"]}),
            _f("tiku", "model", "text", "模型名称", "", "可以从上面的列表选择，也可以直接填写",
               show={"key": "tiku.provider", "has": ["AI"]}),
            _f("tiku", "image_mode", "choice", "题目图片", "auto",
               "题目或选项是图片时怎么交给 AI", options=[
                   {"value": "auto", "label": "自动（先直接识别，不支持就转成文字）"},
                   {"value": "direct", "label": "AI 直接识别图片"},
                   {"value": "transcribe", "label": "先把图片转成文字（含 LaTeX 公式）"},
                   {"value": "off", "label": "不处理"},
               ], show={"key": "tiku.provider", "has": ["AI"]}),
            _f("tiku", "vision_model", "text", "识图模型", "",
               "把图片转成文字用的模型，要能看图，例如 qwen-vl-max、glm-4v-flash；留空则用上面的答题模型",
               show=[{"key": "tiku.provider", "has": ["AI"]}, {"key": "tiku.image_mode", "ne": "off"},
                     {"key": "tiku.image_mode", "ne": "direct"}]),
            _f("tiku", "vision_endpoint", "text", "识图模型接口地址", "",
               "识图模型在另一家服务时填写，例如 https://dashscope.aliyuncs.com/compatible-mode/v1；留空则与答题模型相同",
               show=[{"key": "tiku.provider", "has": ["AI"]}, {"key": "tiku.image_mode", "ne": "off"},
                     {"key": "tiku.image_mode", "ne": "direct"}]),
            _f("tiku", "vision_key", "secret", "识图模型 API Key", "",
               "识图模型接口地址不同时填写",
               show=[{"key": "tiku.provider", "has": ["AI"]}, {"key": "tiku.image_mode", "ne": "off"},
                     {"key": "tiku.image_mode", "ne": "direct"}]),
            _f("tiku", "http_proxy", "text", "代理", "",
               "可选，只在访问外网接口需要翻墙时填写，例如 http://127.0.0.1:7890。不要填模型服务自己的地址；接口在本机时会自动忽略",
               show={"key": "tiku.provider", "has": ["AI"]}),
            _f("tiku", "", "heading", "硅基流动", show={"key": "tiku.provider", "has": ["SiliconFlow"]}),
            _f("tiku", "siliconflow_key", "secret", "API Key", "",
               show={"key": "tiku.provider", "has": ["SiliconFlow"]}),
            _f("tiku", "siliconflow_model", "text", "模型名称", "deepseek-ai/DeepSeek-R1",
               "例如 deepseek-ai/DeepSeek-V3", show={"key": "tiku.provider", "has": ["SiliconFlow"]}),
            _f("tiku", "siliconflow_endpoint", "text", "接口地址", "https://api.siliconflow.cn/v1/chat/completions",
               show={"key": "tiku.provider", "has": ["SiliconFlow"]}),
            _f("tiku", "min_interval_seconds", "number", "大模型请求间隔", "3", "两次请求之间至少等待多久，0 表示不限制",
               min=0, max=120, step=1, decimals=0, suffix="秒",
               show={"key": "tiku.provider", "has": ["AI", "SiliconFlow"]}),
            _f("tiku", "check_llm_connection", "switch", "运行前检查大模型连接", "true",
               "连接失败时会询问是否继续", show={"key": "tiku.provider", "has": ["AI", "SiliconFlow"]}),
        ],
    },
    {
        "id": "answer",
        "title": "答题",
        "subtitle": "找到答案之后如何提交，以及判断题的识别",
        "icon": "",
        "fields": [
            _f("tiku", "submit", "switch", "达到覆盖率时提交", "true",
               "关闭则只保存答案，之后可以自己到学习通检查后提交。需要解锁下一章的章节必须提交"),
            _f("tiku", "cover_rate", "percent", "最低题库覆盖率", "0.75",
               "查到答案的题目占比达到这个值才提交，否则只保存", show={"key": "tiku.submit", "on": True}),
            _f("tiku", "delay", "number", "查题间隔", "2.0", "每查一道题后等待的时间",
               min=0, max=30, step=0.5, decimals=1, suffix="秒"),
            _f("common", "work_redo_enabled", "switch", "答错后自动重做", "true",
               "答错时带着错题信息再答一次；课程只允许作答一次时会保留已提交的成绩"),
            _f("common", "work_max_retries", "number", "最多重做次数", "3",
               min=1, max=10, step=1, decimals=0, suffix="次", show={"key": "common.work_redo_enabled", "on": True}),
            _f("tiku", "true_list", "text", "判断题“正确”的写法", "正确,对,√,是,true,t,1,yes,y", "英文逗号隔开，不要加空格或引号"),
            _f("tiku", "false_list", "text", "判断题“错误”的写法", "错误,错,×,否,不对,不正确,false,f,0,no,n", "英文逗号隔开，不要加空格或引号"),
        ],
    },
    {
        "id": "notify",
        "title": "通知推送",
        "subtitle": "任务结束或出错时推送到手机",
        "icon": "",
        "fields": [
            _f("notification", "provider", "choice", "推送服务", "", options=NOTIFY_PROVIDERS),
            # 匿名使用统计（设置 → 数据与隐私 里的开关，api/telemetry.py），默认关闭
            _f("common", "telemetry", "hidden", "匿名使用统计", "false"),
            _f("notification", "url", "secret", "推送地址", "",
               "服务提供的完整推送地址（含密钥），例如 Server酱的 https://sctapi.ftqq.com/<SendKey>.send",
               show={"key": "notification.provider", "ne": ""}),
            _f("notification", "tg_chat_id", "text", "Chat ID", "", show={"key": "notification.provider", "eq": "Telegram"}),
        ],
    },
]

# Template placeholders that mean "not filled in".
_PLACEHOLDERS = {"xxx", "xxxxxx"}


def _is_local(url: str) -> bool:
    from urllib.parse import urlsplit

    try:
        host = (urlsplit(url.strip()).hostname or "").lower()
    except ValueError:
        return False
    return host in ("localhost", "::1") or host.startswith("127.")


def ai_config_problem(values: dict[str, str]) -> str:
    """Why an AI-based answer mode cannot work with these settings, or "" if it looks usable."""
    picked = _split(values.get("tiku.provider", ""))
    if "AI" in picked:
        endpoint = values.get("tiku.endpoint", "").strip()
        if not endpoint:
            return "答题方式用到了 AI，但还没填写接口地址"
        if not endpoint.lower().startswith(("http://", "https://")):
            return "AI 接口地址要以 http:// 或 https:// 开头"
        if endpoint.rstrip("/").lower().endswith("/chat/completions"):
            return "AI 接口地址不要带 /chat/completions，填到 /v1 即可"
        if not values.get("tiku.model", "").strip():
            return "答题方式用到了 AI，但还没填写模型名称"
        if not values.get("tiku.key", "").strip() and not _is_local(endpoint):
            return "答题方式用到了 AI，但还没填写 API Key"
    if "SiliconFlow" in picked and not values.get("tiku.siliconflow_key", "").strip():
        return "答题方式用到了硅基流动，但还没填写 API Key"
    return ""


def answer_setup_problem(values: dict[str, str]) -> str:
    """Like ai_config_problem, plus 题库 that need a token / address to do anything."""
    problem = ai_config_problem(values)
    if problem:
        return problem
    picked = _split(values.get("tiku.provider", ""))
    if any(p in picked for p in ("TikuYanxi", "TikuLike")) and not values.get("tiku.tokens", "").strip():
        return "选择了言溪 / LIKE 知识库，但还没填写 TOKEN"
    if "TikuGo" in picked and not values.get("tiku.go_authorization", "").strip():
        return "选择了 GO 题，但还没填写授权码"
    if "TikuAdapter" in picked and not values.get("tiku.url", "").strip():
        return "选择了 TikuAdapter，但还没填写服务地址"
    return ""


DISPLAY_ONLY = ("heading", "localmodels", "aiprovider", "modelpicker")


def fields() -> list[dict]:
    return [f for g in GROUPS for f in g["fields"] if f["type"] not in DISPLAY_ONLY]


def read_values(config: configparser.ConfigParser) -> dict[str, str]:
    values = {}
    for f in fields():
        raw = config.get(f["section"], f["key"], fallback=f["default"]).strip()
        values[f["id"]] = "" if raw.lower() in _PLACEHOLDERS else raw
    return values


def write_values(config: configparser.ConfigParser, values: dict[str, str]) -> None:
    """Store values; keys missing from the file are only added when they differ from the default."""
    for f in fields():
        value = str(values.get(f["id"], f["default"])).strip()
        section, key = f["section"], f["key"]
        if not config.has_section(section):
            config.add_section(section)
        if config.has_option(section, key) or value != f["default"]:
            config[section][key] = value


def normalize(field_id: str, value) -> str:
    """QML hands over bools / numbers / lists; store them the way config.ini spells them."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple)):
        return ",".join(str(v).strip() for v in value if str(v).strip())
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)
