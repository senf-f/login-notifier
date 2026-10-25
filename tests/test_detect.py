import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

from login_notifier import detect

TS = "1761390000000000"  # 2025-10-25 11:00:00 UTC


def entry(ident, msg, **extra):
    return {"SYSLOG_IDENTIFIER": ident, "MESSAGE": msg, "__REALTIME_TIMESTAMP": TS, **extra}


class ParseEntryTests(unittest.TestCase):
    def test_ssh_publickey(self):
        e = detect.parse_entry(entry("sshd", "Accepted publickey for alice from 203.0.113.5 port 52144 ssh2: ED25519 SHA256:x"))
        self.assertEqual(e.username, "alice")
        self.assertEqual(e.source_ip, "203.0.113.5")
        self.assertEqual(e.service, "ssh")
        self.assertEqual(e.method, "publickey")
        self.assertEqual(e.timestamp, datetime(2025, 10, 25, 11, 0, tzinfo=timezone.utc))

    def test_ssh_password_ipv6_and_sshd_session(self):
        e = detect.parse_entry(entry("sshd-session", "Accepted password for root from 2001:db8::1 port 22 ssh2"))
        self.assertEqual((e.username, e.source_ip, e.method), ("root", "2001:db8::1", "password"))

    def test_local_console_login_both_pam_formats(self):
        for msg in ("pam_unix(login:session): session opened for user root(uid=0) by LOGIN(uid=0)",
                    "pam_unix(login:session): session opened for user bob by LOGIN(uid=0)"):
            with self.subTest(msg=msg):
                e = detect.parse_entry(entry("login", msg))
                self.assertIn(e.username, ("root", "bob"))
                self.assertIsNone(e.source_ip)
                self.assertEqual(e.service, "local")

    def test_ssh_pam_session_line_ignored_to_avoid_duplicates(self):
        msg = "pam_unix(sshd:session): session opened for user alice(uid=1000) by alice(uid=0)"
        self.assertIsNone(detect.parse_entry(entry("sshd", msg)))
        self.assertIsNone(detect.parse_entry(entry("sshd-session", msg)))

    def test_irrelevant_entries_ignored(self):
        for e in (entry("sshd", "Failed password for root from 1.2.3.4 port 22 ssh2"),
                  entry("sshd", "Invalid user admin from 1.2.3.4 port 22"),
                  entry("sudo", "pam_unix(sudo:session): session opened for user root(uid=0) by alice(uid=1000)"),
                  entry("cron", "pam_unix(cron:session): session opened for user root(uid=0) by (uid=0)"),
                  {"SYSLOG_IDENTIFIER": "sshd", "MESSAGE": [65, 66]}):
            with self.subTest(e=e):
                self.assertIsNone(detect.parse_entry(e))


class CommandTests(unittest.TestCase):
    def test_fresh_start_skips_history(self):
        cmd = detect.journal_command()
        self.assertIn("--lines=0", cmd)
        self.assertIn("SYSLOG_IDENTIFIER=sshd", cmd)
        self.assertIn("SYSLOG_IDENTIFIER=login", cmd)

    def test_resume_after_cursor(self):
        cmd = detect.journal_command("s=abc;i=1")
        self.assertIn("--after-cursor=s=abc;i=1", cmd)
        self.assertNotIn("--lines=0", cmd)


class FollowTests(unittest.TestCase):
    def fake(self, script):
        return [sys.executable, "-c", script]

    def test_yields_entries_skips_bad_lines_then_raises_on_exit(self):
        lines = [json.dumps({"MESSAGE": "a"}), "garbage", "", json.dumps({"MESSAGE": "b"})]
        script = f"import sys; print({chr(10).join(lines)!r}); sys.exit(1)"
        bad = []
        got = []
        with self.assertRaisesRegex(detect.JournalError, "status 1"):
            for e in detect.follow(self.fake(script), on_bad_line=bad.append):
                got.append(e["MESSAGE"])
        self.assertEqual(got, ["a", "b"])
        self.assertEqual(bad, ["garbage"])

    def test_missing_journalctl(self):
        with self.assertRaisesRegex(detect.JournalError, "cannot run"):
            list(detect.follow(["/nonexistent/journalctl"]))


class CursorTests(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "cursor")
            self.assertIsNone(detect.read_cursor(p))
            detect.write_cursor(p, "s=1;i=2")
            self.assertEqual(detect.read_cursor(p), "s=1;i=2")


if __name__ == "__main__":
    unittest.main()
