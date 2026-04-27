import json
import unittest
from pathlib import Path

from fab_exchange_rate_sync import install


APP_ROOT = Path(__file__).resolve().parents[1]
MODULE_ROOT = APP_ROOT / "fab_exchange_rate_sync" / "fab_exchange_rate_sync"


class TestInstall(unittest.TestCase):
	def test_currency_exchange_custom_fields_cover_sync_provenance(self):
		custom_fields = install.get_custom_fields()

		self.assertEqual(set(custom_fields), {"Currency Exchange"})
		self.assertGreaterEqual(
			{field["fieldname"] for field in custom_fields["Currency Exchange"]},
			{
				"fab_ers_section",
				"fab_ers_provider",
				"fab_ers_source_currency",
				"fab_ers_source_timestamp",
				"fab_ers_fetched_at",
				"fab_ers_locked",
			},
		)

	def test_default_providers_include_expected_adapters(self):
		providers = {provider["provider_name"]: provider for provider in install.get_default_providers()}

		self.assertIn("Open Exchange Rates", providers)
		self.assertIn("ExchangeRate.host", providers)
		self.assertEqual(providers["Open Exchange Rates"]["adapter_key"], "open_exchange_rates")
		self.assertEqual(providers["ExchangeRate.host"]["adapter_key"], "exchangerate_host")
		self.assertEqual(providers["Open Exchange Rates"]["default_source_currency"], "USD")

	def test_provider_doctype_contains_provider_fields(self):
		doctype_path = (
			MODULE_ROOT
			/ "doctype"
			/ "exchange_rate_provider"
			/ "exchange_rate_provider.json"
		)
		doctype = json.loads(doctype_path.read_text())
		fields = {field["fieldname"]: field for field in doctype["fields"]}

		self.assertEqual(fields["adapter_key"]["fieldtype"], "Select")
		self.assertEqual(fields["adapter_key"]["read_only"], 1)
		self.assertEqual(fields["api_key"]["fieldtype"], "Password")
		self.assertEqual(fields["endpoint_url"]["read_only"], 1)
		self.assertEqual(fields["minimum_refresh_interval_minutes"]["fieldtype"], "Int")
		self.assertEqual(fields["default_source_currency"]["options"], "Currency")

	def test_settings_doctype_contains_pairs_and_status(self):
		doctype_path = (
			MODULE_ROOT
			/ "doctype"
			/ "exchange_rate_sync_settings"
			/ "exchange_rate_sync_settings.json"
		)
		doctype = json.loads(doctype_path.read_text())
		fields = {field["fieldname"]: field for field in doctype["fields"]}

		self.assertEqual(fields["currency_pairs"]["fieldtype"], "Table")
		self.assertEqual(fields["currency_pairs"]["options"], "Exchange Rate Pair")
		self.assertEqual(fields["status_section"]["fieldtype"], "Section Break")
		self.assertEqual(fields["status_section"]["collapsible"], 1)
		self.assertEqual(fields["last_error"]["read_only"], 1)
