import io
import json
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from login_notifier import config as cfg
from login_notifier import telegram
from login_notifier.detect import LoginEvent

CONFIG = cfg.parse({"bot_token": "123:SECRET", "chat_id": 42})
EVENT = LoginEvent("alice", datetime(2026, 10, 25, 11, 0, tzinfo=timezone.utc), "203.0.113.5", "ssh", "publickey")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeOpener:
    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return FakeResponse(json.dumps(outcome).encode())


def http_error(code, body=b"{}"):
    return urllib.error.HTTPError("https://api.telegram.org/botX/sendMessage", code, "err", {}, io.BytesIO(body))


class FormatTests(unittest.TestCase):
    def test_ssh_message_contains_user_time_ip(self):
        text = telegram.format_message(EVENT, "vps1")
        for part in ("vps1", "alice", "203.0.113.5", "publickey", "2026-10-25 11:00:00 UTC"):
            self.assertIn(part, text)

    def test_local_message(self):
        event = LoginEvent("root", EVENT.timestamp, None, "local")
        self.assertIn("local console", telegram.format_message(event, "vps1"))


class SendTests(unittest.TestCase):
    def setUp(self):
        self.sleeps = []

    def send(self, opener):
        with self.assertLogs("login_notifier.telegram", "DEBUG") as logs:
            telegram.log.debug("start")
            result = telegram.send(CONFIG, "hello", urlopen=opener, sleep=self.sleeps.append)
        self.logs = "\n".join(logs.output)
        return result

    def test_success_posts_to_bot_api(self):
        opener = FakeOpener({"ok": True})
        self.assertTrue(self.send(opener))
        req = opener.requests[0]
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, "https://api.telegram.org/bot123:SECRET/sendMessage")
        self.assertEqual(urllib.parse.parse_qs(req.data.decode()), {"chat_id": ["42"], "text": ["hello"]})

    def test_retries_network_errors_then_succeeds(self):
        opener = FakeOpener(urllib.error.URLError("down"), TimeoutError(), {"ok": True})
        self.assertTrue(self.send(opener))
        self.assertEqual(len(opener.requests), 3)
        self.assertEqual(len(self.sleeps), 2)

    def test_gives_up_after_three_retries_without_raising(self):
        opener = FakeOpener(*[urllib.error.URLError("down")] * 4)
        self.assertFalse(self.send(opener))
        self.assertEqual(len(opener.requests), 4)
        self.assertIn("ERROR", self.logs)
        self.assertNotIn("SECRET", self.logs)

    def test_server_errors_retried_client_errors_not(self):
        self.assertTrue(self.send(FakeOpener(http_error(502), {"ok": True})))
        opener = FakeOpener(http_error(401))
        self.assertFalse(self.send(opener))
        self.assertEqual(len(opener.requests), 1)

    def test_http_error_logs_telegram_description(self):
        body = b'{"ok": false, "error_code": 401, "description": "Unauthorized"}'
        self.assertFalse(self.send(FakeOpener(http_error(401, body))))
        self.assertIn("rejected message: Unauthorized", self.logs)

    def test_api_rejection_returns_false(self):
        self.assertFalse(self.send(FakeOpener({"ok": False, "description": "chat not found"})))
        self.assertIn("chat not found", self.logs)


if __name__ == "__main__":
    unittest.main()
