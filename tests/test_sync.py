import unittest
from datetime import datetime

from fab_exchange_rate_sync.providers import parse_exchangerate_host_payload, parse_open_exchange_rates_payload
from fab_exchange_rate_sync.sync import (
	build_pair_rates_from_quotes,
	collect_requested_currencies,
	compute_effective_interval_minutes,
)


class Row:
	def __init__(self, from_currency, to_currency):
		self.from_currency = from_currency
		self.to_currency = to_currency


class TestSync(unittest.TestCase):
	def test_compute_effective_interval_respects_provider_minimum(self):
		self.assertEqual(compute_effective_interval_minutes("Hourly", 0, 60), 60)
		self.assertEqual(compute_effective_interval_minutes("Custom", 15, 60), 60)
		self.assertEqual(compute_effective_interval_minutes("Custom", 180, 60), 180)
		self.assertEqual(compute_effective_interval_minutes("Daily", 0, 10), 1440)

	def test_manual_sync_can_run_when_automatic_sync_is_disabled(self):
		from unittest.mock import patch

		from fab_exchange_rate_sync.sync import run_exchange_rate_sync

		settings = type("Settings", (), {"enabled": 0})()

		with patch("fab_exchange_rate_sync.sync.frappe.get_single", return_value=settings), patch(
			"fab_exchange_rate_sync.sync.get_enabled_currency_pairs", return_value=[]
		), patch("fab_exchange_rate_sync.sync.now_datetime", return_value=datetime(2026, 4, 25, 12, 0, 0)):
			result = run_exchange_rate_sync(
				ignore_schedule=True,
				raise_on_error=True,
				ignore_enabled=True,
			)

		self.assertEqual(result["status"], "skipped")
		self.assertEqual(result["reason"], "no_pairs")

	def test_collect_requested_currencies_deduplicates_codes(self):
		pairs = [Row("EUR", "USD"), Row("USD", "GBP"), Row("EUR", "GBP")]
		self.assertEqual(collect_requested_currencies(pairs), ["EUR", "GBP", "USD"])

	def test_build_pair_rates_from_quotes_supports_cross_rates(self):
		pairs = [Row("EUR", "GBP"), Row("USD", "EUR")]
		pair_rates = build_pair_rates_from_quotes(
			"USD",
			{"USD": 1.0, "EUR": 0.92, "GBP": 0.79},
			pairs,
		)

		self.assertAlmostEqual(pair_rates[("EUR", "GBP")], 0.79 / 0.92, places=9)
		self.assertAlmostEqual(pair_rates[("USD", "EUR")], 0.92, places=9)

	def test_parse_open_exchange_rates_payload_keeps_source_currency(self):
		snapshot = parse_open_exchange_rates_payload(
			{
				"timestamp": 1714060800,
				"base": "USD",
				"rates": {"EUR": 0.92, "GBP": 0.79},
			}
		)

		self.assertEqual(snapshot.source_currency, "USD")
		self.assertEqual(snapshot.quotes["USD"], 1.0)
		self.assertEqual(snapshot.quotes["EUR"], 0.92)
		self.assertIsNone(snapshot.source_timestamp.tzinfo)

	def test_parse_exchangerate_host_payload_strips_source_prefix(self):
		snapshot = parse_exchangerate_host_payload(
			{
				"success": True,
				"timestamp": 1714060800,
				"source": "USD",
				"quotes": {"USDEUR": 0.92, "USDGBP": 0.79},
			}
		)

		self.assertEqual(snapshot.source_currency, "USD")
		self.assertEqual(snapshot.quotes["USD"], 1.0)
		self.assertEqual(snapshot.quotes["GBP"], 0.79)
		self.assertIsNone(snapshot.source_timestamp.tzinfo)
