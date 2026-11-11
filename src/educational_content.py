# src/educational_content.py

def get_style():
    return """
    <style>
        body { font-family: 'Tahoma', dir='rtl'; background-color: #f4f7f6; color: #333; padding: 20px; direction: rtl; text-align: right; }
        .container { max-width: 800px; margin: 0 auto; background: #fff; padding: 20px; border-radius: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); }
        h1, h2 { color: #2c3e50; border-bottom: 2px solid #eee; padding-bottom: 10px; }
        .score-card { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; text-align: center; }
        .q-box { border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 8px; background: #fafafa; }
        .q-box.correct { border-right: 5px solid #2ecc71; }
        .q-box.wrong { border-right: 5px solid #e74c3c; }
        .option { padding: 5px 10px; margin: 5px 0; border-radius: 4px; background: #fff; border: 1px solid #eee; }
        .option.user-selected { background-color: #fce4ec; border-color: #e74c3c; color: #c0392b; font-weight: bold;}
        .option.real-correct { background-color: #e8f5e9; border-color: #2ecc71; color: #27ae60; font-weight: bold;}
        .option.user-correct { background-color: #e8f5e9; border-color: #2ecc71; color: #27ae60; font-weight: bold;}
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 10px; text-align: center; }
        th { background-color: #f2f2f2; }
    </style>
    """


def get_answer_sheet_html(user_name, score, total_q, answers_detail, quiz_questions):
    """تولید فایل HTML پاسخنامه تشریحی"""
    html = f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>پاسخنامه آزمون - {user_name}</title>
        {get_style()}
    </head>
    <body>
        <div class="container">
            <div class="score-card">
                <h1>کارنامه عملکرد: {user_name}</h1>
                <h2>نمره نهایی: {score}%</h2>
            </div>
            <h3>📋 جزئیات سوالات و پاسخ‌ها</h3>
    """

    for idx, q_data in enumerate(quiz_questions):
        q_id = q_data['id']
        # پیدا کردن پاسخ کاربر برای این سوال
        user_ans_obj = next((a for a in answers_detail if a['question_id'] == q_id), None)

        user_idx = user_ans_obj['user_answer'] if user_ans_obj else -1
        correct_idx = q_data['correct']
        is_correct = (user_idx == correct_idx)

        status_class = "correct" if is_correct else "wrong"
        status_icon = "✅" if is_correct else "❌"

        html += f"""
        <div class="q-box {status_class}">
            <p><strong>سوال {idx + 1}:</strong> {q_data['question']} <span style="float:left">{status_icon}</span></p>
            <div class="options">
        """

        for opt_idx, option_text in enumerate(q_data['options']):
            css_class = "option"
            if opt_idx == correct_idx:
                css_class += " real-correct"
            if opt_idx == user_idx:
                if is_correct:
                    css_class += " user-correct"  # قبلاً سبز شده
                else:
                    css_class += " user-selected"  # قرمز شود

            html += f"<div class='{css_class}'>{opt_idx + 1}. {option_text}</div>"

        html += "</div></div>"

    html += """
            <p style="text-align:center; color:#888; font-size:12px;">تولید شده توسط بات کانون ارزیابی</p>
        </div>
    </body>
    </html>
    """
    return html


def get_progress_chart_html(user_name, history_data):
    """
    تولید نمودار پیشرفت با استفاده از Chart.js
    history_data = [{'date': '1403/10/01', 'score': 45}, ...]
    """
    dates = [d['date'] for d in history_data]
    scores = [d['score'] for d in history_data]

    html = f"""
    <!DOCTYPE html>
    <html lang="fa" dir="rtl">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>روند پیشرفت - {user_name}</title>
        {get_style()}
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <div class="container">
            <div class="score-card" style="background: linear-gradient(135deg, #FF9966 0%, #FF5E62 100%);">
                <h1>📈 گزارش روند پیشرفت</h1>
                <h2>{user_name}</h2>
            </div>

            <div style="position: relative; height:400px; width:100%">
                <canvas id="progressChart"></canvas>
            </div>

            <h3>تاریخچه نمرات:</h3>
            <table>
                <tr><th>تاریخ آزمون</th><th>نمره کسب شده</th></tr>
                {''.join([f"<tr><td>{d['date']}</td><td>{d['score']}%</td></tr>" for d in history_data])}
            </table>
        </div>

        <script>
            const ctx = document.getElementById('progressChart').getContext('2d');
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {dates},
                    datasets: [{{
                        label: 'نمره آزمون (درصد)',
                        data: {scores},
                        borderColor: 'rgba(75, 192, 192, 1)',
                        backgroundColor: 'rgba(75, 192, 192, 0.2)',
                        borderWidth: 3,
                        pointBackgroundColor: '#fff',
                        pointRadius: 5,
                        fill: true,
                        tension: 0.3
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {{
                        y: {{
                            beginAtZero: true,
                            max: 100
                        }}
                    }},
                    plugins: {{
                        legend: {{
                            labels: {{ font: {{ family: 'Tahoma' }} }}
                        }}
                    }}
                }}
            }});
        </script>
    </body>
    </html>
    """
    return html
"""
محتوای آموزشی برای بخش‌های مختلف آزمون
"""
from questions import SECTION_1, SECTION_2, SECTION_3, SECTION_4, SECTION_5

# محتوای آموزشی به فرمت HTML — به‌روز بر اساس «خلاصه جزوه‌های ارزیابی.pdf»
EDUCATIONAL_MATERIALS = {
    SECTION_1: """
        <h3>📚 اهداف، ارکان و مبانی شایستگی</h3>
        <ul>
            <li><strong>تعریف کانون ارزیابی:</strong> داوطلبان در تمرین‌ها و آزمون‌ها شرکت می‌کنند و توسط ارزیابان آموزش‌دیده از نظر شایستگی مشاهده و ارزیابی می‌شوند؛ خروجی، گزارش بازخورد است.</li>
            <li><strong>ارکان موفقیت:</strong> ارزیابان توانمند، مدل شایستگی‌ها، ابزارها و تمرین‌های مناسب، ارزیابی‌شوندگان.</li>
            <li><strong>شایستگی چیست؟</strong> مجموعه دانش، نگرش، مهارت، تجربه، توانایی و ویژگی‌های فردی که به عملکرد موفق منجر می‌شود: مرتبط با شغل، قابل مشاهده، قابل تعریف رفتاری، قابل ارزیابی و آموزش.</li>
            <li><strong>تفاوت با عملکرد و صفت شخصیتی:</strong> شایستگی صلاحیت لازم است نه نتیجه؛ شایستگی قابل آموزش است و صفت ذاتی و پایدار است.</li>
        </ul>

        <h4>🧊 مدل گوه/کوه یخ شایستگی</h4>
        <table>
            <tr><th>بخش</th><th>درصد</th><th>اجزا</th></tr>
            <tr><td>بالای آب</td><td>۱۰٪</td><td>دانش (Knowledge)، مهارت (Skill)</td></tr>
            <tr><td>زیر آب</td><td>۹۰٪</td><td>نگرش، خودپنداره، ویژگی‌های شخصیتی، انگیزش</td></tr>
        </table>

        <h4>🛠️ مهارت‌های سخت و نرم</h4>
        <ul>
            <li><strong>سخت:</strong> قابل اندازه‌گیری و آموزش‌پذیر (زبان، برنامه‌نویسی).</li>
            <li><strong>نرم:</strong> مرتبط با روابط انسانی (ارتباط، رهبری، کار تیمی).</li>
        </ul>

        <h4>🧭 مدل شایستگی و استخراج</h4>
        <ul>
            <li>انواع مدل: دولت/حوزه/صنعت، سازمان، سطح مدیریتی، شغل خاص.</li>
            <li>شیوه‌های استخراج: تحلیل شغل، تحلیل رفتار کارکنان خوب، الگوگیری از مشابه‌ها، پیش‌بینی نیازهای آینده.</li>
            <li>گام‌های طراحی: مرور ادبیات، مصاحبه با افراد موفق، فهرست اولیه، اعتباریابی، ارائه مدل.</li>
            <li>تعداد معمول شایستگی برای یک شغل: ۸ تا ۱۲ مورد.</li>
        </ul>

        <h4>📊 سطح‌بندی شایستگی‌ها (نمونه: تفکر تحلیلی و حل مسئله)</h4>
        <ol>
            <li>تجزیه مسائل ساده</li>
            <li>شناسایی الگوها</li>
            <li>تحلیل موقعیت‌های پیچیده</li>
            <li>ادغام اطلاعات از منابع متنوع</li>
            <li>پیش‌بینی پیامدها و ارائه سیاست‌ها</li>
        </ol>

        <div class="tip-box">
            <strong>استاندارد ارزیابی:</strong> هر شایستگی باید حداقل با دو ابزار و دو ارزیاب سنجیده شود (مصاحبه، ایفای نقش، تمرین نوشتاری، ارائه، موردکاوی، بازی مدیریتی).
        </div>
    """,

    SECTION_2: """
        <h3>🧭 مدل شایستگی ارزیابان (سه لایه) و تقلیل‌گرایی</h3>

        <h4>لایه اول: شایستگی‌های درونی (Being)</h4>
        <ul>
            <li>خودآگاهی: شناخت ارزش‌ها، هیجانات، سوگیری‌ها.</li>
            <li>مهار هیجان: مدیریت هیجان در موقعیت‌های استرس‌زا.</li>
            <li>انصاف و بی‌طرفی: قضاوت بدون سوگیری شخصی/فرهنگی.</li>
            <li>مسئولیت اخلاقی: حفظ حریم و کرامت ارزیابی‌شونده.</li>
            <li>خودانضباطی/خودرهبری: پرهیز از قضاوت عجولانه.</li>
        </ul>

        <h4>لایه دوم: شایستگی‌های ادراکی/شناختی (Knowing)</h4>
        <ul>
            <li>دانش ارزیابی: فرآیند، ابزار، مدل‌ها، خطاهای رایج.</li>
            <li>درک خطاهای شناختی: اثر هاله‌ای، شباهت‌پنداری، تأیید پیش‌فرض.</li>
            <li>تفکر انتقادی و تحلیلی: تمایز داده از تفسیر.</li>
            <li>درک بافت: شناخت شرایط فرهنگی و سازمانی.</li>
            <li>قضاوت حرفه‌ای: نظر متوازن و مستند بر شواهد عینی.</li>
        </ul>

        <h4>لایه سوم: شایستگی‌های رفتاری/بین‌فردی (Doing)</h4>
        <ul>
            <li>شنیدن فعال: بدون پیش‌داوری، با توجه به زبان بدن.</li>
            <li>گفت‌وگوی غیرقضاوتی: احترام‌آمیز و بدون برچسب‌زنی.</li>
            <li>بازخورد اثربخش: صادقانه، دقیق، محترمانه و سازنده.</li>
            <li>مدیریت جلسه ارزیابی: هدایت فضا، زمان و پویایی.</li>
            <li>ثبت و مستندسازی حرفه‌ای: جداسازی تفسیر از داده و رعایت محرمانگی.</li>
        </ul>

        <div class="highlight-box">
            <strong>نکات کلیدی مدل:</strong> بُعد Being محور است؛ خودشناسی و بی‌طرفی در مرکز؛ آموزش و بازآموزی مستمر لازم است؛ سنجش با ابزارهای چندلایه (خودارزیابی، همتایان، مشاهده).
        </div>

        <h4>تقلیل‌گرایی و محدودیت مدل‌ها</h4>
        <ul>
            <li>هر مدل شایستگی ساده‌سازی واقعیت پیچیده انسانی است و وابسته به بستر.</li>
            <li>دلایل نقص: تنوع تجربه، پویایی شایستگی‌ها، دشواری شایستگی‌های ضمنی، تعامل پیچیده شایستگی‌ها.</li>
            <li>پیامدها: شفافیت درباره محدودیت، به‌روزرسانی و گسترش، آموزش کاربران، استفاده از مدل‌های مکمل.</li>
        </ul>
    """,

    SECTION_3: """
        <h3>🔍 فرآیند ارزیابی رفتار (ORCE) و مهارت مشاهده</h3>

        <h4>نقش و وظایف ارزیاب</h4>
        <ol>
            <li>مشاهده رفتار در تمرین‌ها و تست‌ها</li>
            <li>ثبت رفتارها در فرم‌های استاندارد</li>
            <li>طبقه‌بندی رفتارها در ابعاد رفتاری/شایستگی‌ها</li>
            <li>رتبه‌بندی شایستگی‌ها بر اساس شواهد</li>
            <li>توافق با سایر ارزیابان درباره نتایج</li>
        </ol>

        <h4>مدل ORCE (چارچوب استاندارد)</h4>
        <table>
            <tr><th>حرف</th><th>مفهوم</th><th>شرح</th></tr>
            <tr><td>O</td><td>مشاهده</td><td>فعال و هدفمند، بدون قضاوت اولیه</td></tr>
            <tr><td>R</td><td>ثبت</td><td>مستندسازی منظم، عینی، همزمان با مشاهده</td></tr>
            <tr><td>C</td><td>طبقه‌بندی</td><td>انتساب رفتارها به شایستگی‌ها، پس از تمرین</td></tr>
            <tr><td>E</td><td>ارزیابی</td><td>نمره‌دهی بر اساس شواهد طبقه‌بندی‌شده (BARS)</td></tr>
        </table>
        <div class="tip-box">
            <strong>اهداف ORCE:</strong> کاهش خطای انسانی، خروج از شهود، افزایش مقایسه‌پذیری بین ارزیابان، ارتقای اعتبار و روایی.
        </div>

        <h4>ثبت و BARS</h4>
        <ul>
            <li>ثبت: عینی، بدون تفسیر؛ کلمات خبری؛ پرهیز از واژه‌های قضاوتی؛ فوری و خلاصه.</li>
            <li>BARS: مقیاس رفتاری ۱ تا ۵ (ضعیف تا عالی) با توصیف‌های رفتاری برای استانداردسازی امتیازدهی.</li>
        </ul>

        <h4>اصول تقویت مهارت مشاهده</h4>
        <ol>
            <li>موضوع را بشناسید (آگاهی از موقعیت)</li>
            <li>در زمان حال باشید (عدم سفر ذهنی)</li>
            <li>موقعیت‌های جدید را امتحان کنید</li>
            <li>تمرکز و حذف حواس‌پرتی</li>
            <li>تقویت ذهن با تمرین‌های منطقی/بازی‌های فکری</li>
            <li>تقویت حافظه (خواب، تغذیه، تمرین ذهنی)</li>
            <li>ثبت مداوم جزئیات</li>
            <li>تقویت تفکر نقادانه</li>
        </ol>

        <h4>شایستگی‌های رایج مورد سنجش</h4>
        <ul>
            <li>تصمیم‌گیری (ریسک‌پذیری سنجیده، ارزیابی راهکارها)</li>
            <li>مهارت‌های ارتباطی (کلامی، غیرکلامی، نوشتاری)</li>
            <li>کار تیمی (مصالحه، احترام، همکاری)</li>
            <li>ویژگی‌های شخصیتی و اخلاقی (اعتمادبه‌نفس، مسئولیت‌پذیری)</li>
            <li>مدیریت افراد (انگیزش، مشارکت‌پذیری)</li>
            <li>مدیریت عملکرد (برنامه‌ریزی، نتیجه‌گرایی، نظارت)</li>
            <li>رهبری (نفوذ، الگو بودن، توانمندسازی)</li>
            <li>شناخت صنعت و بازار (هوشیاری محیطی، تحلیل روندها)</li>
        </ul>
    """,

    SECTION_4: """
        <h3>📝 گزارش و بازخورد + خطاهای ارزیابی</h3>

        <h4>گزارش و بازخورد</h4>
        <ul>
            <li><strong>هدف:</strong> پیوند مشاهده و تصمیم؛ برای سازمان ابزار تصمیم و برای فرد آینه رفتار.</li>
            <li><strong>مراحل:</strong> مشاهده → طبقه‌بندی → تطبیق با BARS → امتیازدهی → تنظیم گزارش.</li>
            <li><strong>لحن حرفه‌ای:</strong> مثبت و یادگیرنده‌محور؛ پرهیز از برچسب‌زنی (مثل «عصبی»، «ضعیف»).</li>
            <li><strong>ساختار گزارش:</strong> نقاط قوت، نقاط قابل بهبود، جمع‌بندی توسعه‌محور.</li>
            <li><strong>مثال مناسب:</strong> «در تمرین تصمیم‌گیری تمایل به واگذاری تحلیل داشت؛ نیازمند تقویت اعتمادبه‌نفس در ابهام.»</li>
        </ul>

        <h4>خطاهای ارزیابی (نمونه‌های کلیدی)</h4>
        <div class="section-card">
            <h5>ادراکی (Perceptual)</h5>
            <ul>
                <li>اثر هاله‌ای / شاخ</li>
                <li>شباهت به خود / تضاد با خود</li>
                <li>اثر نخستین / تازگی</li>
                <li>مقایسه‌ای، جذابیت ظاهری</li>
            </ul>
        </div>
        <div class="section-card">
            <h5>قضاوتی</h5>
            <ul>
                <li>میانه‌روی</li>
                <li>آسان‌گیری / سخت‌گیری</li>
                <li>ثبات (تعمیم یک نمره به همه تمرین‌ها)</li>
                <li>برچسب‌زنی</li>
            </ul>
        </div>
        <div class="section-card">
            <h5>شناختی/منطقی</h5>
            <ul>
                <li>تأیید پیش‌فرض</li>
                <li>برجسته‌سازی</li>
                <li>اعتماد به حافظه</li>
                <li>علت‌تراشی پسینی</li>
            </ul>
        </div>
        <div class="section-card">
            <h5>رفتاری و سیستمی</h5>
            <ul>
                <li>تأثیر هیجانی و هم‌گروهی</li>
                <li>نقش دوگانه ارزیاب</li>
                <li>خستگی یا فشار زمانی، مکان/زمان اجرا</li>
            </ul>
        </div>

        <div class="tip-box">
            <strong>پیشگیری:</strong> خودآگاهی، آموزش مستمر، تبعیت از ORCE، بازبینی همتا.
        </div>
    """,

    SECTION_5: """
        <h3>⚖️ شیوه‌نامه مدیران حرفه‌ای، ابزارها و آزمون‌های روان‌سنجی</h3>

        <h4>گروه‌های مدیریتی و شایستگی‌ها</h4>
        <div class="section-card">
            <h5>مدیران حرفه‌ای غیرعملیاتی (ستادی)</h5>
            <ul>
                <li>تفکر راهبردی و آینده‌نگری ⭐</li>
                <li>تفکر انتقادی</li>
                <li>قدرت مذاکره و متقاعدسازی</li>
                <li>کارگروهی و تیم‌سازی</li>
                <li>حل مسئله</li>
                <li>ارتباط مؤثر</li>
                <li>نظارت و کنترل</li>
            </ul>
        </div>
        <div class="section-card">
            <h5>مدیران حرفه‌ای عملیاتی</h5>
            <ul>
                <li>کارگروهی و تیم‌سازی</li>
                <li>حل مسئله</li>
                <li>ارتباط مؤثر</li>
                <li>نظارت و کنترل</li>
                <li>مدیریت شرایط اضطراری ⭐</li>
            </ul>
        </div>

        <h4>ابزارهای ارزیابی (حداقل دو ابزار برای هر شایستگی)</h4>
        <ul>
            <li>مصاحبه شایستگی‌محور</li>
            <li>ایفای نقش</li>
            <li>بحث گروهی</li>
            <li>کارتابل (In-Basket)</li>
            <li>آزمون روان‌شناختی</li>
            <li>بازی مدیریتی</li>
        </ul>

        <h4>معافیت از ارائه گواهی شایستگی (تبصره ۱ ماده ۲)</h4>
        <ol>
            <li>سابقه تصدی پست مدیریتی همان سطح</li>
            <li>انتصاب به پست هم‌سطح</li>
            <li>انتصاب به پست پایین‌تر</li>
            <li>پست‌های موضوع تبصره ۳ ماده ۲</li>
        </ol>

        <h4>آزمون‌های شخصیت‌شناسی و کاربردها</h4>
        <ul>
            <li><strong>استخدام:</strong> MMPI-2 (مشاغل حساس، سلامت روان)، Big Five/NEO، DISC</li>
            <li><strong>توسعه و آموزش:</strong> MBTI (۱۶ تیپ)، EQ بار-آن</li>
            <li><strong>تناسب شغل-شاغل:</strong> لنگرگاه‌های شغلی (۸ ارزش/گرایش)، هالند (۶ تیپ: واقع‌گرا، جستجوگر، هنری، اجتماعی، متهور، قراردادی)</li>
            <li><strong>آیزنک (EPI/EPQ):</strong> برون‌گرایی/درون‌گرایی، روان‌آزردگی، روان‌پریشی، صداقت</li>
            <li><strong>نکته:</strong> آزمون‌ها ابزار کمکی‌اند و جایگزین مصاحبه و مشاهده نیستند؛ تفسیر توسط متخصص.</li>
        </ul>
    """
}