from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import frappe
from frappe import _
from frappe.exceptions import ValidationError
from frappe.utils import cint, cstr, flt, get_datetime, getdate, now_datetime, nowdate

from fab_exchange_rate_sync.providers import fetch_provider_rates


SETTINGS_DOCTYPE = "Exchange Rate Sync Settings"
PROVIDER_DOCTYPE = "Exchange Rate Provider"
CURRENCY_EXCHANGE_DOCTYPE = "Currency Exchange"
SYNC_PROVIDER_FIELD = "fab_ers_provider"
SYNC_SOURCE_CURRENCY_FIELD = "fab_ers_source_currency"
SYNC_SOURCE_TIMESTAMP_FIELD = "fab_ers_source_timestamp"
SYNC_FETCHED_AT_FIELD = "fab_ers_fetched_at"
SYNC_LOCKED_FIELD = "fab_ers_locked"


@frappe.whitelist()
def sync_now():
	return run_exchange_rate_sync(ignore_schedule=True, raise_on_error=True, ignore_enabled=True)


def run_scheduled_sync():
	run_exchange_rate_sync(ignore_schedule=False, raise_on_error=False, ignore_enabled=False)


def run_exchange_rate_sync(
	*, ignore_schedule: bool, raise_on_error: bool, ignore_enabled: bool = False
) -> dict[str, Any]:
	settings = frappe.get_single(SETTINGS_DOCTYPE)
	attempted_at = now_datetime()

	if not ignore_enabled and not cint(settings.enabled):
		return {"status": "disabled", "message": _("Exchange rate sync is disabled.")}

	pairs = get_enabled_currency_pairs(settings)
	if not pairs:
		return {"status": "skipped", "reason": "no_pairs", "message": _("No currency pairs are enabled.")}

	providers = get_provider_chain(settings)
	primary_provider = providers[0]
	effective_interval_minutes = compute_effective_interval_minutes(
		cstr(settings.sync_frequency or "Hourly"),
		cint(settings.custom_interval_minutes or 0),
		cint(getattr(primary_provider, "minimum_refresh_interval_minutes", 0)),
	)

	if not ignore_schedule and not is_sync_due(settings.last_attempted_sync_at, effective_interval_minutes, attempted_at):
		return {
			"status": "skipped",
			"reason": "not_due",
			"effective_interval_minutes": effective_interval_minutes,
		}

	settings.last_attempted_sync_at = attempted_at
	settings.last_error = None
	settings.save(ignore_permissions=True)

	sync_dates = build_sync_dates(getdate(nowdate()), cint(settings.historical_days or 0))
	provider_errors: list[str] = []
	for provider_index, provider in enumerate(providers):
		try:
			summary = sync_with_provider(
				settings=settings,
				provider=provider,
				pairs=pairs,
				sync_dates=sync_dates,
				attempted_at=attempted_at,
			)
		except ValidationError as exc:
			provider_errors.append(f"{provider.name}: {exc}")
			continue

		settings.last_successful_sync_at = attempted_at
		settings.last_error = None
		settings.save(ignore_permissions=True)
		summary["status"] = "success"
		summary["effective_interval_minutes"] = effective_interval_minutes
		summary["fallback_used"] = provider_index > 0
		return summary

	last_error = " | ".join(provider_errors) or _("Exchange rate sync failed without a provider error message.")
	settings.last_error = last_error
	settings.save(ignore_permissions=True)
	frappe.log_error(title=_("Exchange rate sync failed"), message=last_error)
	if raise_on_error:
		frappe.throw(last_error)
	return {
		"status": "failed",
		"errors": provider_errors,
		"effective_interval_minutes": effective_interval_minutes,
	}


def sync_with_provider(*, settings, provider, pairs, sync_dates, attempted_at: datetime) -> dict[str, Any]:
	summary = {
		"provider": provider.name,
		"dates": [sync_date.isoformat() for sync_date in sync_dates],
		"inserted": 0,
		"updated": 0,
		"skipped_manual": 0,
		"skipped_locked": 0,
		"skipped_synced": 0,
	}
	requested_currencies = collect_requested_currencies(pairs)

	for sync_date in sync_dates:
		snapshot = fetch_provider_rates(provider, requested_currencies, rate_date=sync_date)
		pair_rates = build_pair_rates_from_quotes(snapshot.source_currency, snapshot.quotes, pairs)
		for row in pairs:
			outcome = upsert_currency_exchange(
				row=row,
				rate=pair_rates[(row.from_currency, row.to_currency)],
				sync_date=sync_date,
				provider=provider,
				source_currency=snapshot.source_currency,
				source_timestamp=snapshot.source_timestamp,
				fetched_at=attempted_at,
				settings=settings,
			)
			summary[outcome] += 1

	return summary


def get_provider_chain(settings) -> list[Any]:
	primary_provider_name = cstr(settings.primary_provider or "").strip()
	if not primary_provider_name:
		raise ValidationError(_("Set a Primary Provider before enabling exchange rate sync."))

	primary_provider = get_provider_doc(primary_provider_name)
	providers = [primary_provider]

	fallback_provider_name = cstr(settings.fallback_provider or "").strip()
	if fallback_provider_name and fallback_provider_name != primary_provider_name:
		providers.append(get_provider_doc(fallback_provider_name))

	return providers


def get_provider_doc(provider_name: str):
	if not frappe.db.exists(PROVIDER_DOCTYPE, provider_name):
		raise ValidationError(_("Exchange Rate Provider {0} does not exist.").format(provider_name))

	provider = frappe.get_doc(PROVIDER_DOCTYPE, provider_name)
	if not cint(provider.enabled):
		raise ValidationError(_("Exchange Rate Provider {0} is disabled.").format(provider.name))

	return provider


def get_enabled_currency_pairs(settings) -> list[Any]:
	pairs = [row for row in (settings.currency_pairs or []) if cint(row.enabled)]
	return pairs


def compute_effective_interval_minutes(
	sync_frequency: str,
	custom_interval_minutes: int,
	provider_minimum_refresh_interval_minutes: int,
) -> int:
	desired_interval_minutes = 60
	if sync_frequency == "Daily":
		desired_interval_minutes = 60 * 24
	elif sync_frequency == "Custom":
		desired_interval_minutes = custom_interval_minutes if custom_interval_minutes > 0 else 60

	provider_minimum = provider_minimum_refresh_interval_minutes if provider_minimum_refresh_interval_minutes > 0 else 0
	return max(desired_interval_minutes, provider_minimum)


def is_sync_due(last_attempted_at, effective_interval_minutes: int, reference_time: datetime) -> bool:
	if not last_attempted_at:
		return True
	return reference_time - get_datetime(last_attempted_at) >= timedelta(minutes=effective_interval_minutes)


def build_sync_dates(reference_date, historical_days: int) -> list[Any]:
	historical_days = historical_days if historical_days >= 0 else 0
	return [reference_date - timedelta(days=offset) for offset in range(historical_days, -1, -1)]


def collect_requested_currencies(pairs) -> list[str]:
	currencies = set()
	for row in pairs:
		currencies.add(cstr(row.from_currency).upper())
		currencies.add(cstr(row.to_currency).upper())
	return sorted(currency for currency in currencies if currency)


def build_pair_rates_from_quotes(source_currency: str, quotes: dict[str, float], pairs) -> dict[tuple[str, str], float]:
	normalized_quotes = {cstr(source_currency).upper(): 1.0}
	for currency, rate in quotes.items():
		normalized_quotes[cstr(currency).upper()] = round(flt(rate), 9)

	pair_rates: dict[tuple[str, str], float] = {}
	for row in pairs:
		from_currency = cstr(row.from_currency).upper()
		to_currency = cstr(row.to_currency).upper()
		from_rate = normalized_quotes.get(from_currency)
		to_rate = normalized_quotes.get(to_currency)
		if not from_rate:
			raise ValidationError(_("Provider data does not include source currency {0}.").format(from_currency))
		if to_rate is None:
			raise ValidationError(_("Provider data does not include target currency {0}.").format(to_currency))
		pair_rates[(from_currency, to_currency)] = round(flt(to_rate / from_rate), 9)

	return pair_rates


def upsert_currency_exchange(
	*,
	row,
	rate: float,
	sync_date,
	provider,
	source_currency: str,
	source_timestamp,
	fetched_at: datetime,
	settings,
) -> str:
	filters = {
		"date": sync_date,
		"from_currency": row.from_currency,
		"to_currency": row.to_currency,
		"for_buying": cint(row.for_buying),
		"for_selling": cint(row.for_selling),
	}
	existing = frappe.db.get_value(
		CURRENCY_EXCHANGE_DOCTYPE,
		filters,
		["name", SYNC_PROVIDER_FIELD, SYNC_LOCKED_FIELD],
		as_dict=True,
	)
	if existing:
		if cint(existing.get(SYNC_LOCKED_FIELD)):
			return "skipped_locked"

		existing_provider = cstr(existing.get(SYNC_PROVIDER_FIELD) or "").strip()
		if not existing_provider and not cint(settings.overwrite_manual_rates):
			return "skipped_manual"
		if existing_provider and not cint(settings.update_existing_synced_rates):
			return "skipped_synced"

		doc = frappe.get_doc(CURRENCY_EXCHANGE_DOCTYPE, existing["name"])
		doc.exchange_rate = rate
		doc.fab_ers_provider = provider.name
		doc.fab_ers_source_currency = source_currency
		doc.fab_ers_source_timestamp = source_timestamp
		doc.fab_ers_fetched_at = fetched_at
		doc.save(ignore_permissions=True)
		return "updated"

	doc = frappe.get_doc(
		{
			"doctype": CURRENCY_EXCHANGE_DOCTYPE,
			"date": sync_date,
			"from_currency": row.from_currency,
			"to_currency": row.to_currency,
			"exchange_rate": rate,
			"for_buying": cint(row.for_buying),
			"for_selling": cint(row.for_selling),
			"fab_ers_provider": provider.name,
			"fab_ers_source_currency": source_currency,
			"fab_ers_source_timestamp": source_timestamp,
			"fab_ers_fetched_at": fetched_at,
		}
	)
	doc.insert(ignore_permissions=True)
	return "inserted"
