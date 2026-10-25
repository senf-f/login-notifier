import json
import os
import stat
from dataclasses import dataclass

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
DEFAULT_API_BASE = "https://api.telegram.org"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    bot_token: str
    chat_id: str
    whitelist: frozenset = frozenset()
    blacklist: frozenset = frozenset()
    log_level: str = "INFO"
    api_base: str = DEFAULT_API_BASE


def _user_list(data, key):
    value = data.get(key, [])
    if not isinstance(value, list) or not all(isinstance(u, str) for u in value):
        raise ConfigError(f"'{key}' must be a list of usernames")
    return frozenset(value)


def parse(data):
    if not isinstance(data, dict):
        raise ConfigError("config must be a JSON object")

    token = data.get("bot_token")
    if not isinstance(token, str) or not token.strip():
        raise ConfigError("missing required field 'bot_token'")

    chat_id = data.get("chat_id")
    if isinstance(chat_id, bool) or not isinstance(chat_id, (str, int)) or str(chat_id).strip() == "":
        raise ConfigError("missing required field 'chat_id'")

    log_level = str(data.get("log_level", "INFO")).upper()
    if log_level not in LOG_LEVELS:
        raise ConfigError(f"'log_level' must be one of {', '.join(LOG_LEVELS)}")

    api_base = data.get("api_base", DEFAULT_API_BASE)
    if not isinstance(api_base, str) or not api_base.startswith(("https://", "http://")):
        raise ConfigError("'api_base' must be an http(s) URL")

    return Config(
        bot_token=token.strip(),
        chat_id=str(chat_id).strip(),
        whitelist=_user_list(data, "whitelist"),
        blacklist=_user_list(data, "blacklist"),
        log_level=log_level,
        api_base=api_base.rstrip("/"),
    )


def check_permissions(st, path, required_uid=0):
    if st.st_uid != required_uid:
        raise ConfigError(f"{path} must be owned by uid {required_uid}")
    if stat.S_IMODE(st.st_mode) & 0o077:
        raise ConfigError(f"{path} must not be accessible by group/others (chmod 600)")


def load(path, check_perms=True):
    try:
        if check_perms:
            check_permissions(os.stat(path), path)
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise ConfigError(f"cannot read {path}: {e.strerror}") from e
    except json.JSONDecodeError as e:
        raise ConfigError(f"{path} is not valid JSON: {e}") from e
    return parse(data)


class ConfigWatcher:
    """Reloads the config when the file's mtime changes; keeps the last good config on errors."""

    def __init__(self, path, check_perms=True, on_reload=None, on_error=None):
        self.path = path
        self.check_perms = check_perms
        self.on_reload = on_reload
        self.on_error = on_error
        self._mtime = os.stat(path).st_mtime_ns if os.path.exists(path) else None
        self._config = load(path, check_perms)

    def current(self):
        try:
            mtime = os.stat(self.path).st_mtime_ns
        except OSError:
            return self._config
        if mtime != self._mtime:
            self._mtime = mtime
            try:
                self._config = load(self.path, self.check_perms)
            except ConfigError as e:
                if self.on_error:
                    self.on_error(e)
            else:
                if self.on_reload:
                    self.on_reload(self._config)
        return self._config
