# fab Exchange Rate Sync

Automatic exchange-rate synchronization for ERPNext.

## Scope

`fab_exchange_rate_sync` manages provider-driven updates for native ERPNext
`Currency Exchange` records while keeping operator control over cadence,
fallbacks, and manual overrides.

Current responsibilities include:

- syncing native `Currency Exchange` records
- supporting primary and fallback providers
- enforcing minimum refresh intervals per provider plan
- protecting manually maintained rates unless explicitly allowed
- storing sync provenance on the generated exchange-rate records

Included providers currently include:

- Open Exchange Rates
- ExchangeRate.host

## Branches

- `develop`: integration branch for testing against Frappe/ERPNext `develop`
- `version-16`: stable branch for Frappe/ERPNext 16

## Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app https://github.com/fabricatorsltd/frappe-fab-exchange-rate-sync.git --branch version-16
bench --site [site] install-app fab_exchange_rate_sync
```

## Setup

1. Open **Exchange Rate Provider** and configure the seeded provider records.
2. Open **Exchange Rate Sync Settings**.
3. Choose the primary provider, optional fallback, and the currency pairs to sync.
4. Enable scheduled sync or run **Sync Now** manually.

## Contributing

Follow the official Frappe contribution guidelines:

- <https://github.com/frappe/erpnext/wiki/Contribution-Guidelines>

Contributions here should follow the same proposal, coding, review, and
documentation expectations as upstream Frappe apps.

## Development

```bash
cd apps/fab_exchange_rate_sync
pre-commit install
```

Pre-commit is configured for Ruff, ESLint, Prettier, and PyUpgrade.

## License

GNU Affero General Public License v3.0
