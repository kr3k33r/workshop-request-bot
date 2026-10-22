import argparse
import os
import time

from engine import Bot, DEFAULT_DATABASE
from telegram_client import TelegramClient, TelegramError
from telegram_service import deliver_notifications, process_update


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", default=str(DEFAULT_DATABASE))
    args = parser.parse_args()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    owner = os.environ.get("TELEGRAM_OWNER_CHAT_ID")
    if not token or not owner:
        raise SystemExit(
            "Задайте TELEGRAM_BOT_TOKEN и TELEGRAM_OWNER_CHAT_ID через переменные окружения."
        )
    if not owner.lstrip("-").isdigit():
        raise SystemExit("TELEGRAM_OWNER_CHAT_ID должен быть числовым chat_id.")
    bot, api = Bot(args.database), TelegramClient(token)
    try:
        if api("getWebhookInfo").get("url"):
            raise SystemExit(
                "У бота подключён webhook. Для polling используйте отдельного бота или самостоятельно отключите webhook."
            )
    except TelegramError:
        raise SystemExit(
            "Не удалось подключиться к Telegram. Проверьте токен и доступность сети."
        ) from None
    print("Telegram connected. Stop: Ctrl+C.")
    while True:
        try:
            deliver_notifications(bot, api, owner)
            updates = api(
                "getUpdates", offset=bot.offset(), timeout=25, allowed_updates=["message"]
            )
            for update in updates:
                process_update(bot, api, owner, update)
                bot.set_offset(update["update_id"] + 1)
                deliver_notifications(bot, api, owner)
        except KeyboardInterrupt:
            return
        except TelegramError:
            print("Telegram temporarily unavailable. Retrying in 5 seconds.")
            time.sleep(5)


if __name__ == "__main__":
    run()
