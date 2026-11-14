-- Cloudflare D1 Free-Tier Schema for AI Cost Radar First-Party Attribution (/events)
-- Privacy-minimal: NO IP addresses, NO cross-day cookies, NO raw freeform user text.

CREATE TABLE IF NOT EXISTS telemetry_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  day_bucket TEXT NOT NULL,
  event_name TEXT NOT NULL,
  route TEXT NOT NULL,
  browser_day_id TEXT NOT NULL,
  source_channel TEXT NOT NULL DEFAULT 'unknown',
  offer_id TEXT NOT NULL DEFAULT '',
  slot_id TEXT NOT NULL DEFAULT '',
  usage_mode TEXT NOT NULL DEFAULT '',
  matched_model_id TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_events_day_name
  ON telemetry_events (day_bucket, event_name);

CREATE INDEX IF NOT EXISTS idx_events_day_offer
  ON telemetry_events (day_bucket, offer_id, event_name);

CREATE TABLE IF NOT EXISTS vendor_settlement_ledger (
  day_bucket TEXT NOT NULL,
  vendor TEXT NOT NULL,
  valid_orders INTEGER NOT NULL DEFAULT 0,
  pending_rmb REAL NOT NULL DEFAULT 0.0,
  settled_rmb REAL NOT NULL DEFAULT 0.0,
  notes TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  PRIMARY KEY (day_bucket, vendor)
);
