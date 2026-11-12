"""The Android app's Python side (android/app/src/main/python), run on desktop Python."""

import configparser
import http.server
import importlib
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANDROID_PY = ROOT / "android" / "app" / "src" / "main" / "python"


def load_bridge():
    sys.path.insert(0, str(ANDROID_PY))
    try:
        return importlib.import_module("xxtplus_android")
    finally:
        sys.path.remove(str(ANDROID_PY))


def load_openai_shim():
    """The shim under its own name, so the real openai package (desktop) is untouched."""
    spec = importlib.util.spec_from_file_location("openai_shim", ANDROID_PY / "openai" / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SettingsTest(unittest.TestCase):
    def setUp(self):
        self.bridge = load_bridge()
        self.tmp = tempfile.TemporaryDirectory()
        self.config = str(Path(self.tmp.name) / "config.ini")
        self.template = str(ROOT / "config_template.ini")

    def tearDown(self):
        self.tmp.cleanup()

    def test_schema_has_only_cloud_model_settings(self):
        schema = json.loads(self.bridge.settings_schema())
        ids = [f["id"] for g in schema["groups"] for f in g["fields"]]
        types_ = [f["type"] for g in schema["groups"] for f in g["fields"]]
        self.assertNotIn("localmodels", types_)
        self.assertNotIn("tiku.endpoint", ids)
        self.assertNotIn("tiku.http_proxy", ids)
        self.assertIn("aiprovider", types_)
        self.assertIn("notification.provider", ids)          # 推送服务 is part of the guide
        text = json.dumps(schema, ensure_ascii=False)
        self.assertNotIn("本机模型", text)
        self.assertNotIn("127.0.0.1", json.dumps([f for g in schema["groups"] if g["id"] == "tiku" for f in g["fields"]],
                                                  ensure_ascii=False))
        notify = next(f for g in schema["groups"] for f in g["fields"] if f["id"] == "notification.provider")
        self.assertEqual(notify["options"][0]["value"], "Local")   # 本机通知 first on the phone
        self.assertTrue(all(p["endpoint"].startswith("https://") for p in schema["aiProviders"]))

    def test_template_placeholders_load_as_empty(self):
        values = json.loads(self.bridge.load_settings(self.config, self.template))
        self.assertEqual(values["common.username"], "")
        self.assertEqual(values["common.course_list"], "")
        self.assertEqual(values["tiku.cover_rate"], "0.75")

    def test_system_notification_is_the_default_once(self):
        import configparser

        def provider():
            return json.loads(self.bridge.load_settings(self.config, self.template))["notification.provider"]

        self.assertEqual(provider(), "Local")                    # the template: ServerChan without an address
        for name, url in (("", ""), ("Bark", "")):               # nothing chosen / a service with no address
            cfg = configparser.ConfigParser(interpolation=None)
            cfg.read(self.template, encoding="utf-8")
            cfg["notification"]["provider"], cfg["notification"]["url"] = name, url
            with open(self.config, "w", encoding="utf-8") as fp:
                cfg.write(fp)
            self.assertEqual(provider(), "Local", name)
        # the user turns pushes off and saves: that choice is kept from now on
        values = json.loads(self.bridge.load_settings(self.config, self.template))
        values["notification.provider"] = ""
        self.bridge.save_settings(self.config, self.template, json.dumps(values))
        self.assertEqual(provider(), "")

    def test_save_round_trip_and_no_proxy(self):
        values = json.loads(self.bridge.load_settings(self.config, self.template))
        values.update({"common.username": "13800000000", "common.password": "pw", "common.speed": "1.5",
                       "tiku.provider": "AI", "tiku.endpoint": "https://api.deepseek.com/v1",
                       "tiku.key": "sk-test", "tiku.model": "deepseek-chat", "tiku.http_proxy": "http://x:1"})
        self.bridge.save_settings(self.config, self.template, json.dumps(values))
        config = configparser.ConfigParser()
        config.read(self.config, encoding="utf-8")
        # stored encrypted (core/secret.py), read back decrypted
        self.assertTrue(config["common"]["username"].startswith("enc:v1:"))
        self.assertNotIn("sk-test", open(self.config, encoding="utf-8").read())
        self.assertEqual(json.loads(self.bridge.load_settings(self.config, self.template))["common.username"],
                         "13800000000")
        self.assertEqual(config["common"]["speed"], "1")  # 倍速已失效：always 1
        self.assertEqual(config["tiku"]["provider"], "AI")
        self.assertEqual(config["tiku"]["http_proxy"], "")
        again = json.loads(self.bridge.load_settings(self.config, self.template))
        self.assertEqual(again["tiku.model"], "deepseek-chat")

    def test_setup_problem_requires_a_cloud_company(self):
        base = {"common.username": "1", "common.password": "2", "tiku.provider": "AI",
                "tiku.model": "m", "tiku.key": "k"}
        local = {**base, "tiku.endpoint": "http://127.0.0.1:8080/v1"}
        custom = {**base, "tiku.endpoint": "https://example.com/v1"}
        cloud = {**base, "tiku.endpoint": "https://api.deepseek.com/v1"}
        self.assertIn("服务商", self.bridge.setup_problem(json.dumps(local)))
        self.assertIn("服务商", self.bridge.setup_problem(json.dumps(custom)))
        self.assertEqual(self.bridge.setup_problem(json.dumps(cloud)), "")
        self.assertIn("API Key", self.bridge.setup_problem(json.dumps({**cloud, "tiku.key": ""})))
        self.assertIn("账号", self.bridge.setup_problem(json.dumps({**cloud, "common.username": ""})))
        # a saved 自定义服务商 counts as chosen; a local address never does on the phone
        saved = json.dumps([{"name": "中转", "endpoint": "https://example.com/v1"},
                            {"name": "本机", "endpoint": "http://127.0.0.1:8080/v1"}])
        self.assertEqual(self.bridge.setup_problem(json.dumps({**custom, "tiku.custom_providers": saved})), "")
        self.assertIn("服务商", self.bridge.setup_problem(json.dumps({**local, "tiku.custom_providers": saved})))

    def test_custom_provider_add_remove_and_round_trip(self):
        added = json.loads(self.bridge.add_custom_provider("", "我的中转", "https://relay.example.com/v1/"))
        self.assertTrue(added["ok"], added)
        self.assertEqual(added["endpoint"], "https://relay.example.com/v1")
        for name, url in (("本机", "http://127.0.0.1:8080/v1"), ("明文", "http://relay2.example.com/v1"),
                          ("重复", "https://relay.example.com/v1"), ("", "https://x.example.com/v1")):
            self.assertFalse(json.loads(self.bridge.add_custom_provider(added["value"], name, url))["ok"], name)
        values = json.loads(self.bridge.load_settings(self.config, self.template))
        values.update({"tiku.custom_providers": added["value"], "tiku.endpoint": added["endpoint"]})
        self.bridge.save_settings(self.config, self.template, json.dumps(values))
        again = json.loads(self.bridge.load_settings(self.config, self.template))
        self.assertEqual(json.loads(again["tiku.custom_providers"]), [{"name": "我的中转", "endpoint": "https://relay.example.com/v1"}])
        self.assertEqual(self.bridge.remove_custom_provider(again["tiku.custom_providers"], "https://relay.example.com/v1"), "")
        schema = json.loads(self.bridge.settings_schema())
        self.assertNotIn("hidden", [f["type"] for g in schema["groups"] for f in g["fields"]])
        self.assertEqual({r["id"] for r in schema["aiRegions"]}, {p["region"] for p in schema["aiProviders"]})


class RunTest(unittest.TestCase):
    """run(): output -> parsed events -> sink, input() answered from Kotlin, exit code."""

    def test_events_and_input(self):
        bridge = load_bridge()
        fake_main = types.ModuleType("main")

        def main():
            print("2026-11-04 08:00:00.000 | INFO     | main:run:1 - 开始学习课程: 大学物理", flush=True)
            print("ID: 1 班级ID: 2 课程名: 大学物理", flush=True)
            courses = input("请输入想要学习的课程列表,以逗号分隔,例: 2151141,189191,198198\n")
            print(f"2026-11-04 08:00:01.000 | INFO     | main:run:1 - 选择了 {courses}", flush=True)
            sys.stderr.write("\r1.1.mp4:  50%|█████     | 00:20/00:40")
            sys.stderr.write("\r1.1.mp4: 100%|██████████| 00:40/00:40\n")
            print('__CX_VIDEO_PREVIEW__{"source": "https://s1.cldisk.com/v.mp4", "title": "1.1"}', flush=True)
            raise SystemExit(0)

        fake_main.main = main
        events = []

        class Sink:
            def emit(self, payload):
                events.append(json.loads(payload))
                if events[-1]["type"] == "courselist":
                    threading.Timer(0.05, bridge.answer, args=("1",)).start()

        saved = sys.modules.get("main"), sys.stdout, sys.stderr, sys.argv[:]
        sys.modules["main"] = fake_main
        try:
            with tempfile.TemporaryDirectory() as tmp:
                cwd = Path.cwd()
                try:
                    code = bridge.run(str(Path(tmp) / "config.ini"), tmp, str(Path(tmp) / "pause.flag"), Sink())
                finally:
                    import os
                    os.chdir(cwd)
        finally:
            old_main, sys.stdout, sys.stderr, sys.argv[:] = saved
            if old_main is None:
                sys.modules.pop("main", None)
            else:
                sys.modules["main"] = old_main
            import builtins
            builtins.input = __builtins__["input"] if isinstance(__builtins__, dict) else __builtins__.input

        kinds = [e["type"] for e in events]
        self.assertEqual(code, 0)
        self.assertIn("activity", kinds)
        course_list = next(e for e in events if e["type"] == "courselist")
        self.assertEqual(course_list["courses"][0]["courseId"], "1")
        self.assertTrue(any(e["type"] == "log" and "选择了 1" in e["message"] for e in events))
        self.assertTrue(any(e["type"] == "progress" and e["percent"] == 100 for e in events))
        video = next(e for e in events if e["type"] == "videopreview")
        self.assertEqual(video["source"], "https://s1.cldisk.com/v.mp4")


class _Handler(http.server.BaseHTTPRequestHandler):
    status = 200

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        type(self).last = (self.headers.get("Authorization"), body)
        type(self).calls = getattr(type(self), "calls", 0) + 1
        if getattr(type(self), "busy", 0) > 0:               # the first `busy` requests: 503
            type(self).busy -= 1
            self.send_response(503)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if type(self).status != 200:
            payload = {"error": {"message": "bad key"}}
        else:
            payload = {"choices": [{"message": {"role": "assistant", "content": '{"Answer": ["2"]}'}}]}
        data = json.dumps(payload).encode()
        self.send_response(type(self).status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class OpenAIShimTest(unittest.TestCase):
    def setUp(self):
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/v1"
        self.openai = load_openai_shim()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        _Handler.status = 200
        _Handler.busy = 0

    def test_chat_completion(self):
        client = self.openai.OpenAI(base_url=self.base, api_key="sk-1")
        completion = client.chat.completions.create(model="m", messages=[{"role": "user", "content": "1+1"}],
                                                    max_tokens=10, extra_body={"thinking": {"type": "disabled"}})
        self.assertEqual(completion.choices[0].message.content, '{"Answer": ["2"]}')
        self.assertIsNone(completion.choices[0].message.reasoning_content)
        auth, body = _Handler.last
        self.assertEqual(auth, "Bearer sk-1")
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["max_tokens"], 10)

    def test_errors_map_to_sdk_classes(self):
        _Handler.status = 401
        client = self.openai.OpenAI(base_url=self.base, api_key="bad")
        with self.assertRaises(self.openai.AuthenticationError) as ctx:
            client.chat.completions.create(model="m", messages=[])
        self.assertIn("bad key", str(ctx.exception))
        self.assertTrue(issubclass(self.openai.APITimeoutError, self.openai.APIConnectionError))

    def test_busy_server_is_tried_again_like_the_sdk(self):
        from unittest import mock

        _Handler.calls, _Handler.busy = 0, 2
        client = self.openai.OpenAI(base_url=self.base, api_key="k", max_retries=2)
        with mock.patch.object(self.openai.time, "sleep") as sleep:
            completion = client.chat.completions.create(model="m", messages=[])
        self.assertEqual(completion.choices[0].message.content, '{"Answer": ["2"]}')
        self.assertEqual(_Handler.calls, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [0.5, 1.0])

    def test_gives_up_after_max_retries_and_a_wrong_key_is_not_retried(self):
        from unittest import mock

        _Handler.calls, _Handler.busy = 0, 5
        client = self.openai.OpenAI(base_url=self.base, api_key="k", max_retries=1)
        with mock.patch.object(self.openai.time, "sleep"), self.assertRaises(self.openai.InternalServerError):
            client.chat.completions.create(model="m", messages=[])
        self.assertEqual(_Handler.calls, 2)
        _Handler.calls, _Handler.busy, _Handler.status = 0, 0, 401
        with self.assertRaises(self.openai.AuthenticationError):
            client.chat.completions.create(model="m", messages=[])
        self.assertEqual(_Handler.calls, 1)

    def test_connection_error(self):
        client = self.openai.OpenAI(base_url="http://127.0.0.1:9/v1", api_key="k")
        with self.assertRaises(self.openai.APIConnectionError):
            client.chat.completions.create(model="m", messages=[])


if __name__ == "__main__":
    unittest.main()
