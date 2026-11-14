#!/usr/bin/env python3
"""
Engine A — Ready-to-Deploy Apify Actor Entrypoint (Pay-Per-Event $0.005/query + Standby MCP).

Uses Python 3.14 standard library ONLY (zero pip dependencies).
Communicates directly with the Apify Platform v2 REST API via runtime environment
variables (APIFY_TOKEN, APIFY_ACTOR_RUN_ID, APIFY_DEFAULT_DATASET_ID,
APIFY_DEFAULT_KEY_VALUE_STORE_ID) and runs locally out of the box for testing.

Publish command:
  cd engine_a_mcp_actor && apify push
Payouts:
  Apify Store -> PayPal ($20 minimum threshold) or Payoneer.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

ENGINE_DIR: Path = Path(__file__).resolve().parent
if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import fetch_and_enrich  # noqa: E402
import mcp_server  # noqa: E402

PPE_EVENT_NAME: str = "routing-query"
PPE_EVENT_PRICE_USD: float = 0.005


def _apify_api_request(
    method: str,
    url: str,
    token: str,
    payload: Any | None = None,
    extra_headers: dict[str, str] | None = None,
) -> tuple[int, bytes]:
    headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    data_bytes: bytes | None = None
    if payload is not None:
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if extra_headers:
        headers.update(extra_headers)

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    ctx = fetch_and_enrich._build_ssl_context()
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def load_actor_input(cli_input_json: str | None = None) -> dict[str, Any]:
    """Load Actor INPUT from CLI flag, local storage, or Apify Cloud Key-Value Store."""
    if cli_input_json:
        return json.loads(cli_input_json)

    env_input = os.environ.get("APIFY_INPUT")
    if env_input:
        return json.loads(env_input)

    local_kv = ENGINE_DIR / "storage" / "key_value_stores" / "default" / "INPUT.json"
    if local_kv.exists():
        return json.loads(local_kv.read_text(encoding="utf-8"))

    api_base = os.environ.get("APIFY_API_BASE_URL", "https://api.apify.com").rstrip("/")
    kv_id = os.environ.get("APIFY_DEFAULT_KEY_VALUE_STORE_ID")
    input_key = os.environ.get("APIFY_INPUT_KEY", "INPUT")
    token = os.environ.get("APIFY_TOKEN")

    if kv_id and token:
        url = f"{api_base}/v2/key-value-stores/{kv_id}/records/{input_key}"
        status, raw = _apify_api_request("GET", url, token)
        if 200 <= status < 300 and raw:
            return json.loads(raw.decode("utf-8"))

    # Default demo input for zero-config test runs
    return {
        "action": "recommend_cheapest_model",
        "task_type": "coding",
        "min_context": 64000,
        "region_preference": "any",
        "monthly_input_m": 15.0,
        "monthly_output_m": 3.0,
    }


def charge_ppe_event(event_name: str = PPE_EVENT_NAME, count: int = 1) -> dict[str, Any]:
    """Trigger Apify Pay-Per-Event ($0.005) billing via Actor Run Charge API."""
    api_base = os.environ.get("APIFY_API_BASE_URL", "https://api.apify.com").rstrip("/")
    run_id = os.environ.get("APIFY_ACTOR_RUN_ID")
    token = os.environ.get("APIFY_TOKEN")

    if not (run_id and token):
        return {
            "mode": "local_simulation",
            "charged": False,
            "event_name": event_name,
            "count": count,
            "estimated_usd": round(PPE_EVENT_PRICE_USD * count, 4),
        }

    url = f"{api_base}/v2/actor-runs/{run_id}/charge"
    idem_key = f"{run_id}-{event_name}-{uuid.uuid4()}"
    status, raw = _apify_api_request(
        method="POST",
        url=url,
        token=token,
        payload={"eventName": event_name, "count": count},
        extra_headers={"idempotency-key": idem_key},
    )
    return {
        "mode": "apify_cloud",
        "charged": 200 <= status < 300,
        "http_status": status,
        "event_name": event_name,
        "count": count,
        "estimated_usd": round(PPE_EVENT_PRICE_USD * count, 4),
        "response": raw.decode("utf-8", errors="replace") if raw else "",
    }


def push_dataset_and_output(records: list[dict[str, Any]]) -> None:
    """Save output items to Apify Default Dataset + OUTPUT KV record (or local storage)."""
    api_base = os.environ.get("APIFY_API_BASE_URL", "https://api.apify.com").rstrip("/")
    dataset_id = os.environ.get("APIFY_DEFAULT_DATASET_ID")
    kv_id = os.environ.get("APIFY_DEFAULT_KEY_VALUE_STORE_ID")
    token = os.environ.get("APIFY_TOKEN")

    if dataset_id and token:
        ds_url = f"{api_base}/v2/datasets/{dataset_id}/items"
        _apify_api_request("POST", ds_url, token, payload=records)

    if kv_id and token:
        kv_url = f"{api_base}/v2/key-value-stores/{kv_id}/records/OUTPUT"
        output_obj = records[0] if len(records) == 1 else {"results": records}
        _apify_api_request("PUT", kv_url, token, payload=output_obj)


def execute_single_query(item: dict[str, Any]) -> dict[str, Any]:
    action = str(item.get("action") or "recommend_cheapest_model").strip()
    args = dict(item)
    if action == "list_free_and_ultra_cheap_models" and "region" not in args:
        args["region"] = args.get("region_preference", "any")
    if (
        action == "calculate_api_budget"
        and args.get("monthly_requests") is None
        and args.get("daily_requests") is not None
        and args.get("monthly_input_m") == 10
        and args.get("monthly_output_m") == 2
    ):
        args.pop("monthly_input_m", None)
        args.pop("monthly_output_m", None)

    charge_info = charge_ppe_event(PPE_EVENT_NAME, count=1)
    tool_result = mcp_server.dispatch_tool_call(action, args)
    return {
        "action": action,
        "charged_event": PPE_EVENT_NAME,
        "event_price_usd": PPE_EVENT_PRICE_USD,
        "billing": charge_info,
        "result": tool_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Apify PPE Actor entrypoint for AI Model Price Router")
    parser.add_argument("--input", type=str, default=None, help="Inline JSON input for local testing")
    args = parser.parse_args()

    # Support Apify Standby Web / Hosted MCP Server mode automatically
    if os.environ.get("APIFY_META_ORIGIN") == "STANDBY":
        port = int(os.environ.get("ACTOR_WEB_SERVER_PORT", "4321"))
        mcp_server.run_http_server(port=port, host="0.0.0.0", enable_x402=False)
        return

    actor_input = load_actor_input(args.input)

    if actor_input.get("refresh_live") or not mcp_server.MODELS_LIVE_PATH.exists():
        fetch_and_enrich.refresh_models_live(mcp_server.MODELS_LIVE_PATH)

    batch_queries = actor_input.get("queries")
    if isinstance(batch_queries, list) and batch_queries:
        outputs = [execute_single_query(q) for q in batch_queries if isinstance(q, dict)]
    else:
        outputs = [execute_single_query(actor_input)]

    push_dataset_and_output(outputs)
    print(json.dumps(outputs[0] if len(outputs) == 1 else outputs, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
