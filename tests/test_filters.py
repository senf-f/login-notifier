import unittest
from datetime import datetime, timezone

from login_notifier import config as cfg
from login_notifier.__main__ import handle_entry
from login_notifier.filters import should_notify

SSH = {"SYSLOG_IDENTIFIER": "sshd", "MESSAGE": "Accepted publickey for {} from 1.2.3.4 port 22 ssh2",
       "__REALTIME_TIMESTAMP": "1761390000000000"}


class ShouldNotifyTests(unittest.TestCase):
    def test_no_lists_notifies_everyone(self):
        self.assertTrue(should_notify("alice", frozenset(), frozenset()))

    def test_blacklist_excludes(self):
        self.assertFalse(should_notify("deploy", frozenset(), frozenset({"deploy"})))
        self.assertTrue(should_notify("alice", frozenset(), frozenset({"deploy"})))

    def test_whitelist_includes_only_listed(self):
        self.assertTrue(should_notify("root", frozenset({"root"}), frozenset()))
        self.assertFalse(should_notify("alice", frozenset({"root"}), frozenset()))

    def test_whitelist_overrides_blacklist(self):
        self.assertTrue(should_notify("root", frozenset({"root"}), frozenset({"root"})))
        self.assertFalse(should_notify("alice", frozenset({"root"}), frozenset({"bob"})))


class HandleEntryTests(unittest.TestCase):
    def run_entry(self, user, **lists):
        sent = []
        config = cfg.parse({"bot_token": "t", "chat_id": 1, **lists})
        entry = {**SSH, "MESSAGE": SSH["MESSAGE"].format(user)}
        handle_entry(entry, config, "vps1", send=lambda c, text: sent.append(text))
        return sent

    def test_filtered_user_sends_nothing(self):
        self.assertEqual(self.run_entry("deploy", blacklist=["deploy"]), [])
        self.assertEqual(self.run_entry("alice", whitelist=["root"]), [])

    def test_allowed_user_sends_message(self):
        sent = self.run_entry("root", whitelist=["root"], blacklist=["root"])
        self.assertEqual(len(sent), 1)
        self.assertIn("root", sent[0])

    def test_non_login_entry_sends_nothing(self):
        sent = []
        config = cfg.parse({"bot_token": "t", "chat_id": 1})
        handle_entry({"SYSLOG_IDENTIFIER": "sshd", "MESSAGE": "Connection closed"}, config, "h",
                     send=lambda c, t: sent.append(t))
        self.assertEqual(sent, [])


if __name__ == "__main__":
    unittest.main()
