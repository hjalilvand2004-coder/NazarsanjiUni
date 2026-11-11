"""
bot.py — نسخه ۲.۲.۰
بازوی بله سامانه نظرسنجی دروس
+ منوی انتخاب کانال (بات/مینی‌اپ/وب) در شروع
+ نمایش نسخه هنگام استارت
+ ترم فعال از جدول surveys خوانده می‌شود
+ اعتبارسنجی شماره دانشجویی مطابق منطق اصلی
"""

import os
import sys
import time
from collections import defaultdict

import pandas as pd
from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from src.config import (
    BALE_BOT_TOKEN, MESSAGES, MAX_COURSES_PER_USER,
    APP_VERSION, WEB_APP_URL, WEBSITE_URL, CHANNEL_BOT
)
from src.bale_api import BaleAPI
from src.database import Database
from src.helpers import SECTION_LABELS  # noqa: F401

PARSE_MODE = "HTML"


# نمایش بنر نسخه هنگام import (برای اطمینان از نسخه در حال اجرا)
def _print_version_banner():
    try:
        db = Database()
        survey = db.get_active_survey()
        if survey:
            survey_name = survey["name"]
            deadline = survey.get("deadline") or "—"
            status_label = f"✓ {survey_name}"
        else:
            survey_name = "(هیچ نظرسنجی فعالی وجود ندارد)"
            deadline = "—"
            status_label = "⚠️  " + survey_name
    except Exception as e:
        status_label = f"❌ Error reading survey: {e}"
        deadline = "—"
    print("=" * 60)
    print(f"  Bale Bot v{APP_VERSION}")
    print(f"  Active Survey: {status_label}")
    print(f"  Deadline: {deadline}")
    print(f"  Web URL:  {WEB_APP_URL}")
    print(f"  Website:  {WEBSITE_URL}")
    print("=" * 60)
    sys.stdout.flush()


def _miniapp_row():
    """ردیف دکمه مینی‌اپ (فقط اگر WEB_APP_URL تنظیم شده باشد)"""
    from src.config import WEB_APP_URL
    if not WEB_APP_URL:
        return None
    return [{"text": "🌐 ورود به مینی‌اپ", "web_app": {"url": WEB_APP_URL}}]


SECTION_OPTIONS = {
    "پایه": "basic",
    "اصلی": "core",
    "تخصصی": "specialized",
    "تخصصی نرم افزار": "specialized_sw",
    "تخصصی اختیاری نرم افزار": "specialized_elective_sw",
    "تخصصی هوش": "specialized_ai",
    "پیش نیاز": "Prerequisite",
    "اختیاری": "electives"
}

SECTION_LABELS = {
    "basic": "پایه",
    "core": "اصلی",
    "specialized": "تخصصی",
    "specialized_sw": "تخصصی نرم افزار",
    "specialized_elective_sw":"تخصصی اختیاری نرم افزار",
    "specialized_ai": "تخصصی هوش",
    "Prerequisite": "پیش نیاز",
    "electives": "اختیاری"
}


class UserState:
    def __init__(self):
        self.phone = None
        self.user_info = None
        self.reg_step = 0

        self.multi_select = False
        self.selected_courses = []
        self.select_message_id = None

        self.is_admin = False
        self.admin_step = 0
        self.temp_course_data = {}


class CourseSurveyBot:
    def __init__(self):
        self.api = BaleAPI(BALE_BOT_TOKEN)
        self.db = Database()
        self.user_states = {}
        self.last_update_id = 0

    # ---------------------- Normalization ---------------------- #
    def normalize_digits(self, value):
        """تبدیل اعداد فارسی/عربی به انگلیسی"""
        if value is None:
            return value
        return str(value).translate(
            str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        ).strip()

    def normalize_text(self, value):
        if value is None:
            return ""
        return self.normalize_digits(str(value).strip())

    def normalize_phone(self, phone):
        phone = self.normalize_digits(str(phone))
        phone = phone.replace(" ", "").replace("-", "")

        # همه شماره‌ها به فرم 09xxxxxxxxx
        if phone.startswith("+98"):
            phone = "0" + phone[3:]
        if phone.startswith("98"):
            phone = "0" + phone[2:]

        if phone.startswith("09") and len(phone) == 11:
            return phone
        return phone

    # ---------------- Helper for student/admin/years ---------------- #
    def is_admin_student_number(self, student_number: str):
        return self.normalize_digits(student_number) == "000000000"

    def get_courses_year_by_student_number(self, student_number: str):
        student_number = self.normalize_digits(student_number)
        if not student_number:
            return None

        p2, p3 = student_number[:2], student_number[:3]

        if p2 in ['94', '95', '96', '97', '98', '99'] or p3 in ['400', '401', '402']:
            return 1394
        if p3 in ['403', '404', '405']:
            return 1403
        return None

    def get_available_courses_for_user(self, user_info):
        student_number = self.normalize_digits(user_info["student_number"])
        student_type = self.normalize_text(user_info["student_type"])

        courses = self.db.get_all_courses()

        # اگر دانشجو ناپیوسته باشد
        if student_type == "ناپیوسته":
            return [
                c for c in courses
                if self.normalize_text(c.get("type_coures")) == "ناپیوسته"
            ]

        # اگر دانشجو پیوسته باشد
        year = self.get_courses_year_by_student_number(student_number)

        if not year:
            return []

        return [
            c for c in courses
            if c["year"] == year and self.normalize_text(c.get("type_coures")) == "پیوسته"
        ]

    def format_admin_courses_grouped(self, courses):
        if not courses:
            return "هیچ درسی در دیتابیس ثبت نشده است."

        grouped = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

        for c in courses:
            year = c.get("year", "نامشخص")
            course_type = self.normalize_text(c.get("type_coures")) or "نامشخص"
            section = SECTION_LABELS.get(c.get("section"), c.get("section", "نامشخص"))
            grouped[year][course_type][section].append(c)

        text = "📋 لیست دسته‌بندی‌شده دروس:\n"

        for year in sorted(grouped.keys()):
            text += f"\n====================\n🗓 سال {year}\n====================\n"

            for course_type in ["پیوسته", "ناپیوسته", "نامشخص"]:
                if course_type not in grouped[year]:
                    continue

                text += f"\n🎓 نوع: {course_type}\n"

                for section in ["پایه", "اصلی", "تخصصی", "تخصصی هوش", "اختیاری"]:
                    if section not in grouped[year][course_type]:
                        continue

                    text += f"  📚 {section}:\n"

                    section_courses = sorted(
                        grouped[year][course_type][section],
                        key=lambda x: (
                            x["row_number"] if x["row_number"] is not None else 9999,
                            x["course_title"]
                        )
                    )

                    for c in section_courses:
                        row_number = c["row_number"] if c["row_number"] is not None else "-"
                        credits = c["credits"] if c["credits"] else "-"
                        text += f"    ▫️ ردیف {row_number} | {c['course_title']} | {credits} واحد\n"

        return text

    # ---------------------- Excel Report ---------------------- #
    def generate_excel_report(self, chat_id):
        """
        ساخت فایل اکسل گزارش پیشنهادات به همراه نمودار خودکار
        """

        query = """
            SELECT 
                COALESCE(c.year, -1) AS year,
                u.student_type AS student_type,
                COALESCE(c.course_title, cr.course_name) AS course_title,
                COUNT(*) AS count
            FROM course_requests cr
            JOIN authorized_users u ON cr.user_id = u.id
            LEFT JOIN courses c ON cr.id_courses = c.id
            GROUP BY 
                COALESCE(c.year, -1),
                u.student_type,
                COALESCE(c.course_title, cr.course_name)
            ORDER BY year DESC, count DESC
        """

        results = self.db.execute_query(query)

        if not results:
            self.api.send_message(chat_id, "هنوز هیچ پیشنهادی برای تهیه گزارش اکسل ثبت نشده است.")
            self.show_admin_menu(chat_id)
            return

        # ---- ساخت DataFrame با نام‌گذاری مطمئن ستون‌ها ---- #
        df = pd.DataFrame(results)

        if df.empty:
            self.api.send_message(chat_id, "داده‌ای برای ساخت گزارش اکسل وجود ندارد.")
            self.show_admin_menu(chat_id)
            return

        # اگر ستون year وجود ندارد، حدس بزنیم خروجی tuple بوده
        if "year" not in df.columns:
            # انتظار: ترتیب ستون‌ها مطابق SELECT
            # (year, student_type, course_title, count)
            if df.shape[1] >= 4:
                df = df.rename(columns={
                    df.columns[0]: "year",
                    df.columns[1]: "student_type",
                    df.columns[2]: "course_title",
                    df.columns[3]: "count",
                })
            else:
                # اگر شکل غیرمنتظره است، پیام خطای خوانا بده
                self.api.send_message(
                    chat_id,
                    "❌ ساختار داده‌های گزارش (ستون year) نامعتبر است. "
                    "لطفاً تابع execute_query یا کوئری را بررسی کنید."
                )
                self.show_admin_menu(chat_id)
                return

        # حالا فرض می‌کنیم year, student_type, course_title, count وجود دارد

        # نرمال‌سازی و نام‌گذاری فارسی
        df["year"] = df["year"].apply(lambda x: "نامشخص" if x == -1 or x is None else str(x))
        df["student_type"] = df["student_type"].apply(lambda x: self.normalize_text(x))
        df["course_title"] = df["course_title"].apply(lambda x: self.normalize_text(x))
        df["count"] = pd.to_numeric(df["count"], errors="coerce").fillna(0).astype(int)

        raw_df = df.rename(columns={
            "year": "سال",
            "student_type": "نوع دانشجو",
            "course_title": "نام درس",
            "count": "تعداد پیشنهاد"
        })

        # ---------------- Summary sheet ---------------- #
        summary_df = (
            raw_df.groupby("نام درس", as_index=False)["تعداد پیشنهاد"]
            .sum()
            .sort_values(by="تعداد پیشنهاد", ascending=False)
        )

        chart_df = summary_df.head(20).copy()

        file_path = "report.xlsx"

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            raw_df.to_excel(writer, sheet_name="داده_خام", index=False)
            summary_df.to_excel(writer, sheet_name="خلاصه", index=False)
            chart_df.to_excel(writer, sheet_name="نمودار", index=False)

        # ---------------- Openpyxl formatting ---------------- #
        wb = load_workbook(file_path)

        header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
        header_font = Font(color="FFFFFF", bold=True)
        center_alignment = Alignment(horizontal="center", vertical="center")

        for ws in wb.worksheets:
            ws.freeze_panes = "A2"

            for cell in ws[1]:
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = center_alignment

            for col_cells in ws.columns:
                max_length = 0
                col_letter = get_column_letter(col_cells[0].column)
                for cell in col_cells:
                    try:
                        val = str(cell.value) if cell.value is not None else ""
                        if len(val) > max_length:
                            max_length = len(val)
                    except Exception:
                        pass
                ws.column_dimensions[col_letter].width = min(max(max_length + 2, 12), 40)

        # ---------------- Chart sheet ---------------- #
        ws_chart = wb["نمودار"]

        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = "نمودار تعداد پیشنهاد هر درس"
        chart.y_axis.title = "تعداد پیشنهاد"
        chart.x_axis.title = "نام درس"
        chart.height = 12
        chart.width = 22

        data = Reference(ws_chart, min_col=2, min_row=1, max_row=ws_chart.max_row)
        categories = Reference(ws_chart, min_col=1, min_row=2, max_row=ws_chart.max_row)

        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)

        ws_chart.add_chart(chart, "D2")

        wb.save(file_path)

        try:
            self.api.send_message(chat_id, "📊 فایل اکسل گزارش با موفقیت ساخته شد. در حال ارسال...")
            self.api.send_document(chat_id, file_path)
        except Exception as e:
            self.api.send_message(chat_id, f"❌ خطا در ارسال فایل اکسل: {e}")
            self.show_admin_menu(chat_id)
            return

        self.show_admin_menu(chat_id)
    # ------------------ Start/Contact/Registration ------------------ #
    def handle_start(self, chat_id):
        """منوی شروع: کاربر انتخاب می‌کند از چه کانالی ادامه دهد"""
        self.user_states[chat_id] = UserState()

        # خواندن ترم فعال از دیتابیس
        survey = self.db.get_active_survey()
        if survey:
            survey_status = MESSAGES["active_survey_info"].format(
                semester=survey["name"], deadline=survey.get("deadline") or "—"
            )
        else:
            survey_status = MESSAGES["no_active_survey"]

        welcome = MESSAGES["welcome"].format(survey_status=survey_status)

        # کیبورد اینلاین با سه گزینه
        kb = [
            [{"text": "📱 مینی‌اپ بله", "callback_data": "chan_miniapp"}],
            [{"text": "🌐 وب‌سایت", "callback_data": "chan_website"}],
            [{"text": "💬 ادامه در همین بات", "callback_data": "chan_bot"}],
            [
                {"text": "🌐 باز کردن سایت", "url": WEBSITE_URL},
                {"text": "📲 دانلود موبایل اپ", "url": WEBSITE_URL + "/download-app"},
            ],
        ]
        self.api.send_message(
            chat_id, welcome,
            self.api.create_inline_keyboard(kb),
            parse_mode=PARSE_MODE
        )

    def handle_channel_choice(self, chat_id, choice):
        """پاسخ به انتخاب کانال توسط کاربر"""
        if choice == "chan_miniapp":
            msg = MESSAGES["channel_chosen_miniapp"].format(web_app_url=WEB_APP_URL)
            # دکمه اینلاین برای باز کردن مینی‌اپ
            kb = self.api.create_inline_keyboard([
                [{"text": "🌐 ورود به مینی‌اپ", "web_app": {"url": WEB_APP_URL}}],
                [
                    {"text": "🌐 وب‌سایت", "url": WEBSITE_URL},
                    {"text": "📲 دانلود موبایل اپ", "url": WEBSITE_URL + "/download-app"},
                ],
                [{"text": "↩ بازگشت به منو", "callback_data": "back_to_start"}],
            ])
            self.api.send_message(chat_id, msg, kb, parse_mode=PARSE_MODE)

        elif choice == "chan_website":
            msg = MESSAGES["channel_chosen_website"].format(website_url=WEBSITE_URL)
            kb = self.api.create_inline_keyboard([
                [{"text": "🌐 باز کردن وب‌سایت", "url": WEBSITE_URL}],
                [{"text": "↩ بازگشت به منو", "callback_data": "back_to_start"}],
            ])
            self.api.send_message(chat_id, msg, kb, parse_mode=PARSE_MODE)

        elif choice == "chan_bot":
            msg = MESSAGES["channel_chosen_bot"]
            kb = self.api.create_contact_keyboard()
            # اضافه‌کردن دکمه بازگشت
            kb["keyboard"].append([{"text": "↩ بازگشت به منو اصلی"}])
            self.api.send_message(chat_id, msg, kb, parse_mode=PARSE_MODE)

    def handle_contact(self, message):
        chat_id = message["chat"]["id"]
        phone = self.normalize_phone(message["contact"]["phone_number"])

        if chat_id not in self.user_states:
            self.user_states[chat_id] = UserState()

        state = self.user_states[chat_id]
        state.phone = phone

        user_info = self.db.is_user_authorized(phone)

        if not user_info:
            # ثبت کانال اولیه ورود
            self.db.record_login(None, CHANNEL_BOT)  # بدون user_id (هنوز ثبت نشده)
            self.start_registration(chat_id)
        else:
            if user_info.get("student_number"):
                user_info["student_number"] = self.normalize_digits(user_info["student_number"])
            if user_info.get("student_type"):
                user_info["student_type"] = self.normalize_text(user_info["student_type"])

            state.user_info = user_info

            # ثبت ورود کاربر در تاریخچه
            self.db.record_login(
                user_info["id"], CHANNEL_BOT,
                ip_address=None,
                user_agent="bale-bot"
            )

            if self.is_admin_student_number(user_info['student_number']):
                state.is_admin = True
                self.show_admin_menu(chat_id)
            else:
            # ⛔ جلوگیری از شرکت دوباره
                if self.db.has_user_submitted_courses(user_info["id"]):
                    self.api.send_message(
                        chat_id,
                        "❌ شما قبلاً پیشنهاد درس خود را ثبت کرده‌اید و امکان شرکت دوباره وجود ندارد."
                    )
                    return

                self.api.send_message(
                    chat_id,
                    MESSAGES["auth_success"].format(name=user_info["name"], phone=phone)
                )
                self.start_multi_course_selection(chat_id)


    def start_registration(self, chat_id):
        state = self.user_states[chat_id]
        state.reg_step = 1
        self.api.send_message(chat_id, "ثبت‌نام لازم است.\nلطفاً نام و نام خانوادگی را وارد کنید:")

    def handle_registration(self, chat_id, text):
        state = self.user_states[chat_id]
        text = self.normalize_text(text)

        if state.reg_step == 1:
            state.user_info = {"name": text}
            state.reg_step = 2
            self.api.send_message(chat_id, "شماره دانشجویی را وارد کنید :")

        elif state.reg_step == 2:
            student_number = self.normalize_digits(text)

            # اعتبارسنجی شماره دانشجویی از طریق دیتابیس
            valid, role_or_error = self.db.validate_student_number(student_number)

            if not valid:
                self.api.send_message(chat_id, f"❌ {role_or_error}")
                return

            # جلوگیری از ثبت‌نام تکراری با شماره تلفن یا شماره دانشجویی
            if self.db.user_exists(state.phone, student_number):
                self.api.send_message(
                    chat_id,
                    "شما با این شماره تلفن یا شماره دانشجویی قبلا یکبار ثبت پیشنهاد نموده اید."
                )
                return

            state.user_info["student_number"] = student_number

            # اگر ادمین باشد، مستقیم ثبت نهایی شود
            if role_or_error == "admin":
                self.finalize_reg(chat_id, "پیوسته")
                return

            # کاربر عادی: انتخاب نوع کارشناسی
            state.reg_step = 3
            kb = [
                [{"text": "پیوسته", "callback_data": "reg_p"}],
                [{"text": "ناپیوسته", "callback_data": "reg_np"}]
            ]
            self.api.send_message(chat_id, "نوع کارشناسی:", self.api.create_inline_keyboard(kb))

    def finalize_reg(self, chat_id, stype):
        state = self.user_states[chat_id]
        sn = self.normalize_digits(state.user_info["student_number"])
        stype = self.normalize_text(stype)
        phone = self.normalize_phone(state.phone)

        role = "admin" if self.is_admin_student_number(sn) else "user"

        if role == "admin":
            stype = "پیوسته"

        self.db.add_authorized_user(state.user_info["name"], phone, sn, stype, role)
        state.user_info = self.db.is_user_authorized(phone)

        if not state.user_info:
            self.api.send_message(chat_id, "❌ خطای داخلی در ثبت‌نام. لطفاً /start را مجدداً ارسال کنید.")
            state.reg_step = 0
            return

        if state.user_info.get("student_number"):
            state.user_info["student_number"] = self.normalize_digits(state.user_info["student_number"])
        if state.user_info.get("student_type"):
            state.user_info["student_type"] = self.normalize_text(state.user_info["student_type"])

        state.reg_step = 0

        if role == "admin":
            state.is_admin = True
            self.show_admin_menu(chat_id)
        else:
            self.start_multi_course_selection(chat_id)

    # ---------------------- Admin panel & report ---------------------- #
    def show_admin_menu(self, chat_id):
        kb = [
            [{"text": "➕ ثبت درس جدید", "callback_data": "admin_add_course"}],
            [{"text": "📋 لیست تمام درس‌ها", "callback_data": "admin_list_courses"}],
            [{"text": "📘 لیست دروس در اکسل", "callback_data": "admin_courses_excel"}],
            [{"text": "📊 گزارش آمار پیشنهادات", "callback_data": "admin_report"}],
            [{"text": "👥 آمار مشارکت دانشجویان", "callback_data": "admin_participation"}],
            [{"text": "📁 نتایج در اکسل", "callback_data": "admin_report_excel"}]
        ]

        row = _miniapp_row()
        if row:
            kb.append(row)

        self.api.send_message(
            chat_id,
            "🔧 <b>پنل مدیریت</b>\n"
            "─────────────────\n"
            "گزینه مورد نظر را انتخاب کنید:\n\n"
            "💡 برای تجربه بهتر، از دکمه «🌐 ورود به مینی‌اپ» استفاده کنید؛ "
            "نمودارها، مدیریت دروس و خروجی اکسل همه در یک رابط کاربری شکیل!",
            self.api.create_inline_keyboard(kb),
            parse_mode=PARSE_MODE
        )

    def handle_admin_flow(self, chat_id, text):
        state = self.user_states[chat_id]
        step = state.admin_step
        text = self.normalize_text(text)

        if step == 1:
            state.temp_course_data['title'] = text
            state.admin_step = 2
            kb = [[{"text": k, "callback_data": f"sect:{v}"}] for k, v in SECTION_OPTIONS.items()]
            self.api.send_message(chat_id, "بخش (Section) درس را انتخاب کنید:", self.api.create_inline_keyboard(kb))


        elif step == 3:

            if text not in ["1394", "1403", "100"]:
                self.api.send_message(chat_id, "لطفاً فقط 1394 یا 1403 یا 100 وارد کنید:")

                return

            state.temp_course_data['year'] = int(text)
            state.admin_step = 4
            kb = [
                [{"text": "پیوسته", "callback_data": "atype:پیوسته"}],
                [{"text": "ناپیوسته", "callback_data": "atype:ناپیوسته"}]
            ]
            self.api.send_message(chat_id, "نوع کارشناسی (type_coures) را انتخاب کنید:", self.api.create_inline_keyboard(kb))

        elif step == 5:
            state.temp_course_data['credits'] = text
            state.admin_step = 6
            self.api.send_message(chat_id, "پیش‌نیاز (اگر ندارد - بفرستید):")

        elif step == 6:
            state.temp_course_data['pre'] = text
            state.admin_step = 7
            self.api.send_message(chat_id, "هم‌نیاز (اگر ندارد - بفرستید):")

        elif step == 7:
            state.temp_course_data['co'] = text
            state.admin_step = 8
            self.api.send_message(chat_id, "شماره ردیف (Row Number) - عدد وارد کنید:")

        elif step == 8:
            row_text = self.normalize_digits(text)

            if not row_text.isdigit():
                self.api.send_message(chat_id, "عدد معتبر وارد کنید:")
                return

            d = state.temp_course_data
            ok = self.db.add_course(
                section=d['section'],
                row_number=int(row_text),
                course_title=d['title'],
                credits=d['credits'],
                prerequisite=d['pre'],
                corequisite=d['co'],
                year=d['year'],
                type_coures=d['type_coures']
            )

            if ok:
                self.api.send_message(chat_id, "✅ درس با موفقیت در دیتابیس ثبت شد.")
            else:
                self.api.send_message(chat_id, "❌ خطا در ثبت درس.")

            state.admin_step = 0
            state.temp_course_data = {}
            self.show_admin_menu(chat_id)

    def show_admin_report(self, chat_id):
        query = """
            SELECT 
                COALESCE(c.year, -1) AS year,
                u.student_type AS student_type,
                COALESCE(c.course_title, cr.course_name) AS course_title,
                COUNT(*) AS count
            FROM course_requests cr
            JOIN authorized_users u ON cr.user_id = u.id
            LEFT JOIN courses c ON cr.id_courses = c.id
            GROUP BY 
                COALESCE(c.year, -1),
                u.student_type,
                COALESCE(c.course_title, cr.course_name)
            ORDER BY year DESC, count DESC
        """

        results = self.db.execute_query(query)

        if not results:
            self.api.send_message(chat_id, "هنوز هیچ پیشنهادی ثبت نشده است.")
            return

        report = "📊 گزارش فراوانی پیشنهادات:\n\n"
        current_group = ""

        for r in results:
            year = r["year"]
            student_type = self.normalize_text(r["student_type"])
            course_title = r["course_title"]
            count = r["count"]

            year_label = year if year != -1 else "نامشخص"
            group = f"🗓 سال {year_label} - {student_type}"

            if group != current_group:
                report += f"\n🔹 {group}:\n"
                current_group = group

            report += f"  ▫️ {course_title}: {count} نفر\n"

        self.api.send_message(chat_id, report)
        self.show_admin_menu(chat_id)

    def show_participation_stats(self, chat_id):
        results = self.db.get_participation_stats()

        if not results:
            self.api.send_message(chat_id, "هنوز هیچ مشارکتی ثبت نشده است.")
            self.show_admin_menu(chat_id)
            return

        report = "👥 آمار مشارکت دانشجویان:\n"

        current_year = None
        for r in results:
            year = r["year_group"]
            stype = self.normalize_text(r["student_type"])
            count = r["participant_count"]

            # 🔥 اصلاح مهم: دانشجوی ناپیوسته → سال همیشه = 100
            if stype == "ناپیوسته":
                year = 100

            year_label = "نامشخص" if year == -1 else str(year)

            if year_label != current_year:
                report += f"\n📘 سال {year_label}\n"
                current_year = year_label

            report += f"▫️ {stype}: {count} نفر\n"

        self.api.send_message(chat_id, report)
        self.show_admin_menu(chat_id)

    def show_admin_courses_list(self, chat_id):
        all_courses = self.db.get_all_courses()
        text = self.format_admin_courses_grouped(all_courses)

        max_len = 3500
        if len(text) <= max_len:
            self.api.send_message(chat_id, text)
        else:
            parts = []
            current = ""

            for line in text.split("\n"):
                if len(current) + len(line) + 1 > max_len:
                    parts.append(current)
                    current = line
                else:
                    current += ("\n" if current else "") + line

            if current:
                parts.append(current)

            for part in parts:
                self.api.send_message(chat_id, part)

        self.show_admin_menu(chat_id)

    # ------------------- Student Course Selection ------------------- #
    def start_multi_course_selection(self, chat_id):
        state = self.user_states[chat_id]
        u = state.user_info

        # بررسی وجود نظرسنجی فعال (v2.4)
        survey = self.db.get_active_survey()
        if not survey:
            self.api.send_message(
                chat_id,
                "⚠️ در حال حاضر <b>نظرسنجی فعالی</b> وجود ندارد.\n"
                "لطفاً بعداً مراجعه کنید یا با آموزش دانشکده تماس بگیرید.",
                parse_mode=PARSE_MODE
            )
            return

        # جلوگیری از شرکت مجدد
        if self.db.has_user_submitted_courses(u["id"], survey["id"]):
            self.api.send_message(
                chat_id,
                "❌ شما قبلاً در فرایند پیشنهاد درس شرکت کرده‌اید."
            )
            return

        courses = self.get_available_courses_for_user(u)

        if not courses:
            self.api.send_message(
                chat_id,
                "🔍 درسی برای شما یافت نشد.\n"
                "لطفاً با آموزش دانشکده تماس بگیرید.",
                parse_mode=PARSE_MODE
            )
            return

        state.multi_select = True
        state.selected_courses = []
        self.render_course_list(chat_id, courses)

    def render_course_list(self, chat_id, courses):
        state = self.user_states[chat_id]
        kb = []

        sorted_courses = sorted(
            courses,
            key=lambda x: (
                x["section"] or "",
                x["row_number"] if x["row_number"] is not None else 9999,
                x["course_title"]
            )
        )

        # ===== [v3.6.5] تشخیص درس‌های مستثنا (کارآموزی/پروژه) =====
        EXEMPT_KEYWORDS = ("کارآموزی", "پروژه")
        non_exempt_selected = 0
        exempt_selected = 0
        for cid in state.selected_courses:
            title = ""
            for c in courses:
                if c["id"] == cid:
                    title = c.get("course_title") or ""
                    break
            if any(kw in title for kw in EXEMPT_KEYWORDS):
                exempt_selected += 1
            else:
                non_exempt_selected += 1

        for c in sorted_courses:
            mark = "✅ " if c['id'] in state.selected_courses else "☐ "

            course_code = c["id"]
            course_title = c["course_title"]

            exempt_label = ""
            if any(kw in (course_title or "") for kw in EXEMPT_KEYWORDS):
                exempt_label = " 🟢"

            kb.append([{
                "text": f"{mark}{course_title} ({course_code}){exempt_label}",
                "callback_data": f"toggle:{c['id']}"
            }])

        kb.append([{"text": "📥 ثبت نهایی انتخاب‌ها", "callback_data": "finalize"}])

        if state.select_message_id:
            self.api.delete_message(chat_id, state.select_message_id)

        sent = self.api.send_message(
            chat_id,
            (
                f"📚 <b>انتخاب دروس</b>\n"
                f"─────────────────\n"
                f"دروس مورد نظر خود را انتخاب کنید (حداکثر <b>{MAX_COURSES_PER_USER}</b> درس).\n"
                f"🟢 دروس کارآموزی و پروژه مشمول این محدودیت نیستند.\n\n"
                f"✅ انتخاب‌شده: <b>{non_exempt_selected}</b> از {MAX_COURSES_PER_USER}"
                + (f" + <b>{exempt_selected}</b> کارآموزی/پروژه" if exempt_selected > 0 else "")
                + f"\n\n"
                f"💡 برای رابط کاربری بهتر، از دکمه «🌐 ورود به مینی‌اپ» استفاده کنید."
            ),
            self.api.create_inline_keyboard(kb),
            parse_mode=PARSE_MODE
        )

        state.select_message_id = sent.get("message_id") if isinstance(sent, dict) else None

    # --------------------- Callback Handler --------------------- #
    def handle_callback(self, chat_id, data, msg_id):
        state = self.user_states.get(chat_id)
        if not state:
            # برای callback های منوی شروع، state جدید بساز
            if data in ("chan_miniapp", "chan_website", "chan_bot", "back_to_start"):
                self.user_states[chat_id] = UserState()
                state = self.user_states[chat_id]
            else:
                return

        data = self.normalize_text(data)

        # ===== منوی انتخاب کانال (v2.2.0) =====
        if data in ("chan_miniapp", "chan_website", "chan_bot"):
            self.handle_channel_choice(chat_id, data)
            return

        if data == "back_to_start":
            self.handle_start(chat_id)
            return

        if data == "reg_p":
            self.finalize_reg(chat_id, "پیوسته")

        elif data == "reg_np":
            self.finalize_reg(chat_id, "ناپیوسته")

        elif data == "admin_add_course":
            state.admin_step = 1
            self.api.send_message(chat_id, "لطفاً نام درس جدید را وارد کنید:")

        elif data.startswith("sect:"):
            state.temp_course_data['section'] = data.split(":", 1)[1]
            state.admin_step = 3
            self.api.send_message(chat_id, "سال درس را وارد کنید (1394 یا 1400):")

        elif data.startswith("atype:"):
            state.temp_course_data['type_coures'] = data.split(":", 1)[1]
            state.admin_step = 5
            self.api.send_message(chat_id, "تعداد واحد درس:")

        elif data == "admin_list_courses":
            self.show_admin_courses_list(chat_id)

        elif data == "admin_report":
            self.show_admin_report(chat_id)

        elif data == "admin_report_excel":
            self.api.send_message(chat_id, "⏳ در حال آماده‌سازی فایل اکسل و نمودار...")
            self.generate_excel_report(chat_id)

        elif data.startswith("toggle:"):
            cid_text = self.normalize_digits(data.split(":", 1)[1])

            if not cid_text.isdigit():
                self.api.send_message(chat_id, "شناسه درس نامعتبر است.")
                return

            cid = int(cid_text)

            if cid in state.selected_courses:
                state.selected_courses.remove(cid)
            else:
                # ===== [v3.6.5] محدودیت ۶ درس، با استثنای کارآموزی و پروژه =====
                EXEMPT_KEYWORDS = ("کارآموزی", "پروژه")
                # پیدا کردن عنوان درس برای بررسی استثنا
                courses_for_check = self.get_available_courses_for_user(state.user_info)
                course_title_to_check = ""
                for c in courses_for_check:
                    if c["id"] == cid:
                        course_title_to_check = c.get("course_title") or ""
                        break
                is_exempt = any(kw in course_title_to_check for kw in EXEMPT_KEYWORDS)
                if not is_exempt:
                    # شمارش دروس عادی انتخاب‌شده
                    non_exempt_count = 0
                    for scid in state.selected_courses:
                        title = ""
                        for c in courses_for_check:
                            if c["id"] == scid:
                                title = c.get("course_title") or ""
                                break
                        if not any(kw in title for kw in EXEMPT_KEYWORDS):
                            non_exempt_count += 1
                    if non_exempt_count >= MAX_COURSES_PER_USER:
                        self.api.send_message(
                            chat_id,
                            f"⚠️ حداکثر {MAX_COURSES_PER_USER} درس می‌توانید انتخاب کنید.\n"
                            f"💡 دروس کارآموزی و پروژه (🟢) در این محدودیت حساب نمی‌شوند."
                        )
                        return
                state.selected_courses.append(cid)

            courses = self.get_available_courses_for_user(state.user_info)
            self.render_course_list(chat_id, courses)



        elif data == "finalize":

            # جلوگیری از ثبت دوباره

            if self.db.has_user_submitted_courses(state.user_info["id"]):
                self.api.send_message(

                    chat_id,

                    "❌ شما قبلاً پیشنهاد درس ثبت کرده‌اید و امکان ثبت مجدد وجود ندارد."

                )

                return

            if not state.selected_courses:
                self.api.send_message(chat_id, "هیچ درسی انتخاب نشده است.")

                return

            success_count = 0

            for cid in state.selected_courses:

                ok = self.db.add_user_course(state.user_info["id"], cid)

                if ok:
                    success_count += 1

            self.api.send_message(
                chat_id,
                (
                    f"🎉 <b>ثبت با موفقیت انجام شد</b>\n"
                    f"─────────────────\n"
                    f"✅ <b>{success_count}</b> درس با موفقیت ثبت شد.\n\n"
                    f"🙏 از مشارکت شما سپاسگزاریم."
                ),
                parse_mode=PARSE_MODE
            )
            # پیام معرفی کانال
            self.api.send_message(
                chat_id,
                "🌙🤖 <b>کانال آموزشی هوش مصنوعی ماه‌افزار هوشمند</b>\n\n"
                "با هدف آموزش، تبیین و ساده‌سازی مفاهیم مرتبط با هوش مصنوعی ایجاد شده است؛ "
                "از مبانی و مفاهیم پایه تا کاربردهای عملی و روزمره هوش مصنوعی در کسب‌وکارها، "
                "سازمان‌ها و زندگی حرفه‌ای.\n\n"
                "اگر به یادگیری هوش مصنوعی علاقه‌مند هستید، همراه ما باشید.\n\n"
                "📢 لینک کانال: @MahAILearning",
                parse_mode=PARSE_MODE
            )
            state.selected_courses = []

            state.multi_select = False

            state.select_message_id = None

        elif data == "admin_courses_excel":
            self.api.send_message(chat_id, "⏳ در حال ساخت فایل اکسل لیست دروس...")
            self.generate_courses_excel(chat_id)

        elif data == "admin_participation":
            self.show_participation_stats(chat_id)

    # ---------------------- generate_courses_excel ---------------------- #
    def generate_courses_excel(self, chat_id):
        courses = self.db.get_all_courses()

        if not courses:
            self.api.send_message(chat_id, "هیچ درسی در دیتابیس ثبت نشده است.")
            self.show_admin_menu(chat_id)
            return

        df = pd.DataFrame(courses)

        # تبدیل مقادیر انگلیسی به فارسی / نرمال
        df["section"] = df["section"].apply(lambda x: SECTION_LABELS.get(x, x))
        df["course_title"] = df["course_title"].apply(lambda x: self.normalize_text(x))
        df["credits"] = df["credits"].apply(lambda x: self.normalize_text(x))
        df["prerequisite"] = df["prerequisite"].apply(lambda x: self.normalize_text(x))
        df["corequisite"] = df["corequisite"].apply(lambda x: self.normalize_text(x))

        # مرتب‌سازی نهایی
        df = df.sort_values(
            by=["year", "section", "row_number", "course_title"],
            ascending=[False, True, True, True]
        )

        file_path = "courses_list.xlsx"

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="لیست_دروس", index=False)

        # باز کردن برای اعمال فرمت
        wb = load_workbook(file_path)
        ws = wb.active

        header_fill = PatternFill(fill_type="solid", fgColor="1F4E78")
        header_font = Font(color="FFFFFF", bold=True)
        center_alignment = Alignment(horizontal="center", vertical="center")

        # فرمت هدر
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center_alignment

        # تنظیم عرض ستون‌ها
        from openpyxl.utils import get_column_letter
        for col_cells in ws.columns:
            max_length = 0
            col_letter = get_column_letter(col_cells[0].column)
            for cell in col_cells:
                value = str(cell.value) if cell.value else ""
                max_length = max(max_length, len(value))
            ws.column_dimensions[col_letter].width = min(max_length + 2, 40)

        wb.save(file_path)

        try:
            self.api.send_document(chat_id, file_path)
        except Exception as e:
            self.api.send_message(chat_id, f"❌ خطا در ارسال فایل: {e}")

        self.show_admin_menu(chat_id)

    # ---------------------- Main Loop ---------------------- #
    def run(self):
        print("🚀 Bot is running...")
        while True:
            try:
                updates = self.api.get_updates(offset=self.last_update_id + 1)

                if updates and "result" in updates:
                    for up in updates["result"]:
                        self.last_update_id = up["update_id"]

                        if "message" in up:
                            msg = up["message"]
                            chat_id = msg["chat"]["id"]

                            if "text" in msg:
                                text = self.normalize_text(msg["text"])

                                if text in ("/start", "/menu", "↩ بازگشت به منو اصلی", "/restart"):
                                    self.handle_start(chat_id)

                                elif chat_id in self.user_states:
                                    st = self.user_states[chat_id]

                                    if st.admin_step > 0:
                                        self.handle_admin_flow(chat_id, text)
                                    elif st.reg_step > 0:
                                        self.handle_registration(chat_id, text)

                            elif "contact" in msg:
                                self.handle_contact(msg)

                        elif "callback_query" in up:
                            cb = up["callback_query"]
                            self.handle_callback(
                                cb["message"]["chat"]["id"],
                                cb["data"],
                                cb["message"]["message_id"]
                            )

                time.sleep(0.5)

            except Exception as e:
                print(f"Error: {e}")
                time.sleep(2)


if __name__ == "__main__":
    import sys
    if sys.stdout and sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    # نمایش بنر نسخه هنگام استارت
    _print_version_banner()

    bot = CourseSurveyBot()
    bot.run()
