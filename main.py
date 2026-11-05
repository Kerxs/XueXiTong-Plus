# -*- coding: utf-8 -*-
import argparse
import configparser
import enum
import os
import sys
import threading
import time
import traceback
import warnings
from dataclasses import dataclass
from typing import Any
from tqdm import tqdm
from api import manual, net, pause, telemetry
from api.answer import Tiku
from api.base import Chaoxing, Account, StudyResult
from api.exceptions import CaptchaBlocked, LoginError, InputFormatError
from api.logger import logger
from api.notification import Notification
from api.live import Live
from api.live_process import LiveProcessor
from api.process import increase_learning_count_for_course

# The phone's Python prints ResourceWarning (unclosed connections) to the run log, in the middle
# of the progress line. They are of no use to users: keep them out on both apps.
warnings.filterwarnings("ignore", category=ResourceWarning)

try:
    from queue import PriorityQueue, ShutDown
except ImportError:
    from queue import PriorityQueue


    class ShutDown(Exception):
        pass


# Exit code for a run that ended on purpose with an explanation (login failed, chapter still failing
# after the re-login): the desktop app must not restart it. Other non-zero codes are unexpected.
EXIT_STOPPED = 2


class RunStopped(Exception):
    """A chapter still failed after the retries, the re-login and the retries after it: stop the run."""


class UserCancelled(Exception):
    """The user chose not to continue at a prompt; exit quietly, it is not an error."""


class ChapterResult(enum.Enum):
    SUCCESS = 0,
    ERROR = 1,
    NOT_OPEN = 2,
    PENDING = 3


def log_error(func):
    def wrapper(*args, **kwargs):
        try:
            func(*args, **kwargs)
        except BaseException as e:
            logger.error(f"Error in thread {threading.current_thread().name}: {e}")
            traceback.print_exception(type(e), e, e.__traceback__)
            raise

    return wrapper


def str_to_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="Samueli924/chaoxing",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("--use-cookies", action="store_true", help="使用cookies登录")

    parser.add_argument(
        "-c", "--config", type=str, default=None, help="使用配置文件运行程序"
    )
    parser.add_argument("-u", "--username", type=str, default=None, help="手机号账号")
    parser.add_argument("-p", "--password", type=str, default=None, help="登录密码")
    parser.add_argument(
        "-l", "--list", type=str, default=None, help="要学习的课程ID列表, 以 , 分隔"
    )
    parser.add_argument(
        "-s", "--speed", type=float, default=1.0, help="视频播放倍速 (默认1, 最大2)"
    )
    parser.add_argument(
        "-j", "--jobs", type=int, default=4, help="同时进行的章节数 (默认4, 如果一个章节有多个任务点，不会限制同时处理任务点的数量)"
    )

    parser.add_argument(
        "-v",
        "--verbose",
        "--debug",
        action="store_true",
        help="启用调试模式, 输出DEBUG级别日志",
    )
    parser.add_argument(
        "-a", "--notopen-action", type=str, default="retry",
        choices=["retry", "ask", "continue"],
        help="遇到关闭任务点时的行为: retry-重试, ask-询问, continue-继续"
    )

    parser.add_argument("--auto-sign", action="store_true", help="自动签到")
    parser.add_argument(
        "--retry-interval", type=float, default=1.0, help="重试等待时间, 单位秒 (默认1.0)"
    )

    parser.add_argument(
        "-lc",
        "--add-learning-count",
        action="store_true",
        help="开启章节学习次数增加模式",
    )
    parser.add_argument(
        "-tc",
        "--target-count",
        type=int,
        default=100,
        help="章节学习次数目标总次数 (默认100)",
    )

    # 在解析之前捕获 -h 的行为
    if len(sys.argv) == 2 and sys.argv[1] in {"-h", "--help"}:
        parser.print_help()
        sys.exit(0)

    return parser.parse_args()


def load_config_from_file(config_path):
    """从配置文件加载设置"""
    from core import secret

    # 账号、密码、TOKEN、API Key 等加密保存（core/secret.py）；读取时解密，旧版明文顺带加密
    try:
        secret.migrate(config_path)
    except OSError:
        pass
    config = secret.read_config(config_path)

    common_config: dict[str, Any] = {}
    tiku_config: dict[str, Any] = {}
    notification_config: dict[str, Any] = {}

    # 检查并读取common节
    if config.has_section("common"):
        common_config = dict(config.items("common"))
        # 处理course_list，将字符串转换为列表
        if "course_list" in common_config and common_config["course_list"]:
            common_config["course_list"] = [item.strip() for item in common_config["course_list"].split(",") if
                                            item.strip()]
        # 处理speed，将字符串转换为浮点数
        if "speed" in common_config:
            common_config["speed"] = float(common_config["speed"])
        if "jobs" in common_config:
            common_config["jobs"] = int(common_config["jobs"])
        # 处理notopen_action，设置默认值为retry
        if "notopen_action" not in common_config:
            common_config["notopen_action"] = "retry"
        if "retry_interval" in common_config:
            common_config["retry_interval"] = float(common_config["retry_interval"])
        else:
            common_config["retry_interval"] = 5.0
        if "work_max_retries" in common_config:
            try:
                common_config["work_max_retries"] = int(common_config["work_max_retries"])
            except ValueError:
                common_config["work_max_retries"] = 3
        else:
            common_config["work_max_retries"] = 3
        if "work_redo_enabled" in common_config:
            common_config["work_redo_enabled"] = str_to_bool(common_config["work_redo_enabled"])
        if "use_cookies" in common_config:
            common_config["use_cookies"] = str_to_bool(common_config["use_cookies"])
        if "add_learning_count" in common_config:
            common_config["add_learning_count"] = str_to_bool(common_config["add_learning_count"])
        if "target_count" in common_config:
            common_config["target_count"] = int(common_config["target_count"])
        if "username" in common_config and common_config["username"] is not None:
            common_config["username"] = common_config["username"].strip()
        if "password" in common_config and common_config["password"] is not None:
            common_config["password"] = common_config["password"].strip()

    # 检查并读取tiku节
    if config.has_section("tiku"):
        tiku_config = dict(config.items("tiku"))
        # 处理数值类型转换
        for key in ["delay", "cover_rate"]:
            if key in tiku_config:
                tiku_config[key] = float(tiku_config[key])

    # 检查并读取notification节
    if config.has_section("notification"):
        notification_config = dict(config.items("notification"))

    return common_config, tiku_config, notification_config


def build_config_from_args(args):
    """从命令行参数构建配置"""
    common_config = {
        "use_cookies": args.use_cookies,
        "username": args.username,
        "password": args.password,
        "course_list": [item.strip() for item in args.list.split(",") if item.strip()] if args.list else None,
        "speed": args.speed or 1.0,
        "jobs": args.jobs,
        "notopen_action": args.notopen_action or "retry",
        "retry_interval": args.retry_interval or 1.0,
        "add_learning_count": args.add_learning_count,
        "target_count": args.target_count,
    }
    return common_config, {}, {}


def init_config():
    """初始化配置"""
    args = parse_args()

    if args.config:
        common_config, tiku_config, notification_config = load_config_from_file(args.config)
    else:
        common_config, tiku_config, notification_config = build_config_from_args(args)
    register_config_secrets(common_config, tiku_config, notification_config)
    return common_config, tiku_config, notification_config, args.config


def register_config_secrets(common_config, tiku_config, notification_config) -> None:
    """Account, keys, tokens and push addresses never appear in logs or push messages (api/logger.redact)."""
    from api.logger import register_secret

    register_secret(common_config.get("username"))
    register_secret(common_config.get("password"))
    for key in ("tokens", "key", "siliconflow_key", "go_authorization"):
        for part in str(tiku_config.get(key) or "").split(","):
            register_secret(part)
    register_secret(notification_config.get("url"))


def init_chaoxing(common_config, tiku_config, config_path=None):
    """初始化超星实例"""
    username = common_config.get("username", "")
    password = common_config.get("password", "")
    use_cookies = common_config.get("use_cookies", False)

    # 如果没有提供用户名密码，从命令行获取
    if (not username or not password) and not use_cookies:
        username = input("请输入你的手机号, 按回车确认\n手机号:")
        password = input("请输入你的密码, 按回车确认\n密码:")

    account = Account(username, password)

    # 设置题库
    tiku = Tiku.get_tiku_from_config(tiku_config, config_path=config_path)  # 载入题库
    tiku.init_tiku()  # 初始化题库

    # 获取查询延迟设置

    # 检查大模型连接（如果使用的是大模型题库）
    # 根据配置文件中的 provider 判断是否为大模型题库
    provider = tiku_config.get('provider', '')
    provider_list = [name.strip() for name in provider.split(',') if name.strip()]
    if any(name in ['AI', 'SiliconFlow'] for name in provider_list):
        check_connection = tiku_config.get('check_llm_connection', 'true').lower() == 'true'
        if check_connection:
            logger.info(f'正在验证大模型配置 (provider={provider})...')
            if not tiku.check_llm_connection():
                logger.error('大模型连接检查失败')
                choice = input('大模型连接检查失败，无法准确答题，是否继续运行？(Y/n): ').strip().lower()
                # 直接回车默认继续运行
                if choice not in ('', 'y', 'yes'):
                    raise UserCancelled('大模型连接检查未通过，已按你的选择停止运行。请在 设置 → 高级选项 → 答题来源 中检查接口地址、API Key 和模型名称')
                logger.info('用户选择继续运行...')

    query_delay = tiku_config.get("delay", 0)

    # 章节检测答错后允许的最大重做次数（答错时反馈给AI并重新提交，直到全部正确）
    work_max_retries = common_config.get("work_max_retries", 3)

    # 是否允许自动重做(默认false: 仅检查并记录成绩, 适用于只允许作答一次的课程)
    work_redo_enabled = common_config.get("work_redo_enabled", True)

    # 实例化超星API
    chaoxing = Chaoxing(
        account=account,
        tiku=tiku,
        query_delay=query_delay,
        work_max_retries=work_max_retries,
        work_redo_enabled=work_redo_enabled,
    )

    return chaoxing


AUTOMATED_JOB_TYPES = ("video", "workid")
# 课件 / 文档 (设置 → 自动完成): opened once so 学习通 records them; main() sets it from the config.
AUTO_DOCUMENTS = True


def _automated(job: dict) -> bool:
    kind = job.get("type")
    return kind in AUTOMATED_JOB_TYPES or (kind == "document" and AUTO_DOCUMENTS)


def process_job(chaoxing: Chaoxing, course: dict, job: dict, job_info: dict, speed: float,
                point: dict | None = None) -> StudyResult:
    """处理单个任务点：自动完成视频（含音频）和章节检测，其他内容提醒用户手动完成"""
    # 桌面版暂停时，不开始新的任务点
    pause.wait_if_paused()
    if not _automated(job):
        # 阅读、直播、问卷、讨论等（以及关闭了自动完成的课件）：通知 / 界面提示用户手动完成，不重试
        manual.report(course, point or {}, job)
        return StudyResult.SUCCESS
    # 视频任务
    if job["type"] == "video":
        logger.trace(f"识别到视频任务, 任务章节: {course['title']} 任务ID: {job['jobid']}")
        # 音频和视频的任务点类型都是 video：按任务卡片（播放模块 / 文件名）判断是哪一种。
        # 判断得出时只按这一种处理，不再“视频失败就当音频再报一遍”（视频按音频上报平台不会确认，
        # 还可能触发验证码）；卡片看不出来时才沿用原来的先视频、再音频。
        media = job.get("media", "")
        if media in ("Video", "Audio"):
            video_result = chaoxing.study_video(course, job, job_info, _speed=speed, _type=media)
        else:
            video_result = chaoxing.study_video(
                course, job, job_info, _speed=speed, _type="Video"
            )
            if video_result.is_failure():
                logger.warning("无法从任务卡片判断是视频还是音频，视频方式失败，正在尝试按音频处理")
                video_result = chaoxing.study_video(
                    course, job, job_info, _speed=speed, _type="Audio")
        if video_result.is_failure():
            logger.warning(
                f"出现异常任务 -> 任务章节: {course['title']} 任务ID: {job['jobid']}, 已跳过"
            )
        return video_result
    # 文档任务
    elif job["type"] == "document":
        logger.trace(f"识别到文档任务, 任务章节: {course['title']} 任务ID: {job['jobid']}")
        result = chaoxing.study_document(course, job)
        if result.is_failure():
            # 打开失败也不让章节一直重试：提醒用户自己点开
            logger.warning(f"课件「{job.get('name', '')}」未能自动完成，已加入需要手动完成的列表")
            manual.report(course, point or {}, job)
            return StudyResult.SUCCESS
        logger.info(f"已完成{job.get('file_label') or '课件'}: {job.get('name', '')}")
        return result
    # 测验任务
    elif job["type"] == "workid":
        logger.trace(f"识别到章节检测任务, 任务章节: {course['title']}")
        result = chaoxing.study_work(course, job, job_info)
        if result == StudyResult.NEEDS_USER:
            # 没有题目 / 已截止：提醒用户去看一下，不算失败，不重试（以前会一直重试直到停止运行）
            manual.report(course, point or {}, {**job, "card_type": f"workid-{job.get('work_problem', 'empty')}"})
            return StudyResult.SUCCESS
        return result
    # 阅读任务
    elif job["type"] == "read":
        logger.trace(f"识别到阅读任务, 任务章节: {course['title']}")
        return chaoxing.study_read(course, job, job_info)
    # 直播任务
    elif job["type"] == "live":
        logger.trace(f"识别到直播任务, 任务章节: {course['title']} 任务ID: {job['jobid']}")
        try:
            # 准备直播所需参数
            defaults = {
                "userid": chaoxing.get_uid(),
                "clazzId": course.get("clazzId"),
                "knowledgeid": job_info.get("knowledgeid")
            }

            # 创建直播对象
            live = Live(
                attachment=job,
                defaults=defaults,
                course_id=course.get("courseId")
            )

            # 启动直播处理线程
            thread = threading.Thread(
                target=LiveProcessor.run_live,
                args=(live, speed),
                daemon=True
            )
            thread.start()
            thread.join()  # 等待直播处理完成
            return StudyResult.SUCCESS
        except Exception as e:
            logger.error(f"处理直播任务时出错: {str(e)}")
            return StudyResult.ERROR

    logger.error(f"未知任务类型: {job['type']}")
    return StudyResult.ERROR


# 验证码过不去时：等多久再重新登录、每次运行最多重新开始几次（之后提醒用户手动处理这个视频）
CAPTCHA_COOLDOWN = 30
MAX_CAPTCHA_RESTARTS = 3


@dataclass
class ChapterTask:
    index: int
    point: dict[str, Any]
    course: dict[str, Any]
    result: ChapterResult = ChapterResult.PENDING
    tries: int = 0
    relogged: bool = False      # already retried after logging in again
    last_error: str = ""

    def __lt__(self, other):
        """比较两个任务的索引大小，用于优先级队列排序."""
        if not isinstance(other, ChapterTask):
            return NotImplemented
        return self.index < other.index


class JobProcessor:
    def __init__(self, chaoxing: Chaoxing, tasks: list[ChapterTask], config: dict[str, Any]):
        """初始化任务处理器."""
        if "jobs" not in config or not config["jobs"]:
            config["jobs"] = 4

        self.chaoxing = chaoxing
        self.speed = config["speed"]
        self.max_tries = 5
        self.tasks = tasks
        self.failed_tasks: list[ChapterTask] = []
        self.task_queue: PriorityQueue[ChapterTask] = PriorityQueue()
        self.retry_queue: PriorityQueue[ChapterTask] = PriorityQueue()
        self.wait_queue: PriorityQueue[ChapterTask] = PriorityQueue()
        self.threads: list[threading.Thread] = []
        self.worker_num = config["jobs"]
        self.config = config
        self.retry_interval = config.get("retry_interval", 1.0)
        # 重试 max_tries 次仍失败：重新登录、重新读取章节，再试 max_tries 次；还不行就停止运行
        self.stop_reason = ""
        self._relogin_lock = threading.Lock()
        self._last_relogin = 0.0
        self._captcha_restarts = 0

    def run(self):
        for task in self.tasks:
            self.task_queue.put(task)

        for i in range(self.worker_num):
            thread = threading.Thread(target=self.worker_thread, daemon=True)
            self.threads.append(thread)
            thread.start()

        threading.Thread(target=self.retry_thread, daemon=True).start()

        # task_queue.join(), but give up waiting once the run has to stop
        while not self.stop_reason:
            with self.task_queue.all_tasks_done:
                if not self.task_queue.unfinished_tasks:
                    break
                self.task_queue.all_tasks_done.wait(timeout=0.5)
        time.sleep(0.5)
        if hasattr(self.task_queue, "shutdown"):
            self.task_queue.shutdown()
        if self.stop_reason:
            raise RunStopped(self.stop_reason)

    def _relogin(self, force: bool = False) -> str:
        """Log in again (once for all workers within a minute; ``force``: within 20 s).
        Returns why it failed, "" when it worked."""
        with self._relogin_lock:
            if time.time() - self._last_relogin < (20 if force else 60):
                return ""           # another chapter just did it
            logger.warning("多次重试失败，正在重新登录学习通…")
            try:
                state = self.chaoxing.login(login_with_cookies=str_to_bool(self.config.get("use_cookies", False)))
            except Exception as e:
                return f"重新登录时出错：{type(e).__name__}: {e}"
            if not state.get("status"):
                return f"重新登录失败：{state.get('msg') or '原因未知'}"
            self._last_relogin = time.time()
            telemetry.count("relogin")
            logger.info("已重新登录")
            return ""

    def _refresh_point(self, task: ChapterTask) -> None:
        """Read the course's chapter list again after logging in, and use the fresh entry for this chapter."""
        try:
            points = self.chaoxing.get_course_point(
                task.course["courseId"], task.course["clazzId"], task.course["cpi"])["points"]
        except Exception as e:
            logger.warning("重新读取章节列表失败，沿用原来的章节信息: {}: {}", type(e).__name__, e)
            return
        fresh = next((p for p in points if p.get("id") == task.point.get("id")), None)
        if fresh:
            task.point = fresh

    def _stop(self, task: ChapterTask, why: str) -> None:
        telemetry.count("run.stopped")
        name = f"{task.course['title']} - {task.point['title']}"
        self.stop_reason = (
            f"章节“{name}”重试 {self.max_tries} 次失败，重新登录后又重试 {self.max_tries} 次仍然失败，已停止运行。"
            if not why else f"章节“{name}”重试 {self.max_tries} 次失败，{why}，已停止运行。"
        )
        if task.last_error:
            self.stop_reason += f"最后一次错误：{task.last_error}。"
        self.stop_reason += ("可能是学习通接口有变化、账号被限制，或这一章需要手动处理。"
                             "请先在学习通里打开这一章看看能否正常学习，稍后再开始运行。")

    def _captcha_restart(self, task: ChapterTask, exc: CaptchaBlocked) -> None:
        """A captcha that could not be passed: wait, log in again and start the chapter over
        (not counted as a try). After MAX_CAPTCHA_RESTARTS in a run the video is left for the user."""
        self._captcha_restarts += 1
        telemetry.count("captcha.restart")
        name = f"{task.course['title']} - {task.point['title']}"
        if self._captcha_restarts > MAX_CAPTCHA_RESTARTS:
            logger.warning(f"本次运行已因验证码重新开始 {MAX_CAPTCHA_RESTARTS} 次，跳过「{exc.job_name}」，请到学习通打开播放一下")
            manual.report(task.course, task.point, {"type": "other", "card_type": "captcha",
                                                     "jobid": exc.job_name, "name": exc.job_name})
            self.task_queue.task_done()
            return
        logger.warning(f"遇到验证码且无法通过，{CAPTCHA_COOLDOWN} 秒后重新登录并重新开始本章: {name}"
                       f"（第 {self._captcha_restarts}/{MAX_CAPTCHA_RESTARTS} 次）")
        waited = 0
        while waited < CAPTCHA_COOLDOWN and not self.stop_reason:
            pause.wait_if_paused()
            time.sleep(1)
            waited += 1
        problem = self._relogin(force=True)
        if problem:
            self.failed_tasks.append(task)
            self._stop(task, problem)
            self.task_queue.task_done()
            return
        self.retry_queue.put(task)

    def _give_up_or_relogin(self, task: ChapterTask) -> None:
        """task failed max_tries times: log in again and retry it, or stop the run."""
        if task.relogged:
            self.failed_tasks.append(task)
            self._stop(task, "")
            self.task_queue.task_done()
            return
        problem = self._relogin()
        if problem:
            self.failed_tasks.append(task)
            self._stop(task, problem)
            self.task_queue.task_done()
            return
        self._refresh_point(task)
        task.relogged = True
        task.tries = 0
        logger.info("重新登录后再试 {} 次: {} - {}", self.max_tries, task.course["title"], task.point["title"])
        self.retry_queue.put(task)

    @log_error
    def worker_thread(self):
        while True:
            try:
                task = self.task_queue.get()
            except ShutDown:
                logger.info("Queue shut down")
                return
            if self.stop_reason:        # the run is stopping: start nothing new
                self.task_queue.task_done()
                return

            try:
                task.result = process_chapter(self.chaoxing, task.course, task.point, self.speed)
            except CaptchaBlocked as e:
                self._captcha_restart(task, e)
                continue
            except Exception as e:
                # An exception used to end this worker thread, leaving its chapter unfinished in the
                # queue: task_queue.join() then waited forever and the run hung.
                if net.is_network_error(e):
                    net.wait_for_network()
                    # A network outage is not the chapter's fault: retry it without using a try.
                    self.retry_queue.put(task)
                    continue
                logger.error("处理章节出错: {} - {}: {}: {}", task.course["title"], task.point["title"],
                             type(e).__name__, e)
                task.last_error = f"{type(e).__name__}: {e}"
                task.result = ChapterResult.ERROR

            match task.result:
                case ChapterResult.SUCCESS:
                    logger.debug("Task success: {} - {}", task.course["title"], task.point["title"])
                    self.task_queue.task_done()
                    logger.debug(f"unfinished task: {self.task_queue.unfinished_tasks}")

                case ChapterResult.NOT_OPEN:
                    if self.config["notopen_action"] == "continue":
                        logger.warning("章节未开启: {} - {}, 正在跳过", task.course["title"], task.point["title"])
                        self.task_queue.task_done()
                        continue

                    task.tries += 1
                    if task.tries >= self.max_tries:
                        logger.error(
                            "章节未开启: {} - {} 可能由于上一章节的章节检测未完成, 也可能由于该章节因为时效已关闭，"
                            "请手动检查完成并提交再重试。或者在配置中配置(自动跳过关闭章节/开启题库并启用提交)"
                            , task.course["title"], task.point["title"])
                        self.task_queue.task_done()
                        continue

                    # self.wait_queue.put(task)
                    self.retry_queue.put(task)

                case ChapterResult.ERROR:
                    task.tries += 1
                    telemetry.count("chapter.retry")
                    logger.warning("重试任务 {} - {} ({}/{} 次尝试)", task.course["title"], task.point["title"],
                                   task.tries,
                                   self.max_tries)
                    if task.tries >= self.max_tries:
                        logger.error("任务重试次数达到上限: {} - {}", task.course["title"], task.point["title"])
                        self._give_up_or_relogin(task)
                        continue
                    self.retry_queue.put(task)

                case _:
                    logger.error("任务 {} 的状态无效 {}", task.result, task.point["title"])
                    self.failed_tasks.append(task)
                    self.task_queue.task_done()

    @log_error
    def retry_thread(self):
        try:
            while True:
                task = self.retry_queue.get()
                # 暂停时不把未开放 / 失败的章节放回队列，否则会一直重试刷日志
                pause.wait_if_paused()
                self.task_queue.put(task)
                # task_done is not called when a task failed and needs to be retried so if is reinserted into the queue,
                # the task num will increase by one and become more than the real task number
                self.task_queue.task_done()
                time.sleep(self.retry_interval)
        except ShutDown:
            pass


def unfinished_chapters(chaoxing: Chaoxing, courses: list[dict]) -> tuple[list[ChapterTask], dict[str, tuple[int, int]]]:
    """Read every course's chapter list again: chapters 学习通 does not show as finished, and per course
    (finished, total). A course whose list cannot be read is left out (no guess)."""
    left: list[ChapterTask] = []
    stats: dict[str, tuple[int, int]] = {}
    for course in courses:
        try:
            points = chaoxing.get_course_point(course["courseId"], course["clazzId"], course["cpi"])["points"]
        except Exception as e:
            logger.debug(f"重新读取章节列表失败: {course.get('title', '')}: {e}")
            continue
        done = sum(1 for p in points if p.get("has_finished"))
        stats[course.get("title", "")] = (done, len(points))
        left += [ChapterTask(point=p, index=i, course=course) for i, p in enumerate(points) if not p.get("has_finished")]
    return left, stats


def completion_report(stats: dict[str, tuple[int, int]]) -> str:
    """"完成情况：高等数学 30/32 章、C语言 12/12 章（共 95%）" ("" when nothing was read)."""
    if not stats:
        return ""
    done = sum(d for d, _ in stats.values())
    total = sum(t for _, t in stats.values())
    parts = "、".join(f"{name} {d}/{t} 章" for name, (d, t) in stats.items())
    rate = f"（共 {done * 100 // total}%）" if total else ""
    return f"完成情况：{parts}{rate}"


def process_chapter(chaoxing: Chaoxing, course: dict[str, Any], point: dict[str, Any], speed: float) -> ChapterResult:
    """处理单个章节"""
    # 暂停时不再读取章节（读取任务点本身就是一次请求）
    pause.wait_if_paused()
    logger.info(f'当前章节: {point["title"]}')
    if point["has_finished"]:
        logger.info(f'章节：{point["title"]} 已完成所有任务点')
        return ChapterResult.SUCCESS

    # 随机等待，避免请求过快
    chaoxing.rate_limiter.limit_rate(random_time=True, random_min=0, random_max=0.2)

    # 获取当前章节的所有任务点
    job_info = None
    jobs, job_info = chaoxing.get_job_list(course, point)

    # 发现未开放章节, 根据配置处理
    if job_info.get("notOpen", False):
        return ChapterResult.NOT_OPEN

    # 已经默认处理空任务，此处不需要判断
    if not jobs:
        pass

    job_results: list[StudyResult] = []
    for job in jobs:
        result = process_job(chaoxing, course, job, job_info, speed, point)
        job_results.append(result)
        if not _automated(job):
            telemetry.count("other.manual")
        else:
            telemetry.count(f"{job.get('type')}.{'fail' if result.is_failure() else 'ok'}")

    for result in job_results:
        if result.is_failure():
            return ChapterResult.ERROR

    return ChapterResult.SUCCESS


def process_course(chaoxing: Chaoxing, course: dict[str, Any], config: dict):
    """处理单个课程"""
    logger.info(f"开始学习课程: {course['title']}")

    # 获取当前课程的所有章节
    point_list = chaoxing.get_course_point(
        course["courseId"], course["clazzId"], course["cpi"]
    )

    # 为了支持课程任务回滚, 采用下标方式遍历任务点

    _old_format_sizeof = tqdm.format_sizeof
    tqdm.format_sizeof = format_time

    tasks = []

    for i, point in enumerate(point_list["points"]):
        task = ChapterTask(point=point, index=i, course=course)
        tasks.append(task)
    p = JobProcessor(chaoxing, tasks, config)
    p.run()

    tqdm.format_sizeof = _old_format_sizeof


def filter_courses(all_course, course_list):
    """过滤要学习的课程"""
    if not course_list:
        # 手动输入要学习的课程ID列表
        print("*" * 10 + "课程列表" + "*" * 10)
        for course in all_course:
            print(f"ID: {course['courseId']} 班级ID: {course['clazzId']} 课程名: {course['title']}")
        print("*" * 28)
        print("提示: 同一 courseId 下若存在多个班级, 将分别完成。")
        try:
            course_list = input(
                "请输入想要学习的课程列表,以逗号分隔,例: 2151141,189191,198198\n"
            ).split(",")
        except Exception as e:
            raise InputFormatError("输入格式错误") from e

    # 筛选需要学习的课程
    course_task = []
    seen_keys = set()
    for course in all_course:
        key = (course["courseId"], course["clazzId"])
        if course["courseId"] in course_list and key not in seen_keys:
            course_task.append(course)
            seen_keys.add(key)
    
    # 如果没有指定课程，则学习所有课程
    if not course_task:
        course_task = all_course

    return course_task


def format_time(num, suffix='', divisor=''):
    total_time = round(num)
    sec = total_time % 60
    mins = (total_time % 3600) // 60
    hrs = total_time // 3600

    if hrs > 0:
        return f"{hrs:02d}:{mins:02d}:{sec:02d}"

    return f"{mins:02d}:{sec:02d}"


def main():
    """主程序入口"""
    try:
        # 初始化配置
        common_config, tiku_config, notification_config, config_path = init_config()

        # 倍速已失效：视频统一按 1 倍速观看（配置里的 speed 不再生效）
        if float(common_config.get("speed", 1.0) or 1.0) != 1.0:
            logger.warning("视频倍速设置已失效，统一按 1 倍速观看")
        common_config["speed"] = 1.0
        common_config["notopen_action"] = common_config.get("notopen_action", "retry")
        
        telemetry.configure(str_to_bool(common_config.get("telemetry", False)), os.getcwd())
        global AUTO_DOCUMENTS
        AUTO_DOCUMENTS = str_to_bool(common_config.get("auto_documents", True))
        auto_homework = str_to_bool(common_config.get("auto_homework", True))
        homework_submit = str_to_bool(common_config.get("homework_submit", True))
        watch_activities = str_to_bool(common_config.get("watch_activities", True))

        # 初始化增加章节学习次数配置
        add_learning_count = str_to_bool(common_config.get("add_learning_count", False))
        target_count = int(common_config.get("target_count", 100))
        
        # 初始化超星实例
        chaoxing = init_chaoxing(common_config, tiku_config, config_path=config_path)

        # 设置外部通知
        notification = Notification()
        notification.config_set(notification_config)
        notification = notification.get_notification_from_config()
        notification.init_notification()
        manual.reset()
        manual.set_notifier(notification)

        # 检查当前登录状态（启动时没有网络：等网络恢复后重试，而不是直接退出）
        for attempt in range(3):
            try:
                _login_state = chaoxing.login(login_with_cookies=common_config.get("use_cookies", False))
                break
            except Exception as e:
                if attempt == 2 or not net.is_network_error(e):
                    raise
                net.wait_for_network()
        if not _login_state["status"]:
            raise LoginError(_login_state["msg"])

        # 获取所有的课程列表
        all_course = chaoxing.get_course_list()

        # 过滤要学习的课程
        course_task = filter_courses(all_course, common_config.get("course_list"))

        # 开始学习
        logger.info(f"课程列表过滤完毕, 当前课程任务数量: {len(course_task)}")

        _old_format_sizeof = tqdm.format_sizeof
        tqdm.format_sizeof = format_time

        tasks = []
        for course in course_task:
            logger.info(f"正在读取课程章节: {course['title']}")
            point_list = chaoxing.get_course_point(
                course["courseId"], course["clazzId"], course["cpi"]
            )
            for i, point in enumerate(point_list["points"]):
                task = ChapterTask(point=point, index=i, course=course)
                tasks.append(task)

        # 全局并发执行所有课程的任务点
        p = JobProcessor(chaoxing, tasks, common_config)
        p.run()

        # 补漏：重新读取章节列表，学习通仍未显示完成的章节再处理一遍
        # （平台确认得晚、偶发失败、上一轮漏掉的任务点）。只有文字、问卷、讨论等需要手动的章节
        # 会一直显示未完成，再处理一遍也只是重复提醒，不会出错。
        leftover, _ = unfinished_chapters(chaoxing, course_task)
        if leftover:
            logger.info(f"补漏：还有 {len(leftover)} 个章节没有显示完成，再处理一遍")
            # 还没开放的章节这一遍直接跳过（第一遍已经按设置等待和重试过）
            JobProcessor(chaoxing, leftover, {**common_config, "notopen_action": "continue"}).run()

        tqdm.format_sizeof = _old_format_sizeof

        # 作业和课堂活动不在章节里：章节处理完后逐门课程查看
        if auto_homework or watch_activities:
            from api import homework

            totals = {"submitted": 0, "saved": 0, "skipped": 0, "failed": 0}
            for course in course_task:
                pause.wait_if_paused()
                if auto_homework:
                    for key, value in homework.run_homework(chaoxing, course, homework_submit).items():
                        totals[key] += value
                        telemetry.count(f"homework.{key}", value)
                if watch_activities:
                    homework.watch_activities(chaoxing, course)
            if auto_homework and any(totals.values()):
                logger.info(f"作业：提交 {totals['submitted']} 份，只保存 {totals['saved']} 份，"
                            f"已交过 {totals['skipped']} 份，未能完成 {totals['failed']} 份")

        # 完成率：最后再读一次章节列表（每门课一次请求）
        _, stats = unfinished_chapters(chaoxing, course_task)
        telemetry.count("chapters.done", sum(d for d, _ in stats.values()))
        telemetry.count("chapters.total", sum(t for _, t in stats.values()))
        report = completion_report(stats)
        if report:
            logger.info(report)
        pending = manual.summary()
        tail = f"\n{report}" if report else ""
        if pending:
            logger.warning(f"自动任务已处理完；{pending}")
            notification.send(f"chaoxing : 自动任务已处理完；{pending}{tail}")
        else:
            logger.info("所有课程学习任务已完成")
            notification.send(f"chaoxing : 所有课程学习任务已完成{tail}")

        # 刷课完成后，如果开启了增加章节学习次数，则执行
        if add_learning_count:
            logger.info("刷课完成，开始增加章节学习次数...")
            common_config["target_count"] = target_count
            for course in course_task:
                increase_learning_count_for_course(chaoxing, course, common_config)
            logger.info("所有课程章节学习次数增加完成")
            notification.send("chaoxing : 所有课程章节学习次数增加完成")
        
    except UserCancelled as e:
        logger.warning(str(e))
        sys.exit(0)
    except RunStopped as e:
        # Expected: one clear explanation, no traceback.
        logger.error(str(e))
        try:
            notification.send(f"chaoxing : {e}")
        except Exception:
            pass
        sys.exit(EXIT_STOPPED)
    except LoginError as e:
        # Expected (wrong password, expired cookies): one clear line, no traceback.
        logger.error(f"登录失败：{e}。请检查账号密码，或重新导入 cookies 后再试")
        try:
            notification.send(f"chaoxing : 登录失败：{e}")
        except Exception:
            pass
        sys.exit(EXIT_STOPPED)
    except SystemExit as e:
        if e.code != 0:
            logger.error(f"错误: 程序异常退出, 返回码: {e.code}")
        sys.exit(e.code)
    except KeyboardInterrupt as e:
        logger.error(f"错误: 程序被用户手动中断, {e}")
    except BaseException as e:
        logger.error(f"错误: {type(e).__name__}: {e}")
        logger.error(traceback.format_exc())
        try:
            notification.send(f"chaoxing : 出现错误 {type(e).__name__}: {e}\n{traceback.format_exc()}")
        except Exception:
            pass  # 如果通知发送失败，忽略异常
        raise e
    finally:
        telemetry.save()


if __name__ == "__main__":
    main()
