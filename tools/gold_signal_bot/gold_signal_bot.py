"""Signal-only XAU/USD Telegram notifier. Never connects to a broker or places orders."""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import signal
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
LOG = logging.getLogger("gold_signal_bot")
TWELVE_DATA_URL = "https://api.twelvedata.com/time_series"
TELEGRAM_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEFRAMES = {
    "1min": ("1min", 60), "5min": ("5min", 300), "15min": ("15min", 900),
    "30min": ("30min", 1800), "1h": ("1h", 3600), "4h": ("4h", 14400),
    "1day": ("1day", 86400),
}


@dataclass(frozen=True)
class Config:
    api_key: str
    bot_token: str
    chat_id: str
    timeframe: str
    poll_seconds: int
    atr_multiplier: float
    tp1_r: float
    tp2_r: float
    state_file: Path
    http_timeout: int

    @classmethod
    def from_env(cls, *, require_market_data: bool = True) -> "Config":
        api_key = os.getenv("GOLD_TWELVE_DATA_API_KEY", "").strip()
        bot_token = os.getenv("GOLD_TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.getenv("GOLD_TELEGRAM_CHAT_ID", "").strip()
        if require_market_data and not api_key:
            raise ValueError("GOLD_TWELVE_DATA_API_KEY is not set in the project-root .env")
        if not bot_token:
            raise ValueError("GOLD_TELEGRAM_BOT_TOKEN is not set in the project-root .env")
        if not chat_id:
            raise ValueError("GOLD_TELEGRAM_CHAT_ID is not set in the project-root .env")
        timeframe = os.getenv("GOLD_TIMEFRAME", "15min").strip().lower()
        if timeframe not in TIMEFRAMES:
            raise ValueError(f"Unsupported GOLD_TIMEFRAME {timeframe!r}")
        interval_seconds = TIMEFRAMES[timeframe][1]
        poll_seconds = int(os.getenv("GOLD_POLL_SECONDS", str(max(20, min(60, interval_seconds // 10)))))
        if poll_seconds < 10:
            raise ValueError("GOLD_POLL_SECONDS must be at least 10")
        atr_multiplier = float(os.getenv("GOLD_RISK_ATR_MULTIPLIER", "1.5"))
        tp1_r = float(os.getenv("GOLD_TP1_R", "1.0"))
        tp2_r = float(os.getenv("GOLD_TP2_R", "2.0"))
        if not all(math.isfinite(v) and v > 0 for v in (atr_multiplier, tp1_r, tp2_r)):
            raise ValueError("ATR multiplier and TP R-multiples must be finite positive numbers")
        if tp2_r <= tp1_r:
            raise ValueError("GOLD_TP2_R must be greater than GOLD_TP1_R")
        state_file = Path(os.getenv(
            "GOLD_SIGNAL_STATE_FILE",
            str(Path.home() / ".quantdinger_gold_signal_state.json"),
        )).expanduser()
        return cls(api_key, bot_token, chat_id, timeframe, poll_seconds,
                   atr_multiplier, tp1_r, tp2_r, state_file,
                   max(5, int(os.getenv("GOLD_HTTP_TIMEOUT", "20"))))


def parse_bar_time(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("Candle is missing datetime")
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def fetch_closed_candles(config: Config, session: requests.Session | None = None) -> list[dict[str, Any]]:
    """Fetch spot XAU/USD from Twelve Data only; never substitute futures."""
    client = session or requests.Session()
    response = client.get(
        TWELVE_DATA_URL,
        params={"symbol": "XAU/USD", "interval": config.timeframe, "outputsize": 120,
                "timezone": "UTC", "format": "ISO", "apikey": config.api_key},
        timeout=config.http_timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Twelve Data returned an unexpected response")
    if payload.get("status") == "error" or payload.get("code"):
        raise RuntimeError(f"Twelve Data error: {payload.get('message') or payload.get('code')}")
    values = payload.get("values")
    if not isinstance(values, list) or not values:
        raise RuntimeError("Twelve Data returned no XAU/USD candles")
    now = datetime.now(timezone.utc)
    seconds = TIMEFRAMES[config.timeframe][1]
    candles = []
    for item in values:
        try:
            bar_time = parse_bar_time(item["datetime"])
            candle = {"time": bar_time, "open": float(item["open"]), "high": float(item["high"]),
                      "low": float(item["low"]), "close": float(item["close"])}
            if not all(math.isfinite(candle[k]) for k in ("open", "high", "low", "close")):
                continue
            if candle["low"] <= 0 or candle["high"] < candle["low"]:
                continue
            if bar_time + timedelta(seconds=seconds) <= now:
                candles.append(candle)
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
    candles.sort(key=lambda c: c["time"])
    result = list({c["time"]: c for c in candles}.values())
    if len(result) < 60:
        raise RuntimeError(f"Only {len(result)} fully closed XAU/USD candles received; at least 60 are required")
    return result


def ema(values: list[float], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("EMA period must be positive")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    previous = sum(values[:period]) / period
    out[period - 1] = previous
    alpha = 2.0 / (period + 1.0)
    for i in range(period, len(values)):
        previous = values[i] * alpha + previous * (1.0 - alpha)
        out[i] = previous
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def atr(candles: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(candles)
    if len(candles) <= period:
        return out
    ranges = []
    for i, c in enumerate(candles):
        prev_close = candles[i - 1]["close"] if i else c["close"]
        ranges.append(max(c["high"] - c["low"], abs(c["high"] - prev_close),
                          abs(c["low"] - prev_close)))
    current = sum(ranges[1:period + 1]) / period
    out[period] = current
    for i in range(period + 1, len(candles)):
        current = (current * (period - 1) + ranges[i]) / period
        out[i] = current
    return out


def detect_signal(candles: list[dict[str, Any]], *, atr_multiplier: float = 1.5,
                  tp1_r: float = 1.0, tp2_r: float = 2.0) -> dict[str, Any] | None:
    """EMA20/EMA50 trend + EMA20 price cross + RSI filter on completed candles."""
    if len(candles) < 60:
        return None
    closes = [float(c["close"]) for c in candles]
    fast, slow = ema(closes, 20), ema(closes, 50)
    momentum, volatility = rsi(closes, 14), atr(candles, 14)
    i, previous = len(candles) - 1, len(candles) - 2
    if any(x is None for x in (fast[i], fast[previous], slow[i], momentum[i], volatility[i])):
        return None
    close = closes[i]
    side = ""
    if closes[previous] <= fast[previous] and close > fast[i] and fast[i] > slow[i] and 50 <= momentum[i] <= 70:
        side = "BUY"
    elif closes[previous] >= fast[previous] and close < fast[i] and fast[i] < slow[i] and 30 <= momentum[i] <= 50:
        side = "SELL"
    if not side:
        return None
    risk = float(volatility[i]) * atr_multiplier
    if not math.isfinite(risk) or risk <= 0:
        return None
    if side == "BUY":
        stop, tp1, tp2 = close - risk, close + risk * tp1_r, close + risk * tp2_r
    else:
        stop, tp1, tp2 = close + risk, close - risk * tp1_r, close - risk * tp2_r
    return {"symbol": "XAU/USD", "side": side, "entry": close, "stop_loss": stop,
            "take_profit_1": tp1, "take_profit_2": tp2, "atr": float(volatility[i]),
            "rsi": float(momentum[i]), "ema_fast": float(fast[i]), "ema_slow": float(slow[i]),
            "candle_time": candles[i]["time"]}


def format_signal(data: dict[str, Any], timeframe: str) -> str:
    stamp = data["candle_time"].strftime("%Y-%m-%d %H:%M UTC")
    return (
        "🟡 <b>GOLD / XAUUSD — SIGNAL</b>\n"
        f"<b>جهت:</b> {data['side']}\n"
        f"<b>تایم‌فریم:</b> {timeframe}\n"
        f"<b>ورود مرجع:</b> {data['entry']:.2f}\n"
        f"<b>حد ضرر:</b> {data['stop_loss']:.2f}\n"
        f"<b>حد سود ۱:</b> {data['take_profit_1']:.2f}\n"
        f"<b>حد سود ۲:</b> {data['take_profit_2']:.2f}\n"
        f"<b>RSI(14):</b> {data['rsi']:.1f} | <b>ATR(14):</b> {data['atr']:.2f}\n"
        f"<b>کندل تأییدشده:</b> {stamp}\n\n"
        "روش: EMA20/EMA50 + شکست EMA20 + فیلتر RSI؛ SL بر پایه ATR.\n"
        "این فقط هشدار تحلیلی است؛ هیچ سفارشی اجرا نشده است. قیمت زنده و اسپرد کارگزار خود را بررسی کنید."
    )


def send_telegram(config: Config, message: str, session: requests.Session | None = None) -> None:
    client = session or requests.Session()
    response = client.post(TELEGRAM_URL.format(token=config.bot_token),
                           data={"chat_id": config.chat_id, "text": message,
                                 "parse_mode": "HTML", "disable_web_page_preview": "true"},
                           timeout=config.http_timeout)
    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError("Telegram rejected the message; check bot token, chat ID, and bot permissions")


def read_state(path: Path) -> str:
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("last_signal_candle") or "")
    except FileNotFoundError:
        return ""
    except (OSError, ValueError, AttributeError):
        LOG.warning("State file is unreadable; duplicate protection starts fresh")
        return ""


def write_state(path: Path, candle_time: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps({"last_signal_candle": candle_time.isoformat()}), encoding="utf-8")
    temp.replace(path)


def run_once(config: Config, session: requests.Session | None = None) -> str:
    candles = fetch_closed_candles(config, session=session)
    data = detect_signal(candles, atr_multiplier=config.atr_multiplier,
                         tp1_r=config.tp1_r, tp2_r=config.tp2_r)
    if not data:
        LOG.info("No new confirmed GOLD signal on %s", config.timeframe)
        return "no_signal"
    key = data["candle_time"].isoformat()
    if key == read_state(config.state_file):
        LOG.info("Signal for this candle was already delivered")
        return "duplicate"
    send_telegram(config, format_signal(data, config.timeframe), session=session)
    write_state(config.state_file, data["candle_time"])
    LOG.info("Delivered %s XAU/USD signal for candle %s", data["side"], key)
    return "sent"


def main() -> int:
    parser = argparse.ArgumentParser(description="Signal-only XAUUSD notifier; no broker or order execution.")
    parser.add_argument("--once", action="store_true", help="check once and exit")
    parser.add_argument("--test-telegram", action="store_true", help="send a Telegram connectivity test")
    args = parser.parse_args()
    logging.basicConfig(level=os.getenv("GOLD_LOG_LEVEL", "INFO").upper(),
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        config = Config.from_env(require_market_data=not args.test_telegram)
    except (ValueError, TypeError) as exc:
        LOG.error("%s", exc)
        return 2
    if args.test_telegram:
        try:
            send_telegram(config, "✅ QuantDinger GOLD notifier: اتصال تلگرام موفق است.\nاین پیام آزمایشی است؛ معامله‌ای اجرا نمی‌شود.")
            LOG.info("Telegram test message delivered")
            return 0
        except Exception as exc:
            LOG.error("Telegram test failed: %s", exc)
            return 1
    if args.once:
        try:
            run_once(config)
            return 0
        except Exception as exc:
            LOG.error("GOLD check failed: %s", exc)
            return 1
    stopping = False
    def stop_handler(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True
        LOG.info("Stop requested")
    signal.signal(signal.SIGINT, stop_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop_handler)
    LOG.info("GOLD notifier started: XAU/USD, timeframe=%s, poll=%ss; signal-only mode",
             config.timeframe, config.poll_seconds)
    while not stopping:
        try:
            run_once(config)
        except Exception as exc:
            LOG.error("GOLD check failed; will retry: %s", exc)
        for _ in range(config.poll_seconds):
            if stopping:
                break
            time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
