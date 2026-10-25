import argparse
import logging
import os
import socket
import sys
from datetime import datetime, timezone

from . import config as cfg
from . import detect, telegram
from .filters import should_notify

log = logging.getLogger("login_notifier")

# sd-daemon(3) priority prefixes so journald records the right severity.
_PRIORITIES = {logging.DEBUG: 7, logging.INFO: 6, logging.WARNING: 4, logging.ERROR: 3, logging.CRITICAL: 2}


class JournalFormatter(logging.Formatter):
    def format(self, record):
        return f"<{_PRIORITIES.get(record.levelno, 6)}>{super().format(record)}"


def setup_logging(level):
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JournalFormatter("%(message)s") if os.environ.get("JOURNAL_STREAM")
                         else logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


def handle_entry(entry, config, hostname, send=telegram.send):
    event = detect.parse_entry(entry)
    if event is None:
        return None
    if not should_notify(event.username, config.whitelist, config.blacklist):
        log.info("Login by %s from %s filtered out", event.username, event.source_ip or "local")
        return event
    log.info("Login by %s from %s, notifying", event.username, event.source_ip or "local")
    send(config, telegram.format_message(event, hostname))
    return event


def run(config_path, state_dir, check_perms=True, journalctl="journalctl"):
    def reloaded(new):
        logging.getLogger().setLevel(new.log_level)
        log.info("Configuration reloaded from %s", config_path)

    watcher = cfg.ConfigWatcher(
        config_path, check_perms,
        on_reload=reloaded,
        on_error=lambda e: log.error("Ignoring invalid config change, keeping previous config: %s", e),
    )
    logging.getLogger().setLevel(watcher.current().log_level)

    os.makedirs(state_dir, exist_ok=True)
    cursor_file = os.path.join(state_dir, "cursor")
    hostname = socket.gethostname()

    cmd = detect.journal_command(detect.read_cursor(cursor_file), journalctl)
    log.info("Watching journal for logins on %s", hostname)
    try:
        for entry in detect.follow(cmd, on_bad_line=lambda l: log.warning("Skipping unparsable journal line")):
            handle_entry(entry, watcher.current(), hostname)
            if "__CURSOR" in entry:
                detect.write_cursor(cursor_file, entry["__CURSOR"])
    except detect.JournalError as e:
        log.error("Journal access failed: %s", e)
        return 1
    return 0


def send_test(config_path, check_perms=True):
    config = cfg.load(config_path, check_perms)
    event = detect.LoginEvent("test", datetime.now(timezone.utc), None, "local")
    text = "Test notification from login-notifier\n\n" + telegram.format_message(event, socket.gethostname())
    return 0 if telegram.send(config, text) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(prog="login-notifier", description="Send a Telegram message on every login.")
    parser.add_argument("--config", default="/etc/login-notifier/config.json")
    parser.add_argument("--state-dir", default=os.environ.get("STATE_DIRECTORY", "/var/lib/login-notifier"))
    parser.add_argument("--test", action="store_true", help="send a test message and exit")
    parser.add_argument("--no-permission-check", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    setup_logging(logging.INFO)
    check_perms = not args.no_permission_check
    try:
        if args.test:
            return send_test(args.config, check_perms)
        return run(args.config, args.state_dir, check_perms)
    except cfg.ConfigError as e:
        log.error("Configuration error: %s", e)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
