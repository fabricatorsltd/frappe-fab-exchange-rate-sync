from __future__ import annotations

import frappe
from frappe import _
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def after_install():
	if frappe.db.exists("DocType", "Exchange Rate Provider"):
		ensure_custom_fields()
		ensure_seed_records()


def after_migrate():
	if frappe.db.exists("DocType", "Exchange Rate Provider"):
		ensure_custom_fields()
		ensure_seed_records()


def ensure_custom_fields():
	if not frappe.db.exists("DocType", "Exchange Rate Provider"):
		return
	create_custom_fields(get_custom_fields(), update=True)


def ensure_seed_records():
	ensure_seed_documents("Exchange Rate Provider", "provider_name", get_default_providers())


def ensure_seed_documents(doctype: str, lookup_field: str, documents: list[dict[str, object]]):
	if not frappe.db.exists("DocType", doctype):
		return

	for payload in documents:
		docname = frappe.db.get_value(doctype, {lookup_field: payload[lookup_field]})
		if not docname:
			frappe.get_doc({"doctype": doctype, **payload}).insert(ignore_permissions=True)
			continue

		doc = frappe.get_doc(doctype, docname)
		changed = False
		for fieldname, value in payload.items():
			if fieldname in {"doctype", "name"}:
				continue
			if doc.get(fieldname) in (None, ""):
				doc.set(fieldname, value)
				changed = True

		if changed:
			doc.save(ignore_permissions=True)


def get_custom_fields() -> dict[str, list[dict[str, object]]]:
	return {
		"Currency Exchange": [
			{
				"fieldname": "fab_ers_section",
				"label": _("Exchange Rate Sync"),
				"fieldtype": "Section Break",
				"insert_after": "for_selling",
			},
			{
				"fieldname": "fab_ers_provider",
				"label": _("Synced Provider"),
				"fieldtype": "Link",
				"options": "Exchange Rate Provider",
				"insert_after": "fab_ers_section",
				"read_only": 1,
			},
			{
				"fieldname": "fab_ers_source_currency",
				"label": _("Source Currency"),
				"fieldtype": "Link",
				"options": "Currency",
				"insert_after": "fab_ers_provider",
				"read_only": 1,
			},
			{
				"fieldname": "fab_ers_source_timestamp",
				"label": _("Source Timestamp"),
				"fieldtype": "Datetime",
				"insert_after": "fab_ers_source_currency",
				"read_only": 1,
			},
			{
				"fieldname": "fab_ers_column_break",
				"fieldtype": "Column Break",
				"insert_after": "fab_ers_source_timestamp",
			},
			{
				"fieldname": "fab_ers_fetched_at",
				"label": _("Fetched At"),
				"fieldtype": "Datetime",
				"insert_after": "fab_ers_column_break",
				"read_only": 1,
			},
			{
				"fieldname": "fab_ers_locked",
				"label": _("Lock From Sync"),
				"description": _("Prevent automated sync runs from updating this exchange rate."),
				"fieldtype": "Check",
				"insert_after": "fab_ers_fetched_at",
			},
		]
	}


def get_default_providers() -> list[dict[str, object]]:
	return [
		{
			"provider_name": "Open Exchange Rates",
			"adapter_key": "open_exchange_rates",
			"enabled": 1,
			"endpoint_url": "https://openexchangerates.org/api",
			"plan_name": "Free / Developer",
			"minimum_refresh_interval_minutes": 60,
			"timeout_seconds": 15,
			"default_source_currency": "USD",
			"supports_historical": 1,
			"use_source_currency_param": 0,
			"use_currencies_param": 1,
		},
		{
			"provider_name": "ExchangeRate.host",
			"adapter_key": "exchangerate_host",
			"enabled": 1,
			"endpoint_url": "https://api.exchangerate.host",
			"plan_name": "Free / Basic",
			"minimum_refresh_interval_minutes": 60,
			"timeout_seconds": 15,
			"default_source_currency": "USD",
			"supports_historical": 1,
			"use_source_currency_param": 0,
			"use_currencies_param": 1,
		},
	]
