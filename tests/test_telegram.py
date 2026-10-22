import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Bot, SERVICES
from telegram_client import TelegramClient, TelegramError
from telegram_service import deliver_notifications, process_update


class TelegramTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.bot = Bot(Path(self.temp.name) / "requests.sqlite3")
        self.calls = []
        self.update_id = 100

    def tearDown(self):
        self.temp.cleanup()

    def api(self, method, **payload):
        self.calls.append((method, payload))
        return {"message_id": len(self.calls)}

    def update(self, text, chat=200):
        self.update_id += 1
        update = {
            "update_id": self.update_id,
            "message": {"chat": {"id": chat, "type": "private"}, "text": text},
        }
        process_update(self.bot, self.api, 999, update)
        return update

    def create_lead(self):
        for text in [
            SERVICES[0],
            "Не сливает воду, ошибка E20",
            "@sample_client",
            "В течение недели",
            "Отправить заявку",
        ]:
            last = self.update(text)
        return last

    def test_customer_request_and_owner_delivery(self):
        self.create_lead()
        self.assertEqual(deliver_notifications(self.bot, self.api, 999), 1)
        notification = self.calls[-1][1]
        self.assertEqual(notification["chat_id"], 999)
        self.assertIn("@sample_client", notification["text"])
        self.assertIn("/take ", notification["text"])
        self.assertEqual(deliver_notifications(self.bot, self.api, 999), 0)

    def test_replayed_update_does_not_duplicate_lead(self):
        update = self.create_lead()
        process_update(self.bot, self.api, 999, update)
        self.assertEqual(len(self.bot.leads()), 1)

    def test_delivery_failure_preserves_outbox(self):
        self.create_lead()

        def unavailable(*args, **kwargs):
            raise TelegramError()

        with self.assertRaises(TelegramError):
            deliver_notifications(self.bot, unavailable, 999)
        self.assertEqual(len(self.bot.pending_notifications()), 1)
        self.assertEqual(deliver_notifications(self.bot, self.api, 999), 1)

    def test_owner_can_manage_status_and_customer_cannot(self):
        self.create_lead()
        identifier = self.bot.leads()[0]["id"]
        self.update("/take " + identifier, chat=999)
        self.assertEqual(self.bot.leads()[0]["status"], "progress")
        self.update("/done " + identifier, chat=200)
        self.assertEqual(self.bot.leads()[0]["status"], "progress")
        self.update("/done " + identifier, chat=999)
        self.assertEqual(self.bot.leads()[0]["status"], "done")

    def test_web_request_never_enters_telegram_outbox(self):
        for index, text in enumerate(
            [SERVICES[0], "Не сливает воду", "@sample_client", "На неделе", "Отправить заявку"]
        ):
            self.bot.send("web_session", text, "request_" + str(index))
        self.assertEqual(self.bot.pending_notifications(), [])
        self.assertEqual(self.bot.leads()[0]["channel"], "web")

    def test_offset_persists_and_bad_status_rejected(self):
        self.bot.set_offset(567)
        self.assertEqual(Bot(self.bot.database).offset(), 567)
        with self.assertRaises(ValueError):
            self.bot.set_status("unknown", [])

    def test_telegram_http_error_does_not_disclose_token(self):
        token = "12345:secret_token"
        with patch(
            "urllib.request.urlopen",
            side_effect=HTTPError(
                "https://api.telegram.org/bot" + token, 403, "Forbidden", {}, None
            ),
        ):
            with self.assertRaises(TelegramError) as raised:
                TelegramClient(token)("sendMessage", chat_id=1, text="hello")
        self.assertNotIn(token, str(raised.exception))
        self.assertFalse(raised.exception.retryable)

    def test_blocked_customer_does_not_block_processing(self):
        def blocked(*args, **kwargs):
            raise TelegramError(retryable=False)

        process_update(
            self.bot,
            blocked,
            999,
            {
                "update_id": 10,
                "message": {"chat": {"id": 200, "type": "private"}, "text": "/start"},
            },
        )
