# src/bale_api.py
"""
کلاس API بله - نسخه اصلاح‌شده و کاملاً سازگار با ارسال فایل (sendDocument)
"""

import os
import mimetypes
import requests
from typing import Optional, Dict, List


class BaleAPI:
    def __init__(self, token: str):
        self.token = token
        self.base_url = f"https://tapi.bale.ai/bot{token}"

        # 🔹 Session برای درخواست‌های JSON
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json"
        })

    # ---------------------------
    # متد عمومی ارسال درخواست JSON
    # ---------------------------
    def _make_request(
        self,
        method: str,
        data: Optional[Dict] = None,
        http_method: str = "POST"
    ) -> Optional[Dict]:

        url = f"{self.base_url}/{method}"

        try:
            if http_method.upper() == "GET":
                response = self.session.get(url, params=data, timeout=30)
            else:
                response = self.session.post(url, json=data, timeout=30)

            response.raise_for_status()
            result = response.json()

            if not result.get("ok", False):
                print(f"❌ API Error: {result}")
                return None

            return result

        except Exception as e:
            print(f"❌ API JSON Error: {e}")
            return None

    # ---------------------------
    # دریافت آپدیت‌ها
    # ---------------------------
    def get_updates(self, offset: int = 0, timeout: int = 30) -> Optional[Dict]:
        data = {"offset": offset, "timeout": timeout}
        return self._make_request("getUpdates", data)

    # ---------------------------
    # ارسال پیام با قالب HTML
    # ---------------------------
    def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict] = None,
        parse_mode: Optional[str] = None
    ) -> Optional[Dict]:

        data = {"chat_id": chat_id, "text": text}

        if parse_mode:
            data["parse_mode"] = parse_mode

        if reply_markup:
            data["reply_markup"] = reply_markup

        return self._make_request("sendMessage", data)

    # ---------------------------
    # دکمه مینی‌اپ
    # ---------------------------
    def create_miniapp_button(self, text: str = "🌐 ورود به مینی‌اپ") -> Dict:
        """دکمه اینلاین که مینی‌اپ را باز می‌کند (نیاز به WEB_APP_URL در config)"""
        from src.config import WEB_APP_URL

        if not WEB_APP_URL:
            return {"inline_keyboard": []}

        return {
            "inline_keyboard": [
                [{"text": text, "web_app": {"url": WEB_APP_URL}}]
            ]
        }

    def add_miniapp_button(self, text: str = "🌐 ورود به مینی‌اپ") -> Dict:
        """دکمه مینی‌اپ برای اضافه کردن به کیبوردهای اینلاین موجود"""
        from src.config import WEB_APP_URL

        if not WEB_APP_URL:
            return {"inline_keyboard": []}

        return {
            "inline_keyboard": [
                [{"text": text, "web_app": {"url": WEB_APP_URL}}]
            ]
        }

    # ---------------------------
    # حذف پیام
    # ---------------------------
    def delete_message(self, chat_id: int, message_id: int) -> Optional[Dict]:
        data = {"chat_id": chat_id, "message_id": message_id}
        return self._make_request("deleteMessage", data)

    # ---------------------------
    # پاسخ callback
    # ---------------------------
    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str = "",
        show_alert: bool = False
    ) -> Optional[Dict]:

        data = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert
        }
        return self._make_request("answerCallbackQuery", data)

    # ---------------------------
    # ارسال فایل (اصلاح‌شده)
    # ---------------------------
    def send_document(
        self,
        chat_id: int,
        document_path: str,
        caption: Optional[str] = None
    ) -> Optional[Dict]:

        url = f"{self.base_url}/sendDocument"

        if not os.path.exists(document_path):
            print(f"❌ File not found: {document_path}")
            return None

        filename = os.path.basename(document_path)
        mime, _ = mimetypes.guess_type(document_path)
        mime = mime or "application/octet-stream"

        data = {"chat_id": str(chat_id)}
        if caption:
            data["caption"] = caption

        try:
            # 🔥 مهم: اینجا session را استفاده نمی‌کنیم چون هدر JSON دارد
            with open(document_path, "rb") as f:
                files = {
                    "document": (filename, f, mime)
                }

                response = requests.post(url, data=data, files=files, timeout=60)

            print("📤 sendDocument status:", response.status_code)
            print("📤 sendDocument response:", response.text)

            response.raise_for_status()

            result = response.json()

            if not result.get("ok", False):
                print(f"❌ API Error (sendDocument): {result}")
                return None

            return result

        except Exception as e:
            print(f"❌ Error sending document: {e}")
            return None

    # ---------------------------
    # کیبوردها
    # ---------------------------
    def create_keyboard(
        self,
        buttons: List[List[str]],
        one_time: bool = False
    ) -> Dict:

        keyboard = [[{"text": b} for b in row] for row in buttons]

        return {
            "keyboard": keyboard,
            "resize_keyboard": True,
            "one_time_keyboard": one_time
        }

    def create_contact_keyboard(self) -> Dict:
        return {
            "keyboard": [
                [{"text": "📱 اشتراک‌گذاری شماره تماس", "request_contact": True}]
            ],
            "resize_keyboard": True,
            "one_time_keyboard": True
        }

    def create_inline_keyboard(self, buttons: List[List[Dict]]) -> Dict:
        return {"inline_keyboard": buttons}

    def remove_keyboard(self) -> Dict:
        return {"remove_keyboard": True}
