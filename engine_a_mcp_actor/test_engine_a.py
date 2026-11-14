#!/usr/bin/env python3
"""
End-to-End Unit & Integration Tests for Engine A:
  1. Live OpenRouter + Mainland China enrichment (models_live.json)
  2. MCP stdio JSON-RPC 2.0 server (initialize, tools/list, tools/call x3)
  3. HTTP API + OpenAPI 3.1.0 Coze spec + x402 HTTP 402 Payment Required gate
  4. Apify PPE ($0.005/query) Actor configuration & execution
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ENGINE_DIR: Path = Path(__file__).resolve().parent
PROJECT_ROOT: Path = ENGINE_DIR.parent
MODELS_LIVE_PATH: Path = PROJECT_ROOT / "shared_data" / "models_live.json"

if str(ENGINE_DIR) not in sys.path:
    sys.path.insert(0, str(ENGINE_DIR))

import mcp_server  # noqa: E402


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class EngineATestSuite(unittest.TestCase):
    def test_01_models_live_schema_and_cn_channels(self) -> None:
        self.assertTrue(MODELS_LIVE_PATH.exists(), "shared_data/models_live.json must exist")
        data = json.loads(MODELS_LIVE_PATH.read_text(encoding="utf-8"))
        self.assertIn("updated_at", data)
        self.assertIn("total_models", data)
        self.assertIn("models", data)
        self.assertEqual(data["total_models"], len(data["models"]))
        self.assertGreaterEqual(data["total_models"], 30)

        cn_keys = {
            m["provider_config_key"]
            for m in data["models"]
            if m.get("region") == "cn_direct"
        }
        self.assertEqual(
            cn_keys,
            {
                "aliyun_bailian_url",
                "tencent_cps_url",
                "siliconflow_invite_url",
                "volcengine_ark_url",
            },
        )
        for m in data["models"]:
            self.assertIn("input_usd_per_1m", m)
            self.assertIn("output_usd_per_1m", m)
            self.assertIn("input_rmb_per_1m", m)
            self.assertIn("output_rmb_per_1m", m)
            self.assertIn("context_length", m)
            self.assertIn("supports_tools", m)
            self.assertIn("modality", m)
            self.assertIn("value_score", m)
            self.assertTrue(set(m["tags"]) & {"cn_direct", "global"})

    def test_02_mcp_stdio_jsonrpc_server(self) -> None:
        requests = [
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
            },
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "recommend_cheapest_model",
                    "arguments": {
                        "task_type": "coding",
                        "min_context": 64000,
                        "region_preference": "cn_direct",
                        "monthly_input_m": 20,
                        "monthly_output_m": 5,
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "calculate_api_budget",
                    "arguments": {
                        "model_query": "deepseek-v3",
                        "daily_requests": 2000,
                        "avg_input_tokens": 1200,
                        "avg_output_tokens": 600,
                    },
                },
            },
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "list_free_and_ultra_cheap_models",
                    "arguments": {"region": "any"},
                },
            },
        ]
        stdin_payload = "\n".join(json.dumps(r) for r in requests) + "\n"
        proc = subprocess.run(
            [sys.executable, str(ENGINE_DIR / "mcp_server.py")],
            input=stdin_payload,
            text=True,
            capture_output=True,
            timeout=15,
            check=True,
        )
        lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
        # 5 requests with 'id' (1 notification produces no output)
        self.assertEqual(len(lines), 5)
        responses = {obj["id"]: obj for obj in (json.loads(ln) for ln in lines)}

        # Verify tools/list
        tools = responses[2]["result"]["tools"]
        tool_names = [t["name"] for t in tools]
        self.assertEqual(
            tool_names,
            [
                "recommend_cheapest_model",
                "calculate_api_budget",
                "list_free_and_ultra_cheap_models",
            ],
        )

        # Verify tools/call #1: recommend_cheapest_model
        rec_res = json.loads(responses[3]["result"]["content"][0]["text"])
        self.assertIsNotNone(rec_res["cheapest_paid_pick"])
        self.assertEqual(rec_res["cheapest_paid_pick"]["region"], "cn_direct")

        # Verify tools/call #2: calculate_api_budget
        bud_res = json.loads(responses[4]["result"]["content"][0]["text"])
        self.assertGreater(bud_res["budget_estimate"]["monthly_rmb"], 0)
        self.assertGreater(bud_res["budget_estimate"]["monthly_usd"], 0)

        # Verify tools/call #3: list_free_and_ultra_cheap_models
        free_res = json.loads(responses[5]["result"]["content"][0]["text"])
        self.assertGreater(free_res["total_free_models"], 0)
        self.assertGreater(free_res["total_ultra_cheap_paid_models"], 0)

    def test_03_http_coze_openapi_and_x402_gate(self) -> None:
        port = _find_free_port()
        mcp_server.ModelRouterHTTPHandler.enable_x402 = True
        httpd = mcp_server.ThreadingHTTPServer(("127.0.0.1", port), mcp_server.ModelRouterHTTPHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.1)

        try:
            # 1. Public /openapi.json check (OpenAPI 3.1.0 for Coze)
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/openapi.json", timeout=5) as resp:
                spec = json.loads(resp.read().decode("utf-8"))
                self.assertEqual(spec["openapi"], "3.1.0")
                self.assertIn("/api/recommend", spec["paths"])
                self.assertIn("/api/budget", spec["paths"])
                self.assertIn("/api/free-cheap", spec["paths"])

            # 2. Unpaid request must return HTTP 402 Payment Required with wallet from config.json
            req_unpaid = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/recommend",
                data=b'{"task_type":"coding"}',
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(req_unpaid, timeout=5)
            self.assertEqual(ctx.exception.code, 402)
            self.assertEqual(ctx.exception.headers.get("X-Payment-Protocol"), "x402")
            self.assertEqual(
                ctx.exception.headers.get("X-Payment-PayTo"),
                mcp_server.get_usdc_wallet(),
            )
            ctx.exception.close()

            # 3. Paid request with X-PAYMENT header succeeds with 200 OK
            req_paid = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/recommend",
                data=b'{"task_type":"reasoning","region_preference":"global"}',
                headers={
                    "Content-Type": "application/json",
                    "X-PAYMENT": "demo-base-usdc-tx-proof",
                },
                method="POST",
            )
            with urllib.request.urlopen(req_paid, timeout=5) as resp2:
                self.assertEqual(resp2.status, 200)
                paid_body = json.loads(resp2.read().decode("utf-8"))
                self.assertGreater(len(paid_body["recommendations"]), 0)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_04_apify_actor_and_ppe_execution(self) -> None:
        ppe = json.loads((ENGINE_DIR / ".actor" / "pay_per_event.json").read_text(encoding="utf-8"))
        self.assertEqual(ppe["routing-query"]["eventPriceUsd"], 0.005)

        actor_cfg = json.loads((ENGINE_DIR / ".actor" / "actor.json").read_text(encoding="utf-8"))
        self.assertEqual(actor_cfg["actorSpecification"], 1)

        proc = subprocess.run(
            [
                sys.executable,
                str(ENGINE_DIR / "apify_main.py"),
                "--input",
                '{"action":"calculate_api_budget","model_query":"qwen3","daily_requests":500}',
            ],
            text=True,
            capture_output=True,
            timeout=15,
            check=True,
        )
        out = json.loads(proc.stdout)
        self.assertEqual(out["charged_event"], "routing-query")
        self.assertEqual(out["event_price_usd"], 0.005)
        self.assertIn("budget_estimate", out["result"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
