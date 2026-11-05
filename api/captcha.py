"""
Captcha API for Chaoxing

本模块用于通过CX验证码，提供包括验证码获取、识别、验证等接口。
使用了开源的验证码识别库[DdddOcr](https://github.com/sml2h3/ddddocr)

Author: skreon
Email: 1340554713@qq.com
Date: 2025-06-05
Version: 1.0.1
"""

from __future__ import annotations

from random import randint
from typing import Optional

from loguru import logger
from requests import RequestException, Session

__author__ = "skreon 1340554713@qq.com"
__version__ = "1.0.1"

try:
    from ddddocr import DdddOcr

    HAS_DDDDOCR = True
except ImportError:
    DdddOcr = None
    HAS_DDDDOCR = False


def ocr_init() -> Optional[DdddOcr]:
    """Initialize and return a reusable OCR instance, if available."""
    if not HAS_DDDDOCR:
        logger.warning(
            "未检测到 ddddocr 依赖，自动验证码识别将不可用。如遇403限制请在浏览器端手动完成验证。"
        )
        return None

    try:
        return DdddOcr(show_ad=False)
    except Exception as exc:
        logger.warning("ddddocr 初始化失败: {}，自动验证码识别将不可用", exc)
        return None


_MISSING = object()


class CxCaptcha:
    """
    CxCaptcha 类用于处理学习任务中出现的验证码

    该类提供了获取、识别和提交验证码的方法，使用 requests 库进行 HTTP 请求，
    并利用 DdddOcr 进行验证码识别。

    Attributes:
        host (str): 超星平台的主机地址。
        api (dict): 包含获取和提交验证码的 API 路径。
        user_agent (str): 用户代理字符串。
        cookies (str): 会话 cookies。
        s (requests.Session): 用于管理会话的请求对象。
    """

    host = "https://mooc1.chaoxing.com"
    api = {
        "get": "/processVerifyPng.ac",
        "submit": "/html/processVerify.ac",
    }
    DEFAULT_TIMEOUT = (5.0, 15.0)

    def __init__(
        self,
        user_agent: str,
        cookies: str,
        ocr: Optional[DdddOcr] = _MISSING,
        *,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
    ):
        """
        初始化 CxCaptcha 实例。

        Args:
            user_agent (str): 用户代理字符串。
            cookies (str): 会话 cookies。
            ocr (DdddOcr, optional): 可复用的 DdddOcr 对象；显式传入 None 可禁用 OCR。
            timeout (tuple[float, float]): HTTP 连接和读取超时（秒）。
        """
        self.user_agent = user_agent
        self.cookies = cookies
        self.timeout = timeout
        self.s: Session = Session()
        self.s.headers.update(
            {
                "User-Agent": self.user_agent,
                "Cookie": self.cookies,
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
            }
        )
        # Keep requests' default TLS certificate validation enabled.
        self.ocr = ocr_init() if ocr is _MISSING else ocr

    def getCaptcha(self) -> Optional[bytes]:
        """
        获取验证码图片。

        Returns:
            Optional[bytes]: 验证码图片二进制数据，获取失败时返回 None。
        """
        url = self.host + self.api["get"]
        try:
            with self.s.get(
                url,
                params={"t": randint(0, 2_147_483_647)},
                timeout=self.timeout,
            ) as response:
                content_type = response.headers.get("Content-Type", "")
                content_type = content_type.split(";", 1)[0].strip().lower()

                if response.status_code != 200:
                    logger.warning("验证码图片请求失败，HTTP 状态码: {}", response.status_code)
                    return None
                if content_type != "image/png" or not response.content:
                    logger.warning("验证码图片响应为空或格式不正确")
                    return None
                return response.content
        except RequestException as exc:
            logger.warning("获取验证码图片失败: {}", exc)
            return None

    def submitCaptcha(self, cap_token: str) -> bool:
        """
        提交验证码以完成验证。

        Args:
            cap_token (str): 验证码 token。

        Returns:
            bool: 收到 HTTP 302 重定向时返回 True，否则返回 False。
        """
        url = self.host + self.api["submit"]
        try:
            with self.s.get(
                url,
                params={"ucode": cap_token, "app": 0},
                timeout=self.timeout,
                # Requests follows GET redirects by default, hiding the 302
                # status this endpoint uses to signal successful validation.
                allow_redirects=False,
            ) as response:
                return response.status_code == 302
        except RequestException as exc:
            logger.warning("提交验证码失败: {}", exc)
            return False

    def recognition(self, img: bytes) -> str:
        """
        使用 DdddOcr 对验证码图片进行识别。

        Args:
            img (bytes): 验证码图片的二进制数据。

        Returns:
            str: 识别出的验证码字符串。
        """
        if self.ocr is None:
            logger.error("ddddocr 实例未成功初始化，无法执行验证码识别")
            raise RuntimeError("ddddocr is not available")
        return self.ocr.classification(img)

    def try_pass(self) -> bool:
        """
        尝试获取、识别并提交一次验证码。

        Returns:
            bool: 验证成功时返回 True，否则返回 False。
        """
        try:
            cap_img = self.getCaptcha()
            if not cap_img:
                return False
            cap_token = self.recognition(cap_img)
            if not cap_token:
                logger.warning("验证码识别结果为空")
                return False
            return self.submitCaptcha(cap_token)
        except Exception as exc:
            logger.error("验证码自动验证时发生异常: {}", exc)
            return False
