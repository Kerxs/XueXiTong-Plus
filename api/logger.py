import os
import sys

from loguru import logger
from tqdm import tqdm

tqdm_stream = sys.stderr

# 日志缓冲区，用于在手动答题时缓存后台日志，答题结束后统一输出
log_buffer = []
MAX_LOG_BUFFER_SIZE = 1000

# ---- 敏感信息脱敏 ----------------------------------------------------------
# 配置加载后登记密码、API Key、TOKEN、推送地址等（main.load_config_from_file），
# 之后所有日志（控制台和 chaoxing.log）以及推送消息里出现时都替换为 ***。
_secrets: set[str] = set()
_PLACEHOLDERS = {"xxx", "xxxxxx", "none", "null", "true", "false"}


def register_secret(value) -> None:
    text = str(value or "").strip()
    if len(text) >= 4 and text.lower() not in _PLACEHOLDERS:
        _secrets.add(text)


def redact(text: str) -> str:
    if not _secrets or not text:
        return text
    for secret in sorted(_secrets, key=len, reverse=True):
        if secret in text:
            text = text.replace(secret, "***")
    return text


def _patch(record) -> None:
    record["message"] = redact(record["message"])


def can_enqueue() -> bool:
    """loguru's enqueue=True needs multiprocessing (named semaphores, sem_open).

    Android (Chaquopy) has no sem_open, so creating the queue fails and importing this
    module used to crash every run on the phone. Without enqueue the sink is still
    thread-safe (loguru locks around each write); only the background queue is skipped.
    """
    try:
        import multiprocessing

        multiprocessing.SimpleQueue()
        return True
    except Exception:  # ImportError / OSError: [Errno 38] Function not implemented
        return False


def tqdm_sink(msg):
    manual_locked = False
    try:
        # 动态获取 api.answer 模块中的 TikuManual 锁，避免循环导入
        if 'api.answer' in sys.modules:
            TikuManual = getattr(sys.modules['api.answer'], 'TikuManual', None)
            if TikuManual and getattr(TikuManual, '_manual_lock', None):
                manual_locked = TikuManual._manual_lock.locked()
    except (AttributeError, KeyError, ImportError):
        pass

    if manual_locked:
        if len(log_buffer) < MAX_LOG_BUFFER_SIZE:
            log_buffer.append(msg)
    else:
        if log_buffer:
            for buffered_msg in log_buffer:
                tqdm.write(buffered_msg.rstrip(), file=tqdm_stream)
            log_buffer.clear()
        tqdm.write(msg.rstrip(), file=tqdm_stream)
    tqdm_stream.flush()


logger.remove()
logger.configure(patcher=_patch)
logger.add(tqdm_sink, colorize=True, enqueue=can_enqueue())
# The log file: DEBUG and up. TRACE lines hold whole 学习通 pages (names, course content) and used
# to make up two thirds of every file; set CHAOXING_TRACE=1 to write them when a page has to be
# looked at. Old files used to be kept for ever.
#
# Kept: LOG_DAYS days, so a problem from a few weeks ago can still be looked up — but never more
# than LOG_FILES_MAX files (10 MB each), whatever their age, so the folder cannot grow without end.
LOG_DAYS = 30
LOG_FILES_MAX = 30


def _expired_logs(files: list) -> None:
    """loguru retention: called with every log file when a new one is started."""
    import time

    limit = time.time() - LOG_DAYS * 86400

    def modified(path) -> float:
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0.0

    newest_first = sorted(files, key=modified, reverse=True)
    for index, path in enumerate(newest_first):
        if index >= LOG_FILES_MAX or modified(path) < limit:
            try:
                os.remove(path)
            except OSError:
                pass


logger.add("chaoxing.log", rotation="10 MB", retention=_expired_logs,
           level="TRACE" if os.environ.get("CHAOXING_TRACE") == "1" else "DEBUG")
