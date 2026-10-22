import argparse
from pathlib import Path
from urllib.parse import parse_qs
from engine import Bot, DEFAULT_DATABASE, STATUSES
from local_server import serve

ROOT = Path(__file__).resolve().parent
bot = None


def get_api(path, query):
    if path == "/api/session":
        return bot.view(parse_qs(query).get("id", [""])[0])
    if path == "/api/leads":
        return {"leads": bot.leads(), "statuses": STATUSES}


def post_api(path, payload):
    if path == "/api/message":
        if isinstance(payload.get("session"), str) and ":" in payload["session"]:
            raise ValueError("Недопустимая сессия браузера.")
        return bot.send(payload.get("session"), payload.get("text"), payload.get("request_id"))
    if path == "/api/status":
        return bot.set_status(payload.get("id"), payload.get("status"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    args = parser.parse_args()
    bot = Bot(args.database)
    serve(ROOT / "web", get_api, post_api, args.port)
