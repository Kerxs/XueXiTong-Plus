# -*- coding: utf-8 -*-
"""Stability: a chapter that throws must not hang the run; network loss waits instead of failing."""
import threading
import unittest
from unittest import mock

import requests

import main
from api import net


class _NoopRateLimiter:
    def limit_rate(self, *args, **kwargs):
        return None


class FlakyChaoxing:
    """get_job_list raises the given exceptions first, then reports an already-empty chapter."""

    def __init__(self, failures):
        self.failures = list(failures)
        self.calls = 0
        self.rate_limiter = _NoopRateLimiter()

    def get_job_list(self, course, point):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return [], {}


def run_processor(chaoxing, max_tries=3, timeout=5.0):
    task = main.ChapterTask(index=0, point={"title": "章节", "has_finished": False}, course={"title": "课程"})
    config = {"speed": 1.0, "jobs": 1, "notopen_action": "retry", "retry_interval": 0.01}
    processor = main.JobProcessor(chaoxing, [task], config)
    processor.max_tries = max_tries
    thread = threading.Thread(target=processor.run, daemon=True)
    thread.start()
    thread.join(timeout)
    return processor, task, thread.is_alive()


class WorkerSurvivesExceptionsTest(unittest.TestCase):
    def setUp(self):
        main.logger.remove()

    def test_unexpected_exception_is_a_counted_retry_not_a_hang(self):
        processor, task, hung = run_processor(FlakyChaoxing([ValueError("坏数据")] * 5), max_tries=3)
        self.assertFalse(hung, "run() hung after a chapter raised (worker thread died)")
        self.assertEqual(task.tries, 3)
        self.assertIn(task, processor.failed_tasks)

    def test_network_outage_waits_and_does_not_use_tries(self):
        chaoxing = FlakyChaoxing([requests.ConnectionError("Network is unreachable")] * 4)
        with mock.patch.object(net, "wait_for_network", return_value=1.0) as waited:
            processor, task, hung = run_processor(chaoxing, max_tries=3)
        self.assertFalse(hung)
        self.assertEqual(waited.call_count, 4)
        self.assertEqual(task.tries, 0)             # the outage did not count against the chapter
        self.assertEqual(processor.failed_tasks, [])
        self.assertEqual(chaoxing.calls, 5)          # 4 outages, then the chapter completed


class WaitForNetworkTest(unittest.TestCase):
    def setUp(self):
        main.logger.remove()

    def test_returns_at_once_when_online(self):
        self.assertEqual(net.wait_for_network(sleep=lambda s: None, check=lambda: True), 0.0)

    def test_backs_off_until_back_online(self):
        states = iter([False, False, False, True])
        sleeps = []
        net.wait_for_network(sleep=sleeps.append, check=lambda: next(states))
        self.assertEqual(len(sleeps), 3)
        self.assertTrue(sleeps[0] < sleeps[1] < sleeps[2] <= 30)

    def test_classifies_errors(self):
        self.assertTrue(net.is_network_error(requests.ConnectionError("x")))
        self.assertTrue(net.is_network_error(requests.Timeout("x")))
        wrapped = RuntimeError("outer")
        wrapped.__cause__ = requests.ConnectionError("inner")
        self.assertTrue(net.is_network_error(wrapped))
        self.assertFalse(net.is_network_error(ValueError("parse")))


if __name__ == "__main__":
    unittest.main()
