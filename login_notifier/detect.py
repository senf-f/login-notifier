import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone

SSHD_IDENTIFIERS = ("sshd", "sshd-session")
LOCAL_IDENTIFIERS = ("login",)

# sshd: "Accepted publickey for alice from 203.0.113.5 port 52144 ssh2: ED25519 SHA256:..."
SSH_ACCEPTED = re.compile(r"^Accepted (?P<method>\S+) for (?P<user>\S+) from (?P<ip>\S+) port \d+")
# login: "pam_unix(login:session): session opened for user root(uid=0) by LOGIN(uid=0)"
PAM_SESSION_OPENED = re.compile(r"pam_unix\((?P<service>[^:]+):session\): session opened for user (?P<user>[^\s(]+)")


class JournalError(Exception):
    pass


@dataclass(frozen=True)
class LoginEvent:
    username: str
    timestamp: datetime
    source_ip: str | None
    service: str
    method: str | None = None


def _timestamp(entry):
    try:
        return datetime.fromtimestamp(int(entry["__REALTIME_TIMESTAMP"]) / 1_000_000, tz=timezone.utc)
    except (KeyError, ValueError):
        return datetime.now(timezone.utc)


def parse_entry(entry):
    """Return a LoginEvent for a successful login journal entry, else None.

    SSH logins are taken only from sshd's "Accepted" line (which carries the IP);
    sshd's own pam_unix "session opened" line is ignored so one login yields one event.
    """
    identifier = entry.get("SYSLOG_IDENTIFIER")
    message = entry.get("MESSAGE")
    if not isinstance(message, str):
        return None

    if identifier in SSHD_IDENTIFIERS:
        m = SSH_ACCEPTED.match(message)
        if m:
            return LoginEvent(m["user"], _timestamp(entry), m["ip"], "ssh", m["method"])
    elif identifier in LOCAL_IDENTIFIERS:
        m = PAM_SESSION_OPENED.search(message)
        if m and m["service"] in LOCAL_IDENTIFIERS:
            return LoginEvent(m["user"], _timestamp(entry), None, "local")
    return None


def journal_command(cursor=None, journalctl="journalctl"):
    cmd = [journalctl, "--follow", "--output=json", "--no-pager"]
    cmd += [f"--after-cursor={cursor}"] if cursor else ["--lines=0"]
    cmd += [f"SYSLOG_IDENTIFIER={i}" for i in SSHD_IDENTIFIERS + LOCAL_IDENTIFIERS]
    return cmd


def follow(cmd, on_bad_line=None):
    """Yield parsed journal entries from a running journalctl; raise JournalError if it fails."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace")
    except OSError as e:
        raise JournalError(f"cannot run {cmd[0]}: {e.strerror}") from e

    try:
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                if on_bad_line:
                    on_bad_line(line)
    finally:
        if proc.poll() is None:
            proc.terminate()
        proc.stdout.close()
        code = proc.wait()
    raise JournalError(f"{cmd[0]} exited with status {code}")


def read_cursor(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read().strip() or None
    except FileNotFoundError:
        return None


def write_cursor(path, cursor):
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(cursor)
    os.replace(tmp, path)
