import sys
import tempfile
import unittest
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Bot, SERVICES


class BotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "db.sqlite3"
        self.bot = Bot(self.path)
        self.session = "session_123456"

    def tearDown(self):
        self.temp.cleanup()

    def send(self, text):
        return self.bot.send(self.session, text, str(uuid.uuid4()))

    def prepare(self):
        for text in [
            SERVICES[0],
            "Не сливает воду, ошибка E20",
            "@sample_client",
            "В течение недели",
        ]:
            self.send(text)

    def test_full_flow_duplicate_confirmation_and_restart(self):
        self.prepare()
        request = str(uuid.uuid4())
        first = self.bot.send(self.session, "Отправить заявку", request)
        second = self.bot.send(self.session, "Отправить заявку", request)
        self.assertEqual(first["created"], second["created"])
        self.send("Отправить заявку")
        self.assertEqual(len(self.bot.leads()), 1)
        self.assertEqual(Bot(self.path).view(self.session)["step"], "done")
        self.send("Новая заявка")
        self.assertEqual(self.bot.view(self.session)["step"], "service")

    def test_invalid_description_and_contact_stay_in_step(self):
        self.send(SERVICES[0])
        self.assertEqual(self.send("нет")["step"], "description")
        self.send("Не сливает воду")
        self.assertEqual(self.send("abc")["step"], "contact")
        self.assertEqual(self.send("@valid_name")["step"], "preferred")

    def test_cancel_does_not_create_lead(self):
        self.prepare()
        self.assertEqual(self.send("/cancel")["step"], "service")
        self.assertEqual(self.bot.leads(), [])

    def test_back_can_change_service(self):
        self.send(SERVICES[0])
        self.send("Назад")
        self.send(SERVICES[1])
        self.send("Не включается техника")
        self.send("client@example.invalid")
        self.send("В течение недели")
        self.send("Отправить заявку")
        self.assertEqual(self.bot.leads()[0]["service"], SERVICES[1])

    def test_sessions_isolated(self):
        self.prepare()
        self.assertEqual(self.bot.view("other_session")["step"], "service")

    def test_bad_identifiers_rejected(self):
        with self.assertRaises(ValueError):
            self.bot.send("../bad", "hello", "request_123")


if __name__ == "__main__":
    unittest.main()
