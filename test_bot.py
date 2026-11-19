import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

from bot import ConfigurationError, NoRedirect, OffsetState, TelegramAPI, TelegramError, process_updates, wait_retry

TOKEN = "123456789:EXAMPLE_ONLY_NOT_A_REAL_TOKEN_123456"


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class BotTests(unittest.TestCase):
    def test_redirects_are_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, None, None, "https://example.com/"))

    def test_request_uses_https_and_only_expected_api_payload(self):
        captured = []

        def opener(request, timeout):
            captured.append((request, timeout))
            return Response(b'{"ok":true,"result":[]}')

        api = TelegramAPI(TOKEN, opener)
        self.assertEqual(api.call("getUpdates", {"offset": 12, "timeout": 30}), [])
        request, timeout = captured[0]
        self.assertTrue(request.full_url.startswith("https://api.telegram.org/bot"))
        self.assertEqual(json.loads(request.data), {"offset": 12, "timeout": 30})
        self.assertEqual(timeout, 40)

    def test_http_error_hides_token_and_preserves_rate_limit_delay(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, "private error", {},
                                         Response(b'{"parameters":{"retry_after":35}}'))

        with self.assertRaises(TelegramError) as raised:
            TelegramAPI(TOKEN, opener).call("getUpdates")
        self.assertEqual(raised.exception.retry_after, 35)
        self.assertNotIn(TOKEN, str(raised.exception))
        self.assertNotIn("private", str(raised.exception))

    def test_network_error_never_prints_its_private_url(self):
        def opener(request, timeout):
            raise urllib.error.URLError("connection to " + request.full_url)

        with self.assertRaises(TelegramError) as raised:
            TelegramAPI(TOKEN, opener).call("getUpdates")
        self.assertEqual(str(raised.exception), "Telegram request failed")

    def test_long_retry_after_is_not_shortened_and_wait_is_interruptible(self):
        def opener(request, timeout):
            raise urllib.error.HTTPError(request.full_url, 429, "rate limited", {},
                                         Response(b'{"parameters":{"retry_after":600}}'))

        with self.assertRaises(TelegramError) as raised:
            TelegramAPI(TOKEN, opener).call("getUpdates")
        self.assertEqual(raised.exception.retry_after, 600)

        class Stop:
            def __init__(self, interrupt=False):
                self.waits = []
                self.interrupt = interrupt

            def wait(self, seconds):
                self.waits.append(seconds)
                return self.interrupt

        stop = Stop()
        wait_retry(stop, 600)
        self.assertEqual(sum(stop.waits), 600)
        stop = Stop(interrupt=True)
        wait_retry(stop, 600)
        self.assertEqual(stop.waits, [60])

    def test_webhook_is_preserved_instead_of_deleted(self):
        calls = []

        def opener(request, timeout):
            calls.append(request.full_url.rsplit("/", 1)[-1])
            return Response(b'{"ok":true,"result":{"url":"https://private.example/hook"}}')

        with self.assertRaises(ConfigurationError) as raised:
            TelegramAPI(TOKEN, opener).check_polling()
        self.assertEqual(calls, ["getWebhookInfo"])
        self.assertNotIn("private.example", str(raised.exception))

    def test_restart_recovers_offset_and_ignores_processed_or_nonprivate_messages(self):
        class API:
            def __init__(self):
                self.messages = []

            def call(self, method, payload):
                self.messages.append((method, payload))

        with tempfile.TemporaryDirectory() as directory:
            api = API()
            state = OffsetState(directory)
            updates = [
                {"update_id": 4, "message": {"chat": {"type": "private", "id": 42}, "text": "hello"}},
                {"update_id": 5, "message": {"chat": {"type": "group", "id": 43}, "text": "ignore"}},
                {"update_id": 6, "message": {"chat": []}},
            ]
            process_updates(api, state, updates)
            self.assertEqual(state.offset, 7)
            reloaded = OffsetState(directory)
            process_updates(api, reloaded, updates)
            self.assertEqual(len(api.messages), 1)
            self.assertEqual(api.messages[0], ("sendMessage", {"chat_id": 42, "text": "Вы написали: hello"}))
            contents = Path(directory, "offset.json").read_text()
            self.assertNotIn("hello", contents)
            self.assertEqual(list(Path(directory).iterdir()), [Path(directory, "offset.json")])

    def test_send_failure_does_not_acknowledge_update(self):
        class API:
            def call(self, *args):
                raise TelegramError(503)

        with tempfile.TemporaryDirectory() as directory:
            state = OffsetState(directory)
            with self.assertRaises(TelegramError):
                process_updates(API(), state, [{"update_id": 4, "message": {"chat": {"id": 42, "type": "private"}, "text": "hello"}}])
            self.assertEqual(OffsetState(directory).offset, 0)

    def test_rejected_reply_does_not_block_the_next_update(self):
        class API:
            def __init__(self, status):
                self.status = status
                self.sent = []

            def call(self, method, payload):
                if payload["chat_id"] == 41:
                    raise TelegramError(self.status)
                self.sent.append(payload["chat_id"])

        for status in (400, 403):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                state = OffsetState(directory)
                api = API(status)
                process_updates(api, state, [
                    {"update_id": 4, "message": {"chat": {"id": 41, "type": "private"}, "text": "rejected"}},
                    {"update_id": 5, "message": {"chat": {"id": 42, "type": "private"}, "text": "hello"}},
                ])
                self.assertEqual(api.sent, [42])
                self.assertEqual(OffsetState(directory).offset, 6)

    def test_invalid_state_and_placeholder_token_fail_without_overwriting_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "offset.json")
            path.write_text('{"offset":"invalid"}')
            with self.assertRaises(ConfigurationError):
                OffsetState(directory)
            self.assertEqual(path.read_text(), '{"offset":"invalid"}')
        with self.assertRaises(ConfigurationError):
            TelegramAPI("replace_me")


if __name__ == "__main__":
    unittest.main()
