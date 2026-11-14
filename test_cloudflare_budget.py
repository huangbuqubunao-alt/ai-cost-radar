"""Exercise the deployed JavaScript arithmetic against the Python engine and invalid requests."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "engine_a_mcp_actor"))
import pricing_core


class BudgetEndpointTests(unittest.TestCase):
    def run_js(self, cases):
        runner = '''
import fs from 'node:fs';
const source = fs.readFileSync('functions/api/budget.js', 'utf8');
const {calculateBudget, onRequestGet} = await import('data:text/javascript;base64,' + Buffer.from(source).toString('base64'));
const {catalog, cases} = JSON.parse(fs.readFileSync(0, 'utf8'));
const outputs = [];
for (const query of cases) {
  const request = new Request('https://example.test/api/budget?' + new URLSearchParams(query));
  const response = await onRequestGet({request, env: {ASSETS: {fetch: async () => Response.json(catalog)}}});
  outputs.push({status: response.status, body: await response.json()});
}
console.log(JSON.stringify(outputs));
'''
        catalog = json.loads((ROOT / "shared_data/models_live.json").read_text())
        result = subprocess.run(["node", "--input-type=module", "-e", runner], cwd=ROOT,
                                input=json.dumps({"catalog": catalog, "cases": cases}), text=True, capture_output=True, check=True)
        return catalog, json.loads(result.stdout)

    def test_arithmetic_and_quota_parity(self):
        catalog = json.loads((ROOT / "shared_data/models_live.json").read_text())
        models = [next(m for m in catalog["models"] if "reasoning" in m["tags"] and not m["is_free"]),
                  next(m for m in catalog["models"] if m["region"] == "cn_direct" and "reasoning" not in m["tags"])]
        cases = [{"model_id": m["id"], "daily_requests": "5000", "cache_hit_rate": ".5", "reasoning_multiplier": "2.5",
                  "output_includes_reasoning": inc} for m in models for inc in ("true", "false")]
        _, results = self.run_js(cases)
        for case, result in zip(cases, results):
            self.assertEqual(result["status"], 200)
            model = next(m for m in models if m["id"] == case["model_id"])
            expected = pricing_core.calculate_token_bill(monthly_input_m=225, monthly_output_m=75,
                input_price_per_1m=model["input_rmb_per_1m"], output_price_per_1m=model["output_rmb_per_1m"],
                cache_hit_factor=model["cache_hit_factor"], cache_hit_rate=.5,
                reasoning_multiplier=2.5 if "reasoning" in model["tags"] else 1,
                output_includes_reasoning=case["output_includes_reasoning"] == "true")
            self.assertAlmostEqual(result["body"]["monthly_rmb"], expected["total_cost"], delta=.0001)
            self.assertEqual(result["body"]["monthly_requests"], 150000)
            self.assertIn("60000", result["body"]["summary_cn"])
            self.assertTrue(all(not t["eligible_by_provided_usage"] for p in result["body"]["coding_plans"] for t in p["tiers"]))

    def test_peak_backend_and_invalid_input(self):
        model = json.loads((ROOT / "shared_data/models_live.json").read_text())["models"][0]["id"]
        cases = [{"model_id": model, "daily_requests": "800", "peak_5h_calls": "6500"},
                 {"model_id": model, "usage_mode": "automated_backend"},
                 {"model_id": "unknown"}, {"model_id": model, "cache_hit_rate": "NaN"},
                 {"model_id": model, "daily_requests": "-1"}, {"model_id": model, "output_includes_reasoning": "garbage"}]
        _, results = self.run_js(cases)
        self.assertEqual([r["status"] for r in results], [200, 200, 400, 400, 400, 400])
        self.assertIn("5 小时", results[0]["body"]["summary_cn"])
        self.assertIn("peak5h=6500", results[0]["body"]["web_calculator_url"])
        self.assertTrue(all(not t["eligible_by_provided_usage"] for p in results[1]["body"]["coding_plans"] for t in p["tiers"]))
        _, unknown = self.run_js([{"model_id": model, "daily_requests": "800"}])
        pro = unknown[0]["body"]["coding_plans"][0]["tiers"][1]
        self.assertIsNone(pro["eligible_by_provided_usage"])
        self.assertIsNone(pro["renewal_saving_rmb"])


if __name__ == "__main__":
    unittest.main()
