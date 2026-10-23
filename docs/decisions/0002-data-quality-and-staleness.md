# ADR 0002 — Data quality and staleness

**Status:** accepted · **Date:** 2026-10-23

## Decision
- Qualities: `valid`, `simulated`, `stale`, `disconnected`, `error`. Adapters emit
  `valid`/`simulated`/`error`; the state store derives `stale`/`disconnected` from the age
  since the last reading, per-source thresholds in config.
- Age uses `time.monotonic()`, never the wall clock: the Pi has no RTC battery by default and
  may be offline, so system time can be wrong (even 1970) after boot.
- Unknown measurements are `None`. Views to the UI drop measured values when a source is
  `disconnected` or `error`; `stale` values stay visible but dimmed and labelled.
- An adapter that loses its device stops publishing rather than inventing a quality.
- Whether data is simulated is a property of the adapter, so the SIMULATED label remains
  even when simulated data becomes stale.
- Threshold alarms evaluate only live data (no flicker from silent devices); unavailability
  of watched sources is a separate informational notice.
