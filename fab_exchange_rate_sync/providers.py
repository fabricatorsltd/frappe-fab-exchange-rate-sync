from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests

import frappe
from frappe import _
from frappe.exceptions import ValidationError
from frappe.utils import cint, cstr, flt, getdate, nowdate


DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_SOURCE_CURRENCY = "USD"
OPEN_EXCHANGE_RATES_ENDPOINT = "https://openexchangerates.org/api"
EXCHANGERATE_HOST_ENDPOINT = "https://api.exchangerate.host"


@dataclass(slots=True)
class ProviderRateSnapshot:
	source_currency: str
	quotes: dict[str, float]
	source_timestamp: datetime | None
	raw_payload: dict[str, Any]


def fetch_provider_rates(provider, currencies: list[str], rate_date=None) -> ProviderRateSnapshot:
	adapter_key = cstr(getattr(provider, "adapter_key", "") or "").strip()
	if adapter_key == "open_exchange_rates":
		return fetch_open_exchange_rates(provider, currencies, rate_date=rate_date)
	if adapter_key == "exchangerate_host":
		return fetch_exchangerate_host(provider, currencies, rate_date=rate_date)

	raise ValidationError(
		_("Exchange rate provider {0} uses unsupported adapter {1}.").format(
			getattr(provider, "name", _("Unknown provider")),
			adapter_key or _("unknown"),
		)
	)


def fetch_open_exchange_rates(provider, currencies: list[str], *, rate_date=None) -> ProviderRateSnapshot:
	source_currency = get_provider_source_currency(provider)
	api_key = get_provider_api_key(provider)
	if not api_key:
		raise ValidationError(_("Set an API key on Exchange Rate Provider {0}.").format(provider.name))

	endpoint_root = cstr(getattr(provider, "endpoint_url", "") or "").strip() or OPEN_EXCHANGE_RATES_ENDPOINT
	request_date = getdate(rate_date or nowdate())
	path = f"/historical/{request_date.isoformat()}.json" if request_date != getdate(nowdate()) else "/latest.json"
	params = {"app_id": api_key}

	symbols = normalize_requested_currencies(currencies, source_currency=source_currency)
	if symbols:
		params["symbols"] = ",".join(currency for currency in symbols if currency != source_currency)
	if cint(getattr(provider, "use_source_currency_param", 0)):
		params["base"] = source_currency

	payload = request_json(
		f"{endpoint_root.rstrip('/')}{path}",
		params=params,
		timeout_seconds=get_provider_timeout_seconds(provider),
	)
	return parse_open_exchange_rates_payload(payload, fallback_source_currency=source_currency)


def fetch_exchangerate_host(provider, currencies: list[str], *, rate_date=None) -> ProviderRateSnapshot:
	source_currency = get_provider_source_currency(provider)
	api_key = get_provider_api_key(provider)
	if not api_key:
		raise ValidationError(_("Set an API key on Exchange Rate Provider {0}.").format(provider.name))

	endpoint_root = cstr(getattr(provider, "endpoint_url", "") or "").strip() or EXCHANGERATE_HOST_ENDPOINT
	request_date = getdate(rate_date or nowdate())
	path = "/historical" if request_date != getdate(nowdate()) else "/live"
	params = {"access_key": api_key}
	if request_date != getdate(nowdate()):
		params["date"] = request_date.isoformat()

	if cint(getattr(provider, "use_source_currency_param", 0)):
		params["source"] = source_currency

	if cint(getattr(provider, "use_currencies_param", 1)):
		symbols = normalize_requested_currencies(currencies, source_currency=source_currency)
		params["currencies"] = ",".join(currency for currency in symbols if currency != source_currency)

	payload = request_json(
		f"{endpoint_root.rstrip('/')}{path}",
		params=params,
		timeout_seconds=get_provider_timeout_seconds(provider),
	)
	return parse_exchangerate_host_payload(payload, fallback_source_currency=source_currency)


def parse_open_exchange_rates_payload(
	payload: dict[str, Any],
	*,
	fallback_source_currency: str = DEFAULT_SOURCE_CURRENCY,
) -> ProviderRateSnapshot:
	if payload.get("error"):
		raise ValidationError(
			_("Open Exchange Rates returned an error: {0}").format(
				cstr(payload.get("message") or _("Unknown provider error"))
			)
		)

	rates = payload.get("rates")
	if not isinstance(rates, dict) or not rates:
		raise ValidationError(_("Open Exchange Rates returned no rates."))

	source_currency = cstr(payload.get("base") or fallback_source_currency or DEFAULT_SOURCE_CURRENCY).upper()
	quotes = {source_currency: 1.0}
	for currency, rate in rates.items():
		quotes[cstr(currency).upper()] = round(flt(rate), 9)

	return ProviderRateSnapshot(
		source_currency=source_currency,
		quotes=quotes,
		source_timestamp=parse_provider_timestamp(payload.get("timestamp")),
		raw_payload=payload,
	)


def parse_exchangerate_host_payload(
	payload: dict[str, Any],
	*,
	fallback_source_currency: str = DEFAULT_SOURCE_CURRENCY,
) -> ProviderRateSnapshot:
	if payload.get("success") is False:
		error = payload.get("error") or {}
		raise ValidationError(
			_("ExchangeRate.host returned an error: {0}").format(
				cstr(error.get("info") or _("Unknown provider error"))
			)
		)

	source_currency = cstr(payload.get("source") or fallback_source_currency or DEFAULT_SOURCE_CURRENCY).upper()
	quotes_payload = payload.get("quotes")
	if not isinstance(quotes_payload, dict) or not quotes_payload:
		raise ValidationError(_("ExchangeRate.host returned no quotes."))

	quotes = {source_currency: 1.0}
	for pair_key, rate in quotes_payload.items():
		pair_key = cstr(pair_key).upper()
		currency = pair_key.removeprefix(source_currency)
		if len(currency) != 3:
			currency = pair_key[-3:]
		quotes[currency] = round(flt(rate), 9)

	return ProviderRateSnapshot(
		source_currency=source_currency,
		quotes=quotes,
		source_timestamp=parse_provider_timestamp(payload.get("timestamp")),
		raw_payload=payload,
	)


def request_json(url: str, *, params: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
	try:
		response = requests.get(
			url,
			params=params,
			timeout=timeout_seconds,
			headers={"User-Agent": "fab_exchange_rate_sync/0.0.1"},
		)
	except requests.RequestException as exc:
		raise ValidationError(_("Exchange rate request to {0} failed: {1}").format(url, cstr(exc))) from exc

	try:
		response.raise_for_status()
	except requests.HTTPError as exc:
		raise ValidationError(
			_("Exchange rate request to {0} failed with status {1}: {2}").format(
				url,
				response.status_code,
				cstr(response.text).strip()[:500] or _("Unknown provider response"),
			)
		) from exc

	try:
		payload = response.json()
	except ValueError as exc:
		raise ValidationError(_("Exchange rate request to {0} returned invalid JSON.").format(url)) from exc

	if not isinstance(payload, dict):
		raise ValidationError(_("Exchange rate request to {0} returned an unexpected payload.").format(url))

	return payload


def parse_provider_timestamp(value: Any) -> datetime | None:
	if value in (None, ""):
		return None
	# Frappe Datetime fields expect naive values, so normalize provider UTC timestamps
	# before persisting them into Currency Exchange provenance fields.
	return datetime.fromtimestamp(int(value), tz=UTC).replace(tzinfo=None)


def normalize_requested_currencies(currencies: list[str], *, source_currency: str) -> list[str]:
	requested = {source_currency}
	for currency in currencies:
		normalized = cstr(currency).strip().upper()
		if normalized:
			requested.add(normalized)
	return sorted(requested)


def get_provider_api_key(provider) -> str | None:
	if hasattr(provider, "get_password"):
		api_key = provider.get_password("api_key", raise_exception=False)
	else:
		api_key = getattr(provider, "api_key", None)
	text = cstr(api_key or "").strip()
	return text or None


def get_provider_timeout_seconds(provider) -> int:
	timeout_seconds = cint(getattr(provider, "timeout_seconds", 0))
	return timeout_seconds if timeout_seconds > 0 else DEFAULT_TIMEOUT_SECONDS


def get_provider_source_currency(provider) -> str:
	return cstr(getattr(provider, "default_source_currency", "") or DEFAULT_SOURCE_CURRENCY).strip().upper()
