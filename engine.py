import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SERVICES = ["Ремонт стиральной машины", "Ремонт посудомоечной машины", "Другая техника"]
WELCOME = "Здравствуйте! Помогу составить заявку в мастерскую. Что нужно отремонтировать?"
STATUSES = {"new": "Новая", "progress": "В работе", "done": "Завершена"}
DEFAULT_DATABASE = Path(__file__).resolve().parent / "runtime" / "requests.sqlite3"


class Bot:
    def __init__(self, database):
        self.database = str(database)
        Path(self.database).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, step TEXT, data TEXT, history TEXT);
            CREATE TABLE IF NOT EXISTS events(session_id TEXT, request_id TEXT, response TEXT, PRIMARY KEY(session_id, request_id));
            CREATE TABLE IF NOT EXISTS leads(id TEXT PRIMARY KEY, session_id TEXT, created TEXT, service TEXT, description TEXT, contact TEXT, preferred TEXT, notified INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(leads)")}
            if "status" not in columns:
                db.execute("ALTER TABLE leads ADD COLUMN status TEXT NOT NULL DEFAULT 'new'")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def validate_session(session):
        if not isinstance(session, str) or not re.fullmatch(r"[A-Za-z0-9:_-]{8,100}", session):
            raise ValueError("Некорректный идентификатор сессии.")

    @staticmethod
    def buttons(step):
        return {
            "service": SERVICES,
            "description": ["Назад"],
            "contact": ["Назад"],
            "preferred": ["Как можно скорее", "В течение недели", "Назад"],
            "review": ["Отправить заявку", "Начать заново"],
            "done": ["Новая заявка"],
        }[step]

    def view(self, session):
        self.validate_session(session)
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session,)).fetchone()
        if not row:
            return {
                "step": "service",
                "history": [{"role": "bot", "text": WELCOME}],
                "buttons": SERVICES,
            }
        return {
            "step": row["step"],
            "history": json.loads(row["history"]),
            "buttons": self.buttons(row["step"]),
        }

    def send(self, session, text, request_id):
        self.validate_session(session)
        if not isinstance(text, str) or not text.strip() or len(text) > 1000:
            raise ValueError("Сообщение должно содержать от 1 до 1000 символов.")
        if not isinstance(request_id, str) or not re.fullmatch(
            r"[A-Za-z0-9:_-]{8,100}", request_id
        ):
            raise ValueError("Некорректный идентификатор сообщения.")
        text = text.strip()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT response FROM events WHERE session_id=? AND request_id=?",
                (session, request_id),
            ).fetchone()
            if previous:
                return json.loads(previous["response"])
            row = db.execute("SELECT * FROM sessions WHERE id=?", (session,)).fetchone()
            step, data, history = (
                ("service", {}, [{"role": "bot", "text": WELCOME}])
                if not row
                else (row["step"], json.loads(row["data"]), json.loads(row["history"]))
            )
            history.append({"role": "user", "text": text})
            created = None
            if text in ["/start", "/cancel", "Начать заново", "Новая заявка"]:
                step, data, message = "service", {}, WELCOME
            elif text == "Назад" and step in ["description", "contact", "preferred"]:
                step, message = {
                    "description": ("service", "Выберите технику."),
                    "contact": (
                        "description",
                        "Коротко опишите неисправность: от 10 до 600 символов.",
                    ),
                    "preferred": (
                        "contact",
                        "Укажите телефон, email или Telegram @username для ответа.",
                    ),
                }[step]
            elif step == "service":
                if text not in SERVICES:
                    message = "Выберите один из вариантов под сообщением."
                else:
                    data = {"service": text}
                    step, message = (
                        "description",
                        "Что случилось с техникой? Напишите модель и симптомы, если знаете. От 10 до 600 символов.",
                    )
            elif step == "description":
                if not 10 <= len(text) <= 600:
                    message = "Нужно описание от 10 до 600 символов. Например: «Машина не сливает воду, на экране ошибка E20»."
                else:
                    data["description"] = text
                    step, message = (
                        "contact",
                        "Как с вами связаться? Укажите телефон, email или Telegram @username.",
                    )
            elif step == "contact":
                valid = (
                    re.fullmatch(r"@[A-Za-z][A-Za-z0-9_]{4,31}", text)
                    or re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", text)
                    and len(text) <= 100
                    or re.fullmatch(r"\+?[\d ()-]{10,24}", text)
                    and 10 <= len(re.sub(r"\D", "", text)) <= 15
                )
                if not valid:
                    message = "Не удалось распознать контакт. Подойдёт телефон, email или Telegram вроде @client_name."
                else:
                    data["contact"] = text
                    step, message = (
                        "preferred",
                        "Когда вам удобно? Это пожелание: мастер отдельно согласует время. Можно выбрать вариант или написать свой (до 100 символов).",
                    )
            elif step == "preferred":
                if len(text) > 100:
                    message = "Сократите пожелание до 100 символов."
                else:
                    data["preferred"] = text
                    step = "review"
                    message = f"Проверьте заявку:\n\n{data['service']}\n{data['description']}\nКонтакт: {data['contact']}\nКогда: {text}\n\nНажмите «Отправить заявку», чтобы передать обращение в очередь мастерской."
            elif step == "review":
                if text != "Отправить заявку":
                    message = "Подтвердите заявку кнопкой или начните заново."
                else:
                    created = uuid.uuid4().hex[:10].upper()
                    db.execute(
                        "INSERT INTO leads(id,session_id,created,service,description,contact,preferred) VALUES(?,?,?,?,?,?,?)",
                        (
                            created,
                            session,
                            datetime.now(timezone.utc).isoformat(),
                            data["service"],
                            data["description"],
                            data["contact"],
                            data["preferred"],
                        ),
                    )
                    step, message = (
                        "done",
                        f"Заявка {created} сохранена. Время визита согласуется отдельно.",
                    )
            else:
                message = "Заявка уже сохранена. Чтобы создать ещё одну, нажмите «Новая заявка»."
            history.append({"role": "bot", "text": message})
            history = history[-32:]
            result = {
                "step": step,
                "history": history,
                "buttons": self.buttons(step),
                "created": created,
            }
            db.execute(
                "INSERT OR REPLACE INTO sessions VALUES(?,?,?,?)",
                (
                    session,
                    step,
                    json.dumps(data, ensure_ascii=False),
                    json.dumps(history, ensure_ascii=False),
                ),
            )
            db.execute(
                "INSERT INTO events VALUES(?,?,?)",
                (session, request_id, json.dumps(result, ensure_ascii=False)),
            )
            return result

    def leads(self):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,created,service,description,contact,preferred,status,notified,CASE WHEN session_id LIKE 'telegram:%' THEN 'telegram' ELSE 'web' END AS channel FROM leads ORDER BY created DESC LIMIT 100"
                )
            ]

    def set_status(self, identifier, status):
        if not isinstance(identifier, str) or not isinstance(status, str) or status not in STATUSES:
            raise ValueError("Неизвестная заявка или статус.")
        with self.connect() as db:
            changed = db.execute(
                "UPDATE leads SET status=? WHERE id=?", (status, identifier)
            ).rowcount
        if not changed:
            raise ValueError("Заявка не найдена.")
        return {"ok": True}

    def pending_notifications(self):
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM leads WHERE notified=0 AND session_id LIKE 'telegram:%' ORDER BY created LIMIT 20"
                )
            ]

    def mark_notified(self, identifier):
        with self.connect() as db:
            db.execute("UPDATE leads SET notified=1 WHERE id=?", (identifier,))

    def offset(self):
        with self.connect() as db:
            saved = db.execute("SELECT value FROM settings WHERE key='offset'").fetchone()
        return int(saved["value"]) if saved else 0

    def set_offset(self, offset):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO settings VALUES('offset',?)", (str(offset),))
