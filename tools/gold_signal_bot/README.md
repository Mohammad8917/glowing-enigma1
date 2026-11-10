# GOLD / XAUUSD Telegram Signal Notifier

این ابزار مستقل برای ارسال هشدارهای تحلیلی طلا به تلگرام است. فقط نماد **XAU/USD** را از Twelve Data می‌خواند و **هیچ اتصال صرافی/کارگزاری، API معاملاتی، ثبت سفارش یا اجرای معامله‌ای ندارد**.

## منطق نسخه اولیه
- داده: کندل XAU/USD از Twelve Data؛ فقط کندل‌های کاملاً بسته‌شده.
- روند: EMA 20 و EMA 50.
- تأیید مومنتوم: RSI 14.
- ماشه: عبور قیمت بسته‌شدن از EMA20 در جهت روند، همراه با فیلتر RSI.
- حد ضرر: 1.5 برابر ATR(14) به‌صورت پیش‌فرض.
- TP1: برابر 1R و TP2: برابر 2R.
- ضدتکرار: زمان کندل پس از ارسال موفق ذخیره می‌شود.
- اگر داده کافی/معتبر نباشد، سیگنال ساخته نمی‌شود.

این فقط یک استراتژی نمونه قابل‌آزمایش است، نه تضمین دقت یا سودآوری. پیش از استفاده واقعی، بک‌تست، آزمون خارج از نمونه و forward-test لازم است. قیمت XAU/USD ارائه‌دهنده ممکن است با قیمت کارگزار و اسپرد آن متفاوت باشد.

## پیش‌نیازها
- Windows 11 و Python 3.11+
- کلید API از Twelve Data برای XAU/USD
- ربات تلگرام و Chat ID مقصد
- اینترنت پایدار

این نسخه عمداً به Yahoo Finance و نماد آتی GC=F برنمی‌گردد؛ اگر داده spot از Twelve Data در دسترس نباشد، خطا می‌دهد تا قیمت آتی به‌جای XAU/USD ارسال نشود.

## نصب در Windows 11 / PowerShell
از ریشه مخزن اجرا کن:

    py -3 -m venv .venv-gold
    .\.venv-gold\Scripts\Activate.ps1
    python -m pip install --upgrade pip
    pip install -r tools\gold_signal_bot\requirements.txt

اگر PowerShell فعال‌سازی را مسدود کرد:

    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
    .\.venv-gold\Scripts\Activate.ps1

## تنظیمات محرمانه
فایل .env اصلی مخزن را باز کن و این متغیرها را اضافه کن. فایل .env در Git نادیده گرفته می‌شود؛ کلیدها را در GitHub یا تلگرام منتشر نکن.

    GOLD_TWELVE_DATA_API_KEY=کلید_Twelve_Data
    GOLD_TELEGRAM_BOT_TOKEN=توکن_ربات_تلگرام
    GOLD_TELEGRAM_CHAT_ID=آیدی_چت_یا_کانال
    GOLD_TIMEFRAME=15min
    GOLD_POLL_SECONDS=45
    GOLD_RISK_ATR_MULTIPLIER=1.5
    GOLD_TP1_R=1.0
    GOLD_TP2_R=2.0

ربات را به کانال اضافه کن و اجازه ارسال پیام بده. برای گروه/کانال خصوصی، Chat ID صحیح لازم است.

## تست و اجرا
از ریشه مخزن:

    python tools\gold_signal_bot\gold_signal_bot.py --test-telegram
    python tools\gold_signal_bot\gold_signal_bot.py --once
    python tools\gold_signal_bot\gold_signal_bot.py

- دستور اول فقط اتصال تلگرام را آزمایش می‌کند.
- دستور دوم یک بار داده را می‌خواند و در صورت وجود سیگنال تأییدشده ارسال می‌کند.
- دستور سوم پایش پیوسته را اجرا می‌کند.
- برای توقف، Ctrl+C بزن.

## متغیرهای اختیاری
| متغیر | پیش‌فرض | توضیح |
|---|---:|---|
| GOLD_TIMEFRAME | 15min | یکی از 1min, 5min, 15min, 30min, 1h, 4h, 1day |
| GOLD_POLL_SECONDS | 45 | فاصله بررسی؛ حداقل 10 ثانیه |
| GOLD_RISK_ATR_MULTIPLIER | 1.5 | ضریب ATR برای فاصله SL |
| GOLD_TP1_R | 1.0 | فاصله TP1 بر حسب R |
| GOLD_TP2_R | 2.0 | فاصله TP2 بر حسب R و باید از TP1 بیشتر باشد |
| GOLD_SIGNAL_STATE_FILE | فایل در پوشه home کاربر | محل ذخیره ضدتکرار |
| GOLD_HTTP_TIMEOUT | 20 | مهلت درخواست HTTP بر حسب ثانیه |

## چک‌لیست پیش از استفاده
1. ابتدا تست تلگرام را اجرا و دریافت پیام را دستی تأیید کن.
2. با --once مطمئن شو API داده کافی و کندل‌های بسته‌شده می‌دهد.
3. تا قبل از ارزیابی بک‌تست و forward-test، سیگنال‌ها را فقط روی کاغذ ثبت کن.
4. Entry/SL/TP بر اساس قیمت بسته‌شدن کندل‌اند؛ قیمت اجرا، اسپرد، لغزش و کمیسیون کارگزار را لحاظ نمی‌کنند.
5. اگر API key یا مجوز نماد/تایم‌فریم کافی نباشد، ابزار سیگنال تولید نمی‌کند و خطا می‌دهد.
6. برنامه را روی ویندوز روشن و متصل به اینترنت نگه دار؛ برای اجرای دائمی، بعداً به سرویس/سرور منتقلش کن.

هیچ بخشی از این ابزار نباید به API سفارش‌گذاری یا کلید معاملاتی متصل شود.
