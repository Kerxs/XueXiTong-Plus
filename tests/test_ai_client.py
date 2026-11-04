import unittest

import httpx
import openai

from api.answer import AI


def make(**conf):
    base = {"endpoint": "https://api.example.com/v1", "key": "k", "model": "m",
            "http_proxy": "", "min_interval_seconds": "0"}
    ai = AI()
    ai.config_set({**base, **conf})
    ai._init_tiku()
    return ai


class AIClientTest(unittest.TestCase):
    def test_local_endpoint_ignores_proxy_and_allows_empty_key(self):
        ai = make(endpoint="http://127.0.0.1:9931/v1", http_proxy="http://127.0.0.1:9931", key="")
        self.assertTrue(ai._is_local_endpoint())
        client = ai._make_client()
        self.assertEqual(client.api_key, "no-key")

    def test_client_has_bounded_timeout_and_retries(self):
        client = make()._make_client()
        self.assertEqual(client.max_retries, 2)
        timeout = client.timeout
        seconds = timeout if isinstance(timeout, (int, float)) else timeout.read
        self.assertLessEqual(seconds, 120)

    def test_remote_endpoint_needs_key(self):
        with self.assertRaisesRegex(ValueError, "API Key"):
            make(key="")._make_client()

    def test_localhost_names(self):
        for url in ("http://localhost:8080/v1", "http://127.0.0.2/v1", "http://[::1]:1234/v1"):
            self.assertTrue(make(endpoint=url)._is_local_endpoint(), url)
        for url in ("https://api.deepseek.com/v1", "http://192.168.1.5:8000/v1", ""):
            self.assertFalse(make(endpoint=url)._is_local_endpoint(), url)

    def test_errors_are_explained(self):
        ai = make()
        request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
        not_found = openai.NotFoundError("File Not Found", response=httpx.Response(404, request=request), body=None)
        self.assertIn("404", ai._explain_error(not_found))
        self.assertIn("/v1", ai._explain_error(not_found))
        auth = openai.AuthenticationError("bad key", response=httpx.Response(401, request=request), body=None)
        self.assertIn("API Key", ai._explain_error(auth))
        self.assertIn("连不上", ai._explain_error(openai.APIConnectionError(request=request)))


if __name__ == "__main__":
    unittest.main()
