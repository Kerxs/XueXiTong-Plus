"""Minimal stand-in for the ``openai`` package on Android.

The real package needs pydantic-core and jiter (Rust extensions without Android builds).
api/answer.py only uses ``OpenAI(base_url, api_key, http_client)``,
``client.chat.completions.create(...)`` and the error classes below, so this module
implements exactly that over httpx, with the same names and attributes.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx

__all__ = [
    "OpenAI", "OpenAIError", "APIError", "APIStatusError", "APIConnectionError", "APITimeoutError",
    "BadRequestError", "AuthenticationError", "PermissionDeniedError", "NotFoundError",
    "RateLimitError", "InternalServerError",
]


class OpenAIError(Exception):
    pass


class APIError(OpenAIError):
    def __init__(self, message: str, body: Any = None):
        super().__init__(message)
        self.message = message
        self.body = body


class APIConnectionError(APIError):
    def __init__(self, message: str = "Connection error."):
        super().__init__(message)


class APITimeoutError(APIConnectionError):
    def __init__(self, message: str = "Request timed out."):
        super().__init__(message)


class APIStatusError(APIError):
    def __init__(self, message: str, status_code: int, body: Any = None):
        super().__init__(message, body)
        self.status_code = status_code


class BadRequestError(APIStatusError):
    pass


class AuthenticationError(APIStatusError):
    pass


class PermissionDeniedError(APIStatusError):
    pass


class NotFoundError(APIStatusError):
    pass


class RateLimitError(APIStatusError):
    pass


class InternalServerError(APIStatusError):
    pass


_STATUS = {400: BadRequestError, 401: AuthenticationError, 403: PermissionDeniedError,
           404: NotFoundError, 429: RateLimitError}


def _ns(value: Any) -> Any:
    """JSON -> attribute access, like the SDK's response models (missing attributes -> None)."""
    if isinstance(value, dict):
        return _Obj({k: _ns(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_ns(v) for v in value]
    return value


class _Obj(SimpleNamespace):
    def __init__(self, data: dict):
        super().__init__(**data)

    def __getattr__(self, name: str) -> Any:  # only called for missing attributes
        if name.startswith("__"):
            raise AttributeError(name)
        return None


class _Completions:
    def __init__(self, client: "OpenAI"):
        self._client = client

    def create(self, *, model: str, messages: list, extra_body: dict | None = None,
               timeout: float | None = None, **params: Any) -> Any:
        body = {"model": model, "messages": messages,
                **{k: v for k, v in params.items() if v is not None}}
        if extra_body:
            body.update(extra_body)
        return _ns(self._client._post("/chat/completions", body, timeout))


class _Chat:
    def __init__(self, client: "OpenAI"):
        self.completions = _Completions(client)


class OpenAI:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None,
                 http_client: httpx.Client | None = None, timeout: float = 600.0, **_: Any):
        self.api_key = api_key or ""
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self._http = http_client or httpx.Client()
        self._timeout = timeout
        self.chat = _Chat(self)

    def _post(self, path: str, body: dict, timeout: float | None) -> Any:
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        try:
            response = self._http.post(self.base_url + path, json=body, headers=headers,
                                       timeout=timeout or self._timeout)
        except httpx.TimeoutException as exc:
            raise APITimeoutError() from exc
        except httpx.HTTPError as exc:
            raise APIConnectionError(f"Connection error: {exc}") from exc
        try:
            data = response.json()
        except ValueError:
            data = None
        if response.status_code >= 400:
            detail = data.get("error") if isinstance(data, dict) else None
            if isinstance(detail, dict):
                detail = detail.get("message")
            message = f"Error code: {response.status_code} - {detail or response.text[:300]}"
            cls = _STATUS.get(response.status_code,
                              InternalServerError if response.status_code >= 500 else APIStatusError)
            raise cls(message, response.status_code, data)
        if data is None:
            raise APIError(f"Invalid JSON response: {response.text[:300]}")
        return data
