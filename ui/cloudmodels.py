# -*- coding: utf-8 -*-
"""Cloud model providers for the AI answer source (OpenAI-compatible APIs).

高级选项 → 答题来源 → OpenAI 兼容接口: pick a common provider to fill the address, or type
any address; the provider is recognised from the host. With the API key filled in,
GET <address>/models lists the models the key can use and the user picks one.
Services that are not in the list can be saved as 自定义服务商 (name + address).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit

# OpenAI-compatible base addresses (the part before /chat/completions).
# region: "cn" = reachable from mainland China directly; "intl" = usually needs a proxy there.
# console: where the user creates an API key.
PROVIDERS = [
    {"id": "deepseek", "name": "DeepSeek", "region": "cn", "endpoint": "https://api.deepseek.com/v1",
     "hosts": ["deepseek.com"], "console": "https://platform.deepseek.com/api_keys"},
    {"id": "dashscope", "name": "通义千问（阿里云百炼）", "region": "cn",
     "endpoint": "https://dashscope.aliyuncs.com/compatible-mode/v1",
     "hosts": ["dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"], "console": "https://bailian.console.aliyun.com/"},
    {"id": "moonshot", "name": "Kimi（月之暗面）", "region": "cn", "endpoint": "https://api.moonshot.cn/v1",
     "hosts": ["moonshot.cn", "moonshot.ai"], "console": "https://platform.moonshot.cn/console/api-keys"},
    {"id": "zhipu", "name": "智谱 GLM", "region": "cn", "endpoint": "https://open.bigmodel.cn/api/paas/v4",
     "hosts": ["bigmodel.cn"], "console": "https://open.bigmodel.cn/usercenter/apikeys"},
    {"id": "volcengine", "name": "豆包（火山方舟）", "region": "cn", "endpoint": "https://ark.cn-beijing.volces.com/api/v3",
     "hosts": ["volces.com"], "console": "https://console.volcengine.com/ark"},
    {"id": "siliconflow", "name": "硅基流动", "region": "cn", "endpoint": "https://api.siliconflow.cn/v1",
     "hosts": ["siliconflow.cn", "siliconflow.com"], "console": "https://cloud.siliconflow.cn/account/ak"},
    {"id": "hunyuan", "name": "腾讯混元", "region": "cn", "endpoint": "https://api.hunyuan.cloud.tencent.com/v1",
     "hosts": ["hunyuan.cloud.tencent.com"], "console": "https://console.cloud.tencent.com/hunyuan/api-key"},
    {"id": "qianfan", "name": "百度千帆", "region": "cn", "endpoint": "https://qianfan.baidubce.com/v2",
     "hosts": ["baidubce.com"], "console": "https://console.bce.baidu.com/qianfan/"},
    {"id": "minimax", "name": "MiniMax", "region": "cn", "endpoint": "https://api.minimaxi.com/v1",
     "hosts": ["minimaxi.com", "minimax.chat", "minimax.io"], "console": "https://platform.minimaxi.com/"},
    {"id": "stepfun", "name": "阶跃星辰", "region": "cn", "endpoint": "https://api.stepfun.com/v1",
     "hosts": ["stepfun.com"], "console": "https://platform.stepfun.com/"},
    {"id": "modelscope", "name": "魔搭 ModelScope", "region": "cn", "endpoint": "https://api-inference.modelscope.cn/v1",
     "hosts": ["modelscope.cn"], "console": "https://modelscope.cn/my/myaccesstoken"},
    {"id": "openai", "name": "OpenAI", "region": "intl", "endpoint": "https://api.openai.com/v1",
     "hosts": ["openai.com"], "console": "https://platform.openai.com/api-keys"},
    {"id": "gemini", "name": "Google Gemini", "region": "intl",
     "endpoint": "https://generativelanguage.googleapis.com/v1beta/openai",
     "hosts": ["generativelanguage.googleapis.com"], "console": "https://aistudio.google.com/apikey"},
    {"id": "anthropic", "name": "Claude（Anthropic）", "region": "intl", "endpoint": "https://api.anthropic.com/v1",
     "hosts": ["anthropic.com"], "console": "https://console.anthropic.com/settings/keys"},
    {"id": "xai", "name": "xAI Grok", "region": "intl", "endpoint": "https://api.x.ai/v1",
     "hosts": ["x.ai"], "console": "https://console.x.ai/"},
    {"id": "mistral", "name": "Mistral", "region": "intl", "endpoint": "https://api.mistral.ai/v1",
     "hosts": ["mistral.ai"], "console": "https://console.mistral.ai/api-keys"},
    {"id": "groq", "name": "Groq", "region": "intl", "endpoint": "https://api.groq.com/openai/v1",
     "hosts": ["groq.com"], "console": "https://console.groq.com/keys"},
    {"id": "openrouter", "name": "OpenRouter", "region": "intl", "endpoint": "https://openrouter.ai/api/v1",
     "hosts": ["openrouter.ai"], "console": "https://openrouter.ai/keys"},
]
REGIONS = [
    {"id": "cn", "label": "国内服务"},
    {"id": "intl", "label": "海外服务（在国内通常需要代理）"},
]
LOCAL_HOSTS = ("localhost", "::1")
LOCAL_NAME = "本机模型服务"

# 自定义服务商: the user's own OpenAI-compatible services (a relay, a company gateway...),
# kept in config.ini [tiku] custom_providers as a JSON list of {"name", "endpoint"}.
CUSTOM_KEY = "tiku.custom_providers"
MAX_CUSTOM = 20
MAX_NAME = 24


def normalize_endpoint(endpoint: str) -> str:
    return (endpoint or "").strip().rstrip("/")


def _host(endpoint: str) -> str:
    try:
        return (urlsplit((endpoint or "").strip()).hostname or "").lower()
    except ValueError:
        return ""


def is_local(endpoint: str) -> bool:
    host = _host(endpoint)
    return host in LOCAL_HOSTS or host.startswith("127.")


def _known(endpoint: str) -> dict | None:
    host = _host(endpoint)
    if not host:
        return None
    for provider in PROVIDERS:
        if any(host == h or host.endswith("." + h) for h in provider["hosts"]):
            return provider
    return None


def parse_custom(text) -> list[dict]:
    """The saved custom providers; anything malformed is dropped instead of failing."""
    if isinstance(text, (list, tuple)):
        items = list(text)
    else:
        try:
            items = json.loads(text) if str(text or "").strip() else []
        except ValueError:
            return []
    out, seen = [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()[:MAX_NAME]
        endpoint = normalize_endpoint(str(item.get("endpoint") or ""))
        if not name or not endpoint.lower().startswith(("http://", "https://")) or endpoint in seen:
            continue
        seen.add(endpoint)
        out.append({"name": name, "endpoint": endpoint})
    return out[:MAX_CUSTOM]


def dump_custom(items) -> str:
    items = parse_custom(items)
    return json.dumps(items, ensure_ascii=False, separators=(",", ":")) if items else ""


def custom_problem(name: str, endpoint: str, existing=(), cloud_only: bool = False) -> str:
    """Why this custom provider cannot be saved ("" = fine). cloud_only: the phone (no local services)."""
    name, endpoint = (name or "").strip(), normalize_endpoint(endpoint)
    saved = parse_custom(existing)
    if not name:
        return "请填写名称"
    if len(name) > MAX_NAME:
        return f"名称最多 {MAX_NAME} 个字"
    if not endpoint:
        return "请填写接口地址"
    if not endpoint.lower().startswith(("http://", "https://")) or not _host(endpoint):
        return "接口地址要以 http:// 或 https:// 开头"
    if endpoint.lower().endswith("/chat/completions"):
        return "接口地址不要带 /chat/completions，填到 /v1 即可"
    local = is_local(endpoint)
    if cloud_only and local:
        return "手机上不能使用本机模型服务"
    if cloud_only and endpoint.lower().startswith("http://"):
        return "请使用 https:// 地址，API Key 不能明文传输"
    for item in saved:
        if item["endpoint"] == endpoint:
            return f"这个地址已经保存为“{item['name']}”"
        if item["name"] == name:
            return "已有同名的自定义服务"
    if len(saved) >= MAX_CUSTOM:
        return f"最多保存 {MAX_CUSTOM} 个自定义服务"
    return ""


def add_custom(existing, name: str, endpoint: str) -> list[dict]:
    return parse_custom([*parse_custom(existing), {"name": name, "endpoint": endpoint}])


def remove_custom(existing, endpoint: str) -> list[dict]:
    endpoint = normalize_endpoint(endpoint)
    return [item for item in parse_custom(existing) if item["endpoint"] != endpoint]


def is_listed(endpoint: str, custom=()) -> bool:
    """A built-in provider's address, or one of the user's saved custom providers."""
    endpoint = normalize_endpoint(endpoint)
    return (any(p["endpoint"] == endpoint for p in PROVIDERS)
            or any(c["endpoint"] == endpoint for c in parse_custom(custom)))


def identify(endpoint: str, custom=()) -> str:
    """Provider name for an address: a saved custom name, a known company, 本机模型服务, or ""."""
    endpoint = normalize_endpoint(endpoint)
    if not _host(endpoint):
        return ""
    for item in parse_custom(custom):
        if item["endpoint"] == endpoint:
            return item["name"]
    if is_local(endpoint):
        return LOCAL_NAME
    provider = _known(endpoint)
    return provider["name"] if provider else ""


def console_url(endpoint: str) -> str:
    """Where to create an API key for this address ("" when unknown)."""
    provider = _known(endpoint)
    return provider["console"] if provider else ""


def public_providers() -> list[dict]:
    """What the UIs need (no host lists)."""
    return [{k: p[k] for k in ("id", "name", "region", "endpoint", "console")} for p in PROVIDERS]


class ModelListError(RuntimeError):
    pass


def _opener(proxy: str):
    if proxy.strip():
        return urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy.strip(), "https": proxy.strip()}))
    return urllib.request.build_opener()


def list_models(endpoint: str, key: str, proxy: str = "", timeout: float = 15) -> list[str]:
    """Model ids the key can use: GET <endpoint>/models (OpenAI format). Raises ModelListError."""
    base = (endpoint or "").strip().rstrip("/")
    if not base.lower().startswith(("http://", "https://")):
        raise ModelListError("请先填写以 http:// 或 https:// 开头的接口地址")
    host = _host(base)
    local = is_local(base)
    if not key.strip() and not local:
        raise ModelListError("请先填写 API Key")
    headers = {"Accept": "application/json", "User-Agent": "XueXiTong-Plus"}
    if key.strip():
        headers["Authorization"] = f"Bearer {key.strip()}"
        if host == "api.anthropic.com":
            # Anthropic's own /models wants these; chat goes through its OpenAI-compatible layer.
            headers["x-api-key"] = key.strip()
            headers["anthropic-version"] = "2023-06-01"
    request = urllib.request.Request(base + "/models", headers=headers)
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({})) if local else _opener(proxy)
        with opener.open(request, timeout=timeout) as resp:  # noqa: S310 - address entered by the user
            data = json.loads(resp.read(4 * 1024 * 1024).decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ModelListError(f"API Key 不正确或没有权限（{exc.code}）") from exc
        if exc.code == 404:
            raise ModelListError("这个服务不提供模型列表，请手动填写模型名称（地址通常以 /v1 结尾）") from exc
        raise ModelListError(f"获取模型列表失败（HTTP {exc.code}）") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", exc)
        raise ModelListError(f"连不上 {base}：{reason}") from exc
    except ValueError as exc:
        raise ModelListError("返回内容不是模型列表，请检查接口地址") from exc
    items = data.get("data") if isinstance(data, dict) else None
    if not isinstance(items, list):
        items = data.get("models") if isinstance(data, dict) else None
    names = []
    for item in items if isinstance(items, list) else []:
        name = str(item.get("id") or item.get("name") or "").strip() if isinstance(item, dict) else ""
        if name.startswith("models/"):  # Gemini lists "models/gemini-…"; chat takes the bare name
            name = name[len("models/"):]
        if name and name not in names:
            names.append(name)
    if not names:
        raise ModelListError("服务没有返回任何模型，请手动填写模型名称")
    return sorted(names, key=str.lower)
