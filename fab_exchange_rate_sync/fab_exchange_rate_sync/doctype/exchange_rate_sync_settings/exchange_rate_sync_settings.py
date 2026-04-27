from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint, cstr


class ExchangeRateSyncSettings(Document):
	def validate(self):
		if cint(self.enabled) and not cstr(self.primary_provider or "").strip():
			frappe.throw(frappe._("Set a Primary Provider before enabling exchange rate sync."))

		if cstr(self.sync_frequency or "Hourly") == "Custom" and cint(self.custom_interval_minutes or 0) <= 0:
			frappe.throw(frappe._("Custom Interval Minutes must be greater than 0."))

		if cstr(self.fallback_provider or "").strip() and self.fallback_provider == self.primary_provider:
			frappe.throw(frappe._("Fallback Provider must be different from Primary Provider."))

		seen_pairs: set[tuple[str, str, int, int]] = set()
		enabled_pairs = 0
		for row in self.currency_pairs or []:
			if row.from_currency == row.to_currency:
				frappe.throw(frappe._("From Currency and To Currency cannot be the same on row {0}.").format(row.idx))

			key = (
				cstr(row.from_currency or ""),
				cstr(row.to_currency or ""),
				cint(row.for_buying),
				cint(row.for_selling),
			)
			if key in seen_pairs:
				frappe.throw(
					frappe._("Duplicate currency pair {0} -> {1} detected.").format(row.from_currency, row.to_currency)
				)
			seen_pairs.add(key)

			if cint(row.enabled):
				enabled_pairs += 1
				if not cint(row.for_buying) and not cint(row.for_selling):
					frappe.throw(
						frappe._("Currency pair {0} -> {1} must apply to buying or selling.").format(
							row.from_currency,
							row.to_currency,
						)
					)

		if cint(self.enabled) and enabled_pairs == 0:
			frappe.throw(frappe._("Enable at least one currency pair before enabling exchange rate sync."))
