from __future__ import annotations

import frappe
from frappe.model.document import Document
from frappe.utils import cint


class ExchangeRateProvider(Document):
	def validate(self):
		if cint(self.minimum_refresh_interval_minutes or 0) <= 0:
			frappe.throw(frappe._("Minimum Refresh Interval Minutes must be greater than 0."))
		if cint(self.timeout_seconds or 0) <= 0:
			frappe.throw(frappe._("Timeout Seconds must be greater than 0."))
