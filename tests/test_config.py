import json
import os
import tempfile
import time
import unittest
from types import SimpleNamespace

from login_notifier import config as cfg

VALID = {"bot_token": "123:abc", "chat_id": -100123, "whitelist": ["alice"], "log_level": "debug"}


class ParseTests(unittest.TestCase):
    def test_valid_config(self):
        c = cfg.parse(VALID)
        self.assertEqual(c.bot_token, "123:abc")
        self.assertEqual(c.chat_id, "-100123")
        self.assertEqual(c.whitelist, frozenset({"alice"}))
        self.assertEqual(c.blacklist, frozenset())
        self.assertEqual(c.log_level, "DEBUG")
        self.assertEqual(c.api_base, cfg.DEFAULT_API_BASE)

    def test_missing_required_fields(self):
        for field in ("bot_token", "chat_id"):
            data = {k: v for k, v in VALID.items() if k != field}
            with self.assertRaisesRegex(cfg.ConfigError, field):
                cfg.parse(data)

    def test_empty_token_rejected(self):
        with self.assertRaises(cfg.ConfigError):
            cfg.parse({**VALID, "bot_token": "  "})

    def test_invalid_values_rejected(self):
        for bad in ({"log_level": "LOUD"}, {"whitelist": "alice"}, {"blacklist": [1]},
                    {"chat_id": True}, {"api_base": "ftp://x"}):
            with self.subTest(bad=bad), self.assertRaises(cfg.ConfigError):
                cfg.parse({**VALID, **bad})


class PermissionTests(unittest.TestCase):
    def st(self, mode, uid=0):
        return SimpleNamespace(st_mode=0o100000 | mode, st_uid=uid)

    def test_root_600_ok(self):
        cfg.check_permissions(self.st(0o600), "c.json")

    def test_group_or_world_readable_rejected(self):
        for mode in (0o640, 0o604, 0o644):
            with self.subTest(mode=oct(mode)), self.assertRaisesRegex(cfg.ConfigError, "600"):
                cfg.check_permissions(self.st(mode), "c.json")

    def test_non_root_owner_rejected(self):
        with self.assertRaisesRegex(cfg.ConfigError, "owned"):
            cfg.check_permissions(self.st(0o600, uid=1000), "c.json")


class FileTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "config.json")

    def tearDown(self):
        self.dir.cleanup()

    def write(self, data):
        with open(self.path, "w") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        # Ensure mtime changes even on coarse-resolution filesystems.
        t = time.time() + getattr(self, "_bump", 0)
        self._bump = getattr(self, "_bump", 0) + 2
        os.utime(self.path, (t, t))

    def test_load_and_invalid_json(self):
        self.write(VALID)
        self.assertEqual(cfg.load(self.path, check_perms=False).bot_token, "123:abc")
        self.write("{not json")
        with self.assertRaisesRegex(cfg.ConfigError, "not valid JSON"):
            cfg.load(self.path, check_perms=False)

    def test_missing_file(self):
        with self.assertRaisesRegex(cfg.ConfigError, "cannot read"):
            cfg.load(self.path, check_perms=False)

    def test_watcher_reloads_and_keeps_last_good(self):
        self.write(VALID)
        reloads, errors = [], []
        w = cfg.ConfigWatcher(self.path, check_perms=False, on_reload=reloads.append, on_error=errors.append)
        self.assertEqual(w.current().blacklist, frozenset())

        self.write({**VALID, "whitelist": [], "blacklist": ["bob"]})
        self.assertEqual(w.current().blacklist, frozenset({"bob"}))
        self.assertEqual(len(reloads), 1)

        self.write({"chat_id": 1})
        self.assertEqual(w.current().blacklist, frozenset({"bob"}))
        self.assertEqual(len(errors), 1)


if __name__ == "__main__":
    unittest.main()
