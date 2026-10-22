from engine import STATUSES
from telegram_client import TelegramError


def lead_message(lead):
    return (
        f"Заявка {lead['id']}\n{lead['service']}\n{lead['description']}\n"
        f"Контакт: {lead['contact']}\nКогда удобно: {lead['preferred']}\n"
        f"В работу: /take {lead['id']}\nЗавершить: /done {lead['id']}"
    )


def owner_reply(bot, text):
    parts = text.split(maxsplit=1)
    command = parts[0].split("@")[0].lower()
    if command in ["/requests", "/inbox"]:
        leads = [lead for lead in bot.leads() if lead["channel"] == "telegram"][:10]
        if not leads:
            return "Заявок из Telegram пока нет."
        return "\n\n".join(
            f"{lead['id']} · {STATUSES[lead['status']]}\n{lead['service']}\n{lead['contact']}"
            for lead in leads
        )
    if command in ["/take", "/done"]:
        if len(parts) != 2:
            return f"Укажите номер: {command} НОМЕР_ЗАЯВКИ"
        identifier = parts[1].strip().upper()
        if not any(
            lead["id"] == identifier and lead["channel"] == "telegram" for lead in bot.leads()
        ):
            return "Заявка из Telegram с таким номером не найдена в последних 100 обращениях."
        bot.set_status(identifier, "progress" if command == "/take" else "done")
        return f'Статус заявки {identifier}: {"В работе" if command == "/take" else "Завершена"}.'
    return "Очередь мастерской:\n/requests — последние заявки\n/take НОМЕР — взять в работу\n/done НОМЕР — завершить"


def process_update(bot, api, owner, update):
    message = update.get("message", {})
    chat = message.get("chat", {})
    text = message.get("text")
    if not isinstance(text, str) or not text.strip():
        return
    if str(chat.get("id")) == str(owner):
        api("sendMessage", chat_id=owner, text=owner_reply(bot, text))
        return
    if chat.get("type") != "private":
        return
    try:
        result = bot.send("telegram:" + str(chat["id"]), text, "update:" + str(update["update_id"]))
        reply = result["history"][-1]["text"]
        markup = {
            "keyboard": [[{"text": label}] for label in result["buttons"]],
            "resize_keyboard": True,
        }
    except ValueError as error:
        reply, markup = str(error), None
    try:
        api(
            "sendMessage",
            chat_id=chat["id"],
            text=reply,
            **({"reply_markup": markup} if markup else {}),
        )
    except TelegramError as error:
        if error.retryable:
            raise


def deliver_notifications(bot, api, owner):
    delivered = 0
    for lead in bot.pending_notifications():
        api("sendMessage", chat_id=owner, text=lead_message(lead))
        bot.mark_notified(lead["id"])
        delivered += 1
    return delivered
