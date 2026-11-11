"""Architecture boundary and backwards-compatibility contract tests."""
import unittest

import gold_signal_bot
from gold_signal import indicators, market_data, service, state, strategy, telegram


class ArchitectureContractTests(unittest.TestCase):
    def test_legacy_facade_reexports_modular_public_api(self):
        self.assertIs(gold_signal_bot.ema, indicators.ema)
        self.assertIs(gold_signal_bot.atr, indicators.atr)
        self.assertIs(gold_signal_bot.detect_signal, strategy.detect_signal)
        self.assertIs(gold_signal_bot.fetch_closed_candles, market_data.fetch_closed_candles)
        self.assertIs(gold_signal_bot.run_once, service.run_once)
        self.assertIs(gold_signal_bot.process_lock, state.process_lock)
        self.assertIs(gold_signal_bot.send_telegram, telegram.send_telegram)

    def test_market_and_strategy_layers_do_not_depend_on_cli(self):
        self.assertNotIn("gold_signal.cli", market_data.__dict__)
        self.assertNotIn("gold_signal.cli", strategy.__dict__)

    def test_service_is_the_orchestration_boundary(self):
        self.assertIs(gold_signal_bot.run_once, service.run_once)
        self.assertTrue(callable(service.run_once))


if __name__ == "__main__":
    unittest.main()
