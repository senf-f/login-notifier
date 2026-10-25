import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

log = logging.getLogger(__name__)

RETRIES = 3
RETRY_DELAY = 2.0
TIMEOUT = 10


class _Rejected(Exception):
    pass


class _Transient(Exception):
    pass


def format_message(event, hostname):
    if event.source_ip:
        origin = f"{event.source_ip} (ssh{', ' + event.method if event.method else ''})"
    else:
        origin = "local console"
    return (
        f"Login on {hostname}\n"
        f"User: {event.username}\n"
        f"From: {origin}\n"
        f"Time: {event.timestamp:%Y-%m-%d %H:%M:%S %Z}"
    )


def _post(urlopen, url, body):
    """One API call. Raises _Rejected (don't retry) or _Transient (retry); never mentions the URL/token."""
    try:
        with urlopen(urllib.request.Request(url, data=body, method="POST"), timeout=TIMEOUT) as resp:
            payload = json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        with e:
            try:
                description = json.loads(e.read()).get("description")
            except (ValueError, OSError, AttributeError):
                description = None
        reason = description or f"HTTP {e.code}"
        raise (_Transient if e.code == 429 or e.code >= 500 else _Rejected)(reason) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise _Transient(str(getattr(e, "reason", e))) from None
    except ValueError:
        raise _Rejected("invalid JSON response") from None
    if not payload.get("ok", True):
        raise _Rejected(payload.get("description", "unknown error"))


def send(config, text, *, urlopen=urllib.request.urlopen, sleep=time.sleep):
    """POST text to the configured chat. Returns True on success; never raises for network/API errors."""
    url = f"{config.api_base}/bot{config.bot_token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": config.chat_id, "text": text}).encode()

    for attempt in range(RETRIES + 1):
        try:
            _post(urlopen, url, body)
            return True
        except _Rejected as e:
            log.error("Telegram API rejected message: %s", e)
            return False
        except _Transient as e:
            if attempt == RETRIES:
                log.error("Failed to send Telegram notification after %d attempts: %s", attempt + 1, e)
                return False
            log.warning("Telegram send failed (%s), retrying (%d/%d)", e, attempt + 1, RETRIES)
            sleep(RETRY_DELAY * (attempt + 1))
    return False
