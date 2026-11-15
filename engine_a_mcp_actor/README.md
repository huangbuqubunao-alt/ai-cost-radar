# AI LLM Price Router & Token Budget Calculator (MCP + Pay-Per-Event Actor)

Real-time AI model cost router and monthly/annual API budget calculator across **80+ Global (OpenRouter USD)** and **Mainland China Direct (Aliyun Bailian Qwen3, Tencent Cloud DeepSeek/Hunyuan, SiliconFlow, Volcengine Doubao RMB)** LLM endpoints.

Built with **zero third-party dependencies** for `<50ms` cold starts, supporting both **standard Actor runs** and **Apify Standby Hosted MCP Server (`/mcp`)** mode.

## Supported Actions (`action`)

1. **`recommend_cheapest_model`** *(default)* — Finds the cheapest paid pick, highest value-score pick, and best `$0 / ¥0` free pick matching your `task_type` (`coding`, `reasoning`, `general`, `multimodal`, `cheap`, `free`), `min_context`, and `region_preference` (`any`, `global`, `cn_direct`), plus optional `hybrid_80_20_litellm_config`.
2. **`calculate_api_budget`** — Computes daily, monthly, and yearly API bills in both **USD ($)** and **RMB (¥)** from `model_query`, `daily_requests`, `avg_input_tokens`, `avg_output_tokens`, `team_size` (`1..50`), or real multi-file CSV/JSONL/JSON bills (`usage_snippet`, `usage_snippets`, `usage_file_names`) across **Claude Code `.jsonl`**, **OpenAI Codex CLI `.jsonl`** (`turn_context` + `token_usage_record`), **VS Code Cline / Roo Code `ui_messages.json`**, and cloud CSVs with streaming deduplication, per-session `file_breakdown` cost ranking, `bill_audit`, and zero-code `migration_litellm_config`.
3. **`list_free_and_ultra_cheap_models`** — Lists all currently verified `$0 / ¥0` free LLM APIs and ultra-low-cost production models (`<= $0.50 / 1M` blended tokens).

## Standalone Local Coding Clients CLI Scanner (`audit_local_claude.py`)

Scan local **Claude Code** (`~/.claude/projects`), **OpenAI Codex CLI** (`~/.codex/sessions`), and **VS Code / Cursor Cline & Roo Code** (`ui_messages.json`) session transcripts 100% locally (read-only, zero raw log uploads) to rank models, clients (`--client {all,claude,codex,cline}`), and high-spend sessions by 30-day RMB spend:

```bash
python3 audit_local_claude.py --client all --days 30 --seats 1 --export-csv summary.csv
# Or run directly via hosted static script:
curl -fsSL https://ai-cost-radar-nlu.pages.dev/audit_local_claude.py | python3 - --days 30
```

## Example Input

```json
{
  "action": "recommend_cheapest_model",
  "task_type": "coding",
  "min_context": 64000,
  "region_preference": "any",
  "monthly_input_m": 15,
  "monthly_output_m": 3
}
```

## Pricing (Pay-Per-Event)

- **`routing-query`**: `$0.005` USD per routing recommendation or budget calculation query (`200 queries = $1.00`).
