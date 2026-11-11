"""Offline tests; no network calls, broker connections, or credentials required."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from gold_signal_bot import (
    _is_expected_gold_pause, atr, detect_signal, ema, parse_bar_time, process_lock, read_state,
    rsi, validate_candles, write_state,
)


class IndicatorTests(unittest.TestCase):
    def test_ema_seed_and_length(self):
        result = ema([1.0, 2.0, 3.0, 4.0, 5.0], 3)
        self.assertEqual(len(result), 5)
        self.assertIsNone(result[0])
        self.assertAlmostEqual(result[2], 2.0)
        self.assertGreater(result[3], result[2])

    def test_rsi_is_bounded(self):
        result = rsi([float(i) for i in range(30)], 14)
        self.assertEqual(result[-1], 100.0)

    def test_atr_is_positive(self):
        bars = [{"open": 100+i, "high": 102+i, "low": 99+i, "close": 101+i}
                for i in range(25)]
        self.assertGreater(atr(bars, 14)[-1], 0)

    def test_naive_time_is_treated_as_utc(self):
        self.assertEqual(parse_bar_time("2026-11-10 10:00:00").tzinfo, timezone.utc)

    def test_insufficient_history_never_creates_signal(self):
        bars = [{"time": datetime.now(timezone.utc), "open": 1, "high": 2,
                 "low": 0.5, "close": 1} for _ in range(20)]
        self.assertIsNone(detect_signal(bars))


class CandleValidationTests(unittest.TestCase):
    interval = 900

    def make_bars(self, count=65, *, now=None):
        now = now or datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
        last_open = now - timedelta(seconds=self.interval + 5)
        first_open = last_open - timedelta(seconds=self.interval * (count - 1))
        bars = []
        for i in range(count):
            stamp = first_open + timedelta(seconds=self.interval * i)
            price = 2600.0 + i
            bars.append({"time": stamp, "open": price, "high": price + 2,
                         "low": price - 2, "close": price + 1})
        return bars, now

    def test_sorts_and_collapses_identical_duplicates(self):
        bars, now = self.make_bars()
        shuffled = list(reversed(bars)) + [bars[10].copy()]
        result = validate_candles(shuffled, timeframe_seconds=self.interval, now=now)
        self.assertEqual(len(result), len(bars))
        self.assertEqual(result, bars)

    def test_rejects_conflicting_duplicate_timestamp(self):
        bars, now = self.make_bars()
        duplicate = bars[10].copy()
        duplicate["close"] += 5
        duplicate["high"] += 5
        with self.assertRaisesRegex(RuntimeError, "conflicting duplicate"):
            validate_candles(bars + [duplicate], timeframe_seconds=self.interval, now=now)

    def test_rejects_invalid_ohlc_relationship(self):
        bars, now = self.make_bars()
        bars[5]["high"] = bars[5]["open"] - 1
        with self.assertRaisesRegex(RuntimeError, "OHLC"):
            validate_candles(bars, timeframe_seconds=self.interval, now=now)

    def test_rejects_non_finite_price(self):
        bars, now = self.make_bars()
        bars[5]["close"] = float("nan")
        with self.assertRaisesRegex(RuntimeError, "non-finite"):
            validate_candles(bars, timeframe_seconds=self.interval, now=now)

    def test_rejects_unclosed_candle(self):
        bars, now = self.make_bars()
        bars[-1]["time"] = now - timedelta(seconds=100)
        with self.assertRaisesRegex(RuntimeError, "unclosed or future"):
            validate_candles(bars, timeframe_seconds=self.interval, now=now)

    def test_rejects_stale_data_during_open_session(self):
        bars, _ = self.make_bars()
        now = bars[-1]["time"] + timedelta(seconds=self.interval * 8)
        with self.assertRaisesRegex(RuntimeError, "stale"):
            validate_candles(bars, timeframe_seconds=self.interval, now=now)

    def test_rejects_internal_gap(self):
        bars, now = self.make_bars()
        del bars[20]
        with self.assertRaisesRegex(RuntimeError, "Missing XAU/USD candles"):
            validate_candles(bars, timeframe_seconds=self.interval, now=now)

    def test_rejects_too_little_valid_history(self):
        bars, now = self.make_bars(count=20)
        with self.assertRaisesRegex(RuntimeError, "at least 60"):
            validate_candles(bars, timeframe_seconds=self.interval, now=now)

    def test_recognizes_daily_maintenance_window_only_when_bounded(self):
        start = datetime(2026, 11, 10, 20, 45, tzinfo=timezone.utc)
        end = datetime(2026, 11, 10, 22, 0, tzinfo=timezone.utc)
        extended = datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)
        self.assertTrue(_is_expected_gold_pause(start, end))
        self.assertFalse(_is_expected_gold_pause(start, extended))

    def test_weekend_pause_ends_after_sunday_open(self):
        friday = datetime(2026, 11, 13, 21, 0, tzinfo=timezone.utc)
        sunday_before_open = datetime(2026, 11, 15, 21, 30, tzinfo=timezone.utc)
        sunday_after_open = datetime(2026, 11, 15, 23, 0, tzinfo=timezone.utc)
        self.assertTrue(_is_expected_gold_pause(friday, sunday_before_open))
        self.assertFalse(_is_expected_gold_pause(friday, sunday_after_open))


class StateAndLockTests(unittest.TestCase):
    def test_state_round_trip(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            stamp = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
            self.assertEqual(read_state(path), "")
            write_state(path, stamp)
            self.assertEqual(read_state(path), stamp.isoformat())

    def test_process_lock_rejects_second_instance(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "state.json"
            with process_lock(path):
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    with process_lock(path):
                        pass


if __name__ == "__main__":
    unittest.main()
