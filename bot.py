#!/usr/bin/env python3
"""Small private-chat polling example. Requires Python 3.9+, no pip packages."""
import json
import os
import re
import signal
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from pathlib import Path


class ConfigurationError(Exception):
    pass


class TelegramError(Exception):
    def __init__(self, status=None, retry_after=0):
        super().__init__("Telegram request failed" + (" (HTTP %s)" % status if status else ""))
        self.status = status
        self.retry_after = retry_after


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class TelegramAPI:
    def __init__(self, token, opener=None):
        if not re.fullmatch(r"[0-9]{5,20}:[A-Za-z0-9_-]{20,120}", token):
            raise ConfigurationError("Set a valid BOT_TOKEN in the environment file")
        self._token = token
        self._opener = opener if opener is not None else urllib.request.build_opener(NoRedirect()).open

    def call(self, method, payload=None):
        request = urllib.request.Request(
            "https://api.telegram.org/bot%s/%s" % (self._token, method),
            data=json.dumps(payload or {}).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with self._opener(request, timeout=40) as response:
                data = json.loads(response.read(1024 * 1024))
        except urllib.error.HTTPError as error:
            retry_after = 0
            try:
                parameters = json.loads(error.read(65536)).get("parameters", {})
                value = parameters.get("retry_after", 0)
                if type(value) is int:
                    retry_after = max(0, value)
            except (ValueError, AttributeError, TypeError):
                pass
            # HTTPError text contains the URL, including the token. Never log it.
            raise TelegramError(error.code, retry_after) from None
        except (OSError, ValueError):
            raise TelegramError() from None
        if not isinstance(data, dict) or data.get("ok") is not True:
            raise TelegramError()
        return data.get("result")

    def check_polling(self):
        result = self.call("getWebhookInfo")
        if not isinstance(result, dict):
            raise TelegramError()
        if result.get("url"):
            raise ConfigurationError("A webhook is active; use a separate test bot or stop here")


class OffsetState:
    def __init__(self, directory):
        self.path = Path(directory) / "offset.json"
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.offset = 0
        if self.path.exists():
            try:
                self.offset = json.loads(self.path.read_text(encoding="utf-8"))["offset"]
                if type(self.offset) is not int or self.offset < 0:
                    raise ValueError()
            except (ValueError, KeyError, TypeError):
                raise ConfigurationError("Invalid offset state; preserve it and inspect before restarting") from None

    def advance(self, value):
        filename = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as output:
                filename = output.name
                json.dump({"offset": value}, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(filename, self.path)
            self.offset = value
        finally:
            if filename and os.path.exists(filename):
                os.unlink(filename)


def process_updates(api, state, updates):
    if not isinstance(updates, list):
        raise TelegramError()
    for update in updates:
        update_id = update.get("update_id") if isinstance(update, dict) else None
        if type(update_id) is not int or update_id < state.offset:
            continue
        message = update.get("message", {})
        chat = message.get("chat", {}) if isinstance(message, dict) else {}
        if not isinstance(chat, dict):
            chat = {}
        text = message.get("text") if isinstance(message, dict) else None
        if chat.get("type") == "private" and type(chat.get("id")) is int and isinstance(text, str):
            try:
                api.call("sendMessage", {"chat_id": chat["id"], "text": "Вы написали: " + text[:1000]})
            except TelegramError as error:
                if error.status not in (400, 403):
                    raise
                print("Skipping rejected private-chat reply (HTTP %s)" % error.status, file=sys.stderr)
        state.advance(update_id + 1)


def wait_retry(stop, seconds):
    # Short interruptible waits also support long provider deadlines safely.
    while seconds > 0:
        interval = min(seconds, 60)
        if stop.wait(interval):
            return
        seconds -= interval


def main():
    os.umask(0o077)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    try:
        api = TelegramAPI(os.environ.get("BOT_TOKEN", "").strip())
        state = OffsetState(os.environ.get("STATE_DIRECTORY", "./state"))
        api.check_polling()
    except (ConfigurationError, OSError) as error:
        print(str(error) if isinstance(error, ConfigurationError) else "Cannot open offset state", file=sys.stderr)
        return 2
    except TelegramError as error:
        print(str(error), file=sys.stderr)
        return 2 if error.status in (401, 404) else 1
    failures = 0
    while not stop.is_set():
        try:
            updates = api.call("getUpdates", {"offset": state.offset, "timeout": 30, "allowed_updates": ["message"]})
            process_updates(api, state, updates)
            failures = 0
        except (TelegramError, OSError) as error:
            print(str(error) if isinstance(error, TelegramError) else "Cannot save offset state", file=sys.stderr)
            if isinstance(error, TelegramError) and error.status in (401, 404):
                return 2
            failures += 1
            wait_retry(stop, max(min(60, 2 ** min(failures, 6)), getattr(error, "retry_after", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
