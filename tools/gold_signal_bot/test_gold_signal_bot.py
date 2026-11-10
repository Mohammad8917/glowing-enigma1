"""Offline unit tests; no network calls or credentials required."""
from datetime import datetime, timezone
import unittest

from gold_signal_bot import atr, detect_signal, ema, parse_bar_time, rsi


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


class SignalTests(unittest.TestCase):
    def test_insufficient_history_never_creates_signal(self):
        bars = [{"time": datetime.now(timezone.utc), "open": 1, "high": 2,
                 "low": 0.5, "close": 1} for _ in range(20)]
        self.assertIsNone(detect_signal(bars))


if __name__ == "__main__":
    unittest.main()
