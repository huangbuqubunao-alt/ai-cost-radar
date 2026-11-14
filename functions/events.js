// Cloudflare Pages Function: POST /events
// First-party, zero-SDK, non-blocking event collector backed by Cloudflare D1 free tier.
// If D1 is unbound or hits free-tier limits, returns 202 so client math & links never break.

const ALLOWED_EVENTS = new Set([
  "page_view",
  "result_view",
  "usage_import",
  "offer_impression",
  "affiliate_click",
  "share_copy",
  "share_summary",
  "share_open",
]);

const ALLOWED_ROUTES = new Set([
  "/",
  "/coding-plan-2026/",
  "/deepseek-vs-qwen/",
  "/claude-code-domestic/",
  "/dify-openclaw-cloud-server/",
]);

const SAFE_TOKEN_RE = /^[A-Za-z0-9_./:\-]{1,96}$/;
const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

function sanitizeToken(val, maxLen = 80, fallback = "") {
  const s = String(val || "").trim().slice(0, maxLen);
  return SAFE_TOKEN_RE.test(s) ? s : fallback;
}

export async function onRequestOptions() {
  return new Response(null, {
    status: 204,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    },
  });
}

export async function onRequestPost(context) {
  let payload;
  try {
    payload = await context.request.json();
  } catch {
    return Response.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  const eventName = String(payload?.event_name || "").trim();
  const dayBucket = String(payload?.day_bucket || "").trim();
  const browserDayId = sanitizeToken(payload?.browser_day_id, 48, "");

  if (!ALLOWED_EVENTS.has(eventName) || !DAY_RE.test(dayBucket) || browserDayId.length < 4) {
    return Response.json({ ok: false, error: "validation_failed" }, { status: 400 });
  }

  const rawRoute = String(payload?.route || "/").trim();
  const route = ALLOWED_ROUTES.has(rawRoute) ? rawRoute : "/";
  const sourceChannel = sanitizeToken(payload?.source_channel, 64, "unknown");
  const offerId = sanitizeToken(payload?.offer_id, 80, "");
  const slotId = sanitizeToken(payload?.slot_id, 48, "");
  const rawMode = String(payload?.usage_mode || "").trim();
  const usageMode = rawMode === "interactive_ide" || rawMode === "automated_backend" ? rawMode : "";
  const matchedModelId = sanitizeToken(payload?.matched_model_id, 80, "");

  const db = context.env?.DB;
  if (!db) {
    return Response.json({ ok: true, degraded: "no_d1_binding" }, { status: 202 });
  }

  try {
    await db
      .prepare(
        `INSERT INTO telemetry_events
          (day_bucket, event_name, route, browser_day_id, source_channel, offer_id, slot_id, usage_mode, matched_model_id)
         VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9)`
      )
      .bind(
        dayBucket,
        eventName,
        route,
        browserDayId,
        sourceChannel,
        offerId,
        slotId,
        usageMode,
        matchedModelId
      )
      .run();
    return Response.json({ ok: true }, { status: 202 });
  } catch {
    // Graceful degradation when free-tier daily quota is exhausted
    return Response.json({ ok: true, degraded: "d1_write_skipped" }, { status: 202 });
  }
}
