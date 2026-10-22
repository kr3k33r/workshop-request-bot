import json
import urllib.error
import urllib.request


class TelegramError(Exception):
    def __init__(self, retryable=True):
        super().__init__("Telegram request failed")
        self.retryable = retryable


class TelegramClient:
    def __init__(self, token):
        self.token = token

    def __call__(self, method, **payload):
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                data = json.load(response)
        except urllib.error.HTTPError as error:
            raise TelegramError(error.code == 429 or error.code >= 500) from None
        except (OSError, ValueError):
            raise TelegramError() from None
        if not data.get("ok"):
            code = data.get("error_code", 500)
            raise TelegramError(code == 429 or code >= 500)
        return data["result"]
