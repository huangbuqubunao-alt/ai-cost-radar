// Cloudflare Pages Function: GET & POST /admin/stats
// Fail-closed private reconciliation endpoint protected by env.ADMIN_STATS_TOKEN.
// Separates: 估算日 UV, 测算完成, 卡片点击率(去重点击/去重曝光), 厂商有效订单, 已结算人民币.

function isAuthorized(request, env) {
  const expected = String(env?.ADMIN_STATS_TOKEN || "").trim();
  if (!expected || expected.length < 12) return false; // Fail-closed when unconfigured
  const auth = request.headers.get("Authorization") || "";
  return auth === `Bearer ${expected}`;
}

export async function onRequestGet(context) {
  if (!isAuthorized(context.request, context.env)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  const db = context.env?.DB;
  if (!db) {
    return Response.json({ error: "d1_not_bound" }, { status: 503 });
  }

  const url = new URL(context.request.url);
  const today = new Date().toISOString().slice(0, 10);
  const day = /^\d{4}-\d{2}-\d{2}$/.test(url.searchParams.get("day") || "")
    ? url.searchParams.get("day")
    : today;

  const kpiRows = await db
    .prepare(
      `SELECT
         COUNT(DISTINCT browser_day_id) AS estimated_daily_uv,
         COUNT(DISTINCT CASE WHEN event_name = 'result_view' THEN browser_day_id END) AS calculations_completed_uv,
         COUNT(DISTINCT CASE WHEN event_name = 'usage_import' THEN browser_day_id END) AS usage_imports_uv,
         COUNT(DISTINCT CASE WHEN event_name IN ('share_copy', 'share_summary') THEN browser_day_id END) AS shares_copied_uv,
         COUNT(DISTINCT CASE WHEN event_name = 'share_open' THEN browser_day_id END) AS share_opens_uv
       FROM telemetry_events
       WHERE day_bucket = ?1`
    )
    .bind(day)
    .first();

  const trafficRows = await db.prepare(
    `SELECT route, source_channel, COUNT(DISTINCT browser_day_id) AS unique_visitors
     FROM telemetry_events WHERE day_bucket = ?1 GROUP BY route, source_channel`
  ).bind(day).all();

  const placements = await db.prepare(
    `SELECT route, source_channel, offer_id, slot_id,
       COUNT(DISTINCT CASE WHEN event_name = 'offer_impression' THEN browser_day_id END) AS unique_viewers,
       COUNT(DISTINCT CASE WHEN event_name = 'affiliate_click' THEN browser_day_id END) AS unique_clickers
     FROM telemetry_events WHERE day_bucket = ?1 AND offer_id != ''
       GROUP BY route, source_channel, offer_id, slot_id`
  ).bind(day).all();

  const offerRows = await db
    .prepare(
      `SELECT
         offer_id,
         COUNT(DISTINCT CASE WHEN event_name = 'offer_impression' THEN browser_day_id END) AS unique_viewers,
         COUNT(DISTINCT CASE WHEN event_name = 'affiliate_click' THEN browser_day_id END) AS unique_clickers
       FROM telemetry_events
       WHERE day_bucket = ?1 AND offer_id != ''
       GROUP BY offer_id`
    )
    .bind(day)
    .all();

  const ledgerRows = await db
    .prepare(
      `SELECT vendor, valid_orders, pending_rmb, settled_rmb, notes
       FROM vendor_settlement_ledger
       WHERE day_bucket = ?1`
    )
    .bind(day)
    .all();

  const featureRows = await db
    .prepare(
      `SELECT
         event_name,
         COALESCE(NULLIF(slot_id, ''), 'unspecified') AS slot_id,
         COUNT(DISTINCT browser_day_id) AS unique_users
       FROM telemetry_events
       WHERE day_bucket = ?1 AND event_name IN ('usage_import', 'share_copy', 'share_summary', 'share_open')
       GROUP BY event_name, COALESCE(NULLIF(slot_id, ''), 'unspecified')
       ORDER BY unique_users DESC, event_name ASC, slot_id ASC`
    )
    .bind(day)
    .all();

  const offers = (offerRows.results || []).map((r) => ({
    offer_id: r.offer_id,
    unique_viewers: Number(r.unique_viewers || 0),
    unique_clickers: Number(r.unique_clickers || 0),
    ctr_pct:
      Number(r.unique_viewers || 0) > 0
        ? Number(((Number(r.unique_clickers || 0) / Number(r.unique_viewers)) * 100).toFixed(2))
        : 0,
  }));

  const ledger = ledgerRows.results || [];
  const validOrders = ledger.reduce((acc, r) => acc + Number(r.valid_orders || 0), 0);
  const pendingRmb = Number(ledger.reduce((acc, r) => acc + Number(r.pending_rmb || 0), 0).toFixed(2));
  const settledRmb = Number(ledger.reduce((acc, r) => acc + Number(r.settled_rmb || 0), 0).toFixed(2));
  const calcUv = Number(kpiRows?.calculations_completed_uv || 0);

  return Response.json({
    day,
    metric_label_zh: "估算日 UV（短期按日轮换标识，跨设备/清理存储/拦截有偏差）",
    estimated_daily_uv: Number(kpiRows?.estimated_daily_uv || 0),
    calculations_completed_uv: calcUv,
    usage_imports_uv: Number(kpiRows?.usage_imports_uv || 0),
    shares_copied_uv: Number(kpiRows?.shares_copied_uv || 0),
    share_opens_uv: Number(kpiRows?.share_opens_uv || 0),
    offers,
    feature_funnel: (featureRows.results || []).map((r) => ({
      event_name: r.event_name,
      slot_id: r.slot_id || "unspecified",
      unique_users: Number(r.unique_users || 0),
    })),
    traffic: trafficRows.results,
    placements: placements.results.map(row => ({
      ...row,
      ctr_pct: row.unique_viewers ? Number((100 * row.unique_clickers / row.unique_viewers).toFixed(2)) : null,
    })),
    vendor_valid_orders: validOrders,
    pending_commission_rmb: pendingRmb,
    settled_commission_rmb: settledRmb,
    settled_rmb_per_100_calc_users: calcUv > 0 ? Number(((settledRmb / calcUv) * 100).toFixed(2)) : 0,
    vendor_ledger_breakdown: ledger,
  });
}

export async function onRequestPost(context) {
  if (!isAuthorized(context.request, context.env)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  const db = context.env?.DB;
  if (!db) {
    return Response.json({ error: "d1_not_bound" }, { status: 503 });
  }
  const body = await context.request.json();
  const day = String(body?.day_bucket || "").trim();
  const vendor = String(body?.vendor || "").trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || !/^[a-z0-9_-]{2,32}$/.test(vendor)) {
    return Response.json({ error: "invalid_params" }, { status: 400 });
  }
  await db
    .prepare(
      `INSERT INTO vendor_settlement_ledger (day_bucket, vendor, valid_orders, pending_rmb, settled_rmb, notes)
       VALUES (?1, ?2, ?3, ?4, ?5, ?6)
       ON CONFLICT(day_bucket, vendor) DO UPDATE SET
         valid_orders = excluded.valid_orders,
         pending_rmb = excluded.pending_rmb,
         settled_rmb = excluded.settled_rmb,
         notes = excluded.notes,
         updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')`
    )
    .bind(
      day,
      vendor,
      Number(body?.valid_orders || 0),
      Number(body?.pending_rmb || 0),
      Number(body?.settled_rmb || 0),
      String(body?.notes || "").slice(0, 200)
    )
    .run();

  return Response.json({ ok: true, day_bucket: day, vendor });
}
