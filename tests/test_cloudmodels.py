import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from ui import cloudmodels

MODELS = ["deepseek-chat", "deepseek-reasoner", "Qwen/Qwen2.5-72B-Instruct"]


def serve(key="sk-test", has_models=True):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            if self.path != "/v1/models" or not has_models:
                self.send_error(404)
                return
            if self.headers.get("Authorization") != f"Bearer {key}":
                self.send_error(401)
                return
            body = json.dumps({"object": "list", "data": [{"id": m, "object": "model"} for m in MODELS]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}/v1"


class ProviderListTest(unittest.TestCase):
    def test_every_provider_is_complete(self):
        regions = {r["id"] for r in cloudmodels.REGIONS}
        ids = [p["id"] for p in cloudmodels.PROVIDERS]
        self.assertEqual(len(ids), len(set(ids)))
        for p in cloudmodels.PROVIDERS:
            self.assertIn(p["region"], regions, p)
            self.assertTrue(p["endpoint"].startswith("https://") and not p["endpoint"].endswith("/"), p)
            self.assertTrue(p["console"].startswith("https://"), p)
            self.assertEqual(cloudmodels.console_url(p["endpoint"]), p["console"])
        self.assertNotIn("hosts", cloudmodels.public_providers()[0])

    def test_new_companies_are_recognised(self):
        self.assertEqual(cloudmodels.identify("https://generativelanguage.googleapis.com/v1beta/openai/"), "Google Gemini")
        self.assertEqual(cloudmodels.identify("https://api.x.ai/v1"), "xAI Grok")
        self.assertEqual(cloudmodels.identify("https://api.minimax.chat/v1"), "MiniMax")


class CustomProviderTest(unittest.TestCase):
    def test_add_parse_remove(self):
        saved = cloudmodels.dump_custom(cloudmodels.add_custom("", "公司网关", "https://llm.corp.example/v1/"))
        self.assertEqual(cloudmodels.parse_custom(saved), [{"name": "公司网关", "endpoint": "https://llm.corp.example/v1"}])
        self.assertEqual(cloudmodels.identify("https://llm.corp.example/v1", saved), "公司网关")
        self.assertEqual(cloudmodels.identify("https://llm.corp.example/v1"), "")
        self.assertTrue(cloudmodels.is_listed("https://llm.corp.example/v1/", saved))
        self.assertTrue(cloudmodels.is_listed("https://api.deepseek.com/v1"))
        self.assertFalse(cloudmodels.is_listed("https://other.example/v1", saved))
        self.assertEqual(cloudmodels.dump_custom(cloudmodels.remove_custom(saved, "https://llm.corp.example/v1")), "")

    def test_custom_name_wins_over_company(self):
        saved = cloudmodels.dump_custom([{"name": "我的 DeepSeek", "endpoint": "https://api.deepseek.com/v1"}])
        self.assertEqual(cloudmodels.identify("https://api.deepseek.com/v1", saved), "我的 DeepSeek")

    def test_problems(self):
        saved = cloudmodels.dump_custom([{"name": "A", "endpoint": "https://a.example/v1"}])
        p = cloudmodels.custom_problem
        self.assertEqual(p("B", "https://b.example/v1", saved), "")
        self.assertIn("名称", p("", "https://b.example/v1", saved))
        self.assertIn("http", p("B", "b.example/v1", saved))
        self.assertIn("/chat/completions", p("B", "https://b.example/v1/chat/completions", saved))
        self.assertIn("已经保存", p("B", "https://a.example/v1/", saved))
        self.assertIn("同名", p("A", "https://c.example/v1", saved))
        self.assertEqual(p("本机", "http://127.0.0.1:8080/v1", saved), "")             # desktop: fine
        self.assertIn("本机", p("本机", "http://127.0.0.1:8080/v1", saved, cloud_only=True))
        self.assertIn("https", p("B", "http://b.example/v1", saved, cloud_only=True))
        full = [{"name": str(i), "endpoint": f"https://{i}.example/v1"} for i in range(cloudmodels.MAX_CUSTOM)]
        self.assertIn("最多", p("x", "https://x.example/v1", full))

    def test_damaged_value_is_ignored(self):
        self.assertEqual(cloudmodels.parse_custom("{not json"), [])
        self.assertEqual(cloudmodels.parse_custom('[{"name": "x", "endpoint": "ftp://x"}, 3, {"name": ""}]'), [])


class CloudModelsTest(unittest.TestCase):
    def test_identify(self):
        self.assertEqual(cloudmodels.identify("https://api.deepseek.com/v1"), "DeepSeek")
        self.assertEqual(cloudmodels.identify("https://dashscope.aliyuncs.com/compatible-mode/v1"), "通义千问（阿里云百炼）")
        self.assertEqual(cloudmodels.identify("https://ark.cn-beijing.volces.com/api/v3"), "豆包（火山方舟）")
        self.assertEqual(cloudmodels.identify("http://127.0.0.1:9931/v1"), "本机模型服务")
        self.assertEqual(cloudmodels.identify("https://llm.example.com/v1"), "")
        self.assertEqual(cloudmodels.identify("https://evil-deepseek.com.example.org/v1"), "")
        self.assertEqual(cloudmodels.identify(""), "")

    def test_presets_are_recognised_as_themselves(self):
        for provider in cloudmodels.PROVIDERS:
            self.assertEqual(cloudmodels.identify(provider["endpoint"]), provider["name"], provider)

    def test_lists_models_with_the_key(self):
        server, endpoint = serve()
        try:
            self.assertEqual(cloudmodels.list_models(endpoint + "/", "sk-test"), sorted(MODELS, key=str.lower))
            with self.assertRaisesRegex(cloudmodels.ModelListError, "401"):
                cloudmodels.list_models(endpoint, "sk-wrong")
        finally:
            server.shutdown()

    def test_service_without_model_list(self):
        server, endpoint = serve(has_models=False)
        try:
            with self.assertRaisesRegex(cloudmodels.ModelListError, "手动填写"):
                cloudmodels.list_models(endpoint, "sk-test")
        finally:
            server.shutdown()

    def test_input_checks(self):
        with self.assertRaisesRegex(cloudmodels.ModelListError, "http"):
            cloudmodels.list_models("api.deepseek.com/v1", "k")
        with self.assertRaisesRegex(cloudmodels.ModelListError, "API Key"):
            cloudmodels.list_models("https://api.deepseek.com/v1", "")
        with self.assertRaisesRegex(cloudmodels.ModelListError, "连不上"):
            cloudmodels.list_models("http://127.0.0.1:9/v1", "", timeout=2)


if __name__ == "__main__":
    unittest.main()
