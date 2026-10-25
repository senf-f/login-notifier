# login-notifier

Sends a Telegram message whenever someone logs in to a Linux server (SSH or local console).

```
Login on vps1
User: alice
From: 203.0.113.5 (ssh, publickey)
Time: 2026-10-25 11:04:49 UTC
```

It follows the systemd journal for successful logins: sshd's `Accepted ...` line for SSH, and
`pam_unix(login:session): session opened` for local console logins. Each login produces exactly one
message, and the position in the journal is saved so restarts neither miss nor re-send logins.

## Prerequisites

- Linux with systemd/journald (tested on Debian 12; Ubuntu 22.04+ and Debian 13 work the same way)
- Python 3.10+ (`python3`, no extra packages)
- Root access
- An existing Telegram bot

## Getting a bot token and chat ID

1. **Bot token:** in Telegram, talk to [@BotFather](https://t.me/BotFather). Send `/newbot` to make a
   new bot, or `/mybots` -> your bot -> *API Token* to look up an existing one. The token looks like
   `123456789:AAH...`.
2. **Chat ID:** send any message to your bot (or add it to a group and post there), then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser. The number at `"chat":{"id": ...}`
   is your chat ID. Group IDs are negative, e.g. `-1001234567890`.

## Install

```sh
git clone <this repo> login-notifier && cd login-notifier
sudo sh install.sh
```

This installs the code to `/opt/login-notifier`, the unit to `/etc/systemd/system/login-notifier.service`,
and (on first install only) an example config to `/etc/login-notifier/config.json`, owned by root with mode `600`.

## Configure

Edit `/etc/login-notifier/config.json`:

```json
{
  "bot_token": "123456789:AAH...",
  "chat_id": "123456789",
  "whitelist": [],
  "blacklist": ["deploy", "backup"],
  "log_level": "INFO"
}
```

| Field | Required | Meaning |
|---|---|---|
| `bot_token` | yes | Telegram bot token |
| `chat_id` | yes | Chat or group to notify (string or number) |
| `whitelist` | no | If non-empty, notify **only** for these users. Takes precedence over `blacklist`. |
| `blacklist` | no | Never notify for these users (e.g. automation accounts) |
| `log_level` | no | `DEBUG`, `INFO` (default), `WARNING` or `ERROR` |

The file must be owned by root and not readable by group/others (`chmod 600`). Otherwise the service
refuses to start. If a required field is missing, it exits with an error naming the field.

Changes to `whitelist`, `blacklist` and `log_level` take effect on the next login, with no restart needed.
If you save an invalid config while the service is running, the error is logged and the previous config stays in use.

Check the setup by sending a test message:

```sh
sudo PYTHONPATH=/opt/login-notifier python3 -m login_notifier --test
```

## Run as a service

```sh
sudo systemctl enable --now login-notifier
systemctl status login-notifier
journalctl -u login-notifier -f
```

The service starts on boot. If it crashes, it restarts after 5 seconds. Log severities are preserved
in the journal, so `journalctl -u login-notifier -p warning` shows only problems.

## Updating and uninstalling

- **Update:** `git pull && sudo sh install.sh && sudo systemctl restart login-notifier`. Your config is kept.
- **Uninstall:**
  ```sh
  sudo systemctl disable --now login-notifier
  sudo rm -rf /opt/login-notifier /etc/login-notifier /var/lib/login-notifier /etc/systemd/system/login-notifier.service
  sudo systemctl daemon-reload
  ```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `Configuration error: ... must not be accessible by group/others` | `sudo chmod 600 /etc/login-notifier/config.json && sudo chown root:root /etc/login-notifier/config.json`, then `systemctl restart login-notifier` |
| `Configuration error: missing required field ...` | Add the field, then restart. Config errors stop the service instead of restart-looping. |
| `Telegram API rejected message: Unauthorized` | Wrong `bot_token` |
| `Telegram API rejected message: Bad Request: chat not found` | Wrong `chat_id`, or you haven't sent the bot a message yet |
| `Telegram send failed ..., retrying` | Network problem. Each message is retried 3 times, then dropped with an error. |
| `Journal access failed` | journald isn't available or `journalctl` is missing. systemd restarts the service after 5s. |
| No message for SSH logins | Check `journalctl -t sshd -t sshd-session \| grep Accepted` shows your login. Make sure sshd's `SyslogFacility`/`LogLevel` hasn't been lowered below `INFO`. |
| Logins on a box using `/var/log/auth.log` only | Not supported. The journal is required. |

## Development

```sh
python3 -m unittest discover -s tests -t .    # unit tests
sh tests/integration/run.sh                   # full install test in a systemd container (needs Docker)
```

The integration test installs into a Debian 12 container, replaces Telegram with a local mock
(`api_base` config key), and checks the install, permissions, SSH notification, deduplication,
live config reload, journal severity, crash restart, and resume-after-restart.
