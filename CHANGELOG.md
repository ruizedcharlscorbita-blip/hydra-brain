# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.2.0] - 2026-07-16

### Added
- **Live Health Pings:** Upgraded `health/monitor.py` to perform active completions pings using `max_tokens=1` to test real endpoint status.
- **Provider Error Diagnostics:** Captures and classifies specific HTTP errors (429 Rate Limits, 502 Bad Gateway, 401 Unauthorized) and records status values (`rate_limited`, `degraded`, `unavailable`).
- **Data Boundary Safety:** Ensures updates modify only the `"health"` subkey of each registry model, conforming to data ownership specs.
- **Fallback Mocks:** Retains stable mock/simulated checks when `HYDRA_MOCK=true` or when no API credentials are configured.

## [0.1.0] - 2026-07-15

### Added
- **OpenRouter Discovery:** Discovers and filters free models from the OpenRouter API.
- **Model Registry:** Wraps model details in a structured schema envelope (v1.0) with stable, deterministic hash IDs.
- **Self-Healing Normalizer:** Automatically repairs model listings with stable IDs and placeholders on save.
- **Registry API:** Exposes public search, provider filtering, and model lookup functions.
- **Health Monitor:** Evaluates model latency and availability, writing checks in-place.
- **Inventory Validation:** Ensures format compliance and unique constraints.
- **Comparison Engine:** Analyzes current models against historical snapshots.
- **Structured Reporting:** Writes Markdown diff summaries and active catalog reports.
- **Standardized Documentation:** Introduces Architecture Specifications and Registry Schemas.
