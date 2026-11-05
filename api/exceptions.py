try:
    from requests.exceptions import JSONDecodeError
except ImportError:
    from json import JSONDecodeError


class LoginError(Exception):
    def __init__(self, *args: object):
        super().__init__(*args)


class InputFormatError(Exception):
    def __init__(self, *args: object):
        super().__init__(*args)


class MaxRollBackExceeded(Exception):
    def __init__(self, *args: object):
        super().__init__(*args)


class MaxRetryExceeded(Exception):
    def __init__(self, *args: object):
        super().__init__(*args)


class CaptchaBlocked(Exception):
    """A video report hit a captcha that could not be passed 3 times (e.g. its image would not even load).

    The chapter runner (main.JobProcessor) waits 30 s, logs in again and starts the chapter over.
    """

    def __init__(self, job_name: str = ""):
        super().__init__(f"验证码无法通过: {job_name}")
        self.job_name = job_name


class FontDecodeError(Exception):
    def __init__(self, *args: object):
        super().__init__(*args)
