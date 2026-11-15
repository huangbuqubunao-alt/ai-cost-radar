// Public, stateless price arithmetic. Never calls a paid model API or records input.
function number(params, key, fallback, max) {
  const raw = params.get(key);
  const value = raw === null ? fallback : Number(raw);
  if (raw === "" || !Number.isFinite(value) || value < 0 || value > max) {
    throw new Error(`Invalid ${key}`);
  }
  return value;
}

function parseScaledNumber(rawVal) {
  if (typeof rawVal === "number") {
    if (!Number.isFinite(rawVal) || rawVal < 0) throw new Error("Invalid numeric value");
    return rawVal;
  }
  const s = String(rawVal ?? "").trim().replace(/[,_]/g, "");
  if (!s) throw new Error("Empty number");
  const m = s.match(/^([0-9]+(?:\.[0-9]+)?)\s*(百万|亿|万|千|[kKmMbBwW])?$/);
  if (!m) throw new Error(`Invalid number: ${rawVal}`);
  const base = Number(m[1]);
  const unit = (m[2] || "").toLowerCase();
  const multMap = {
    b: 1e9,
    "亿": 1e8,
    m: 1e6,
    "百万": 1e6,
    w: 1e4,
    "万": 1e4,
    k: 1e3,
    "千": 1e3,
    "": 1,
  };
  return Math.max(0, base * (multMap[unit] ?? 1));
}

function splitDelimitedLine(line, delim) {
  const cells = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === delim && !inQuotes) {
      cells.push(cur.trim());
      cur = "";
    } else {
      cur += ch;
    }
  }
  cells.push(cur.trim());
  return cells;
}

function parseCurrencyRmb(rawVal, headerCompact, fxRate = 7.2) {
  const s = String(rawVal ?? "").trim();
  if (!s || ["-", "n/a", "na", "null", "none"].includes(s.toLowerCase())) return 0;
  const sLow = s.toLowerCase();
  let isRmb = false;
  if (["¥", "￥", "rmb", "cny", "元"].some((sym) => sLow.includes(sym))) isRmb = true;
  else if (["$", "usd"].some((sym) => sLow.includes(sym))) isRmb = false;
  else if (["rmb", "cny", "应付金额", "账单金额", "消费金额", "费用", "金额", "花费", "总费用", "元"].some((k) => headerCompact.includes(k))) isRmb = true;

  const cleaned = s
    .replace(/^(?:usd|rmb|cny|us\$|[$¥￥])\s*/i, "")
    .replace(/\s*(?:usd|rmb|cny|元)$/i, "")
    .trim();
  if (!cleaned) return 0;
  const val = parseScaledNumber(cleaned);
  return isRmb ? val : val * fxRate;
}

function tryParseCsvBill(text, days, fxRate = 7.2) {
  const rawLines = [];
  for (const ln of text.split(/\r?\n/)) {
    const s = ln.trim();
    if (!s || s.startsWith("#")) continue;
    if (/^\|?[\s:-]+(?:\|[\s:-]+)+\|?$/.test(s)) continue;
    rawLines.push(s);
  }
  if (rawLines.length < 2) return null;

  const headerLine = rawLines[0];
  const pipeCount = (headerLine.match(/\|/g) || []).length;
  const isPipe = pipeCount >= 2;
  let delim = null;
  if (isPipe) {
    delim = "|";
  } else {
    const counts = ["\t", ",", ";"].map((d) => [d, headerLine.split(d).length - 1]);
    counts.sort((a, b) => b[1] - a[1]);
    if (counts[0][1] >= 1) delim = counts[0][0];
  }
  if (!delim) return null;

  const rows = isPipe
    ? rawLines.map((ln) => ln.replace(/^\|+|\|+$/g, "").split("|").map((c) => c.trim().replace(/^['"]|['"]$/g, "")))
    : rawLines.map((ln) => splitDelimitedLine(ln, delim));
  if (rows.length < 2) return null;

  const rawHeaders = rows[0].map((c) => String(c || "").trim().replace(/^\ufeff/, "").replace(/^['"]|['"]$/g, ""));
  if (rawHeaders.length < 2) return null;
  if (rawHeaders.some((h) => h && /^[0-9.]+$/.test(h))) return null;

  const compactHeaders = rawHeaders.map((h) => h.toLowerCase().replace(/[\s_\-()/（）]+/g, ""));
  const modelAliases = new Set(["model", "modelid", "modelname", "modelpermaslug", "modelslug", "permaslug", "endpoint", "模型", "模型名称", "模型id", "调用模型"]);
  const reqAliases = new Set(["requests", "requestcount", "numrequests", "calls", "apicalls", "totalrequests", "totalcalls", "count", "调用次数", "请求次数", "请求数", "调用量"]);
  const inAliases = new Set(["tokensprompt", "nativetokensprompt", "prompttokens", "inputtokens", "totalinputtokens", "input", "prompt", "输入token", "输入tokens", "输入token数", "提问token", "入参token"]);
  const outAliases = new Set(["tokenscompletion", "nativetokenscompletion", "completiontokens", "outputtokens", "totaloutputtokens", "output", "completion", "输出token", "输出tokens", "输出token数", "回答token", "出参token"]);
  const cachedAliases = new Set(["nativetokenscached", "cachedtokens", "cachedinputtokens", "prompttokenscached", "cachehit", "缓存命中token", "缓存命中tokens", "命中缓存token", "缓存token", "缓存输入token", "命中缓存"]);
  const cReadAliases = new Set(["cachereadinputtokens", "cachereadtokens", "cacheread"]);
  const cWriteAliases = new Set(["cachecreationinputtokens", "cachewritetokens", "cachewrite", "缓存写入token"]);
  const reasonAliases = new Set(["nativetokensreasoning", "reasoningtokens", "thinkingtokens", "思考token", "思考tokens", "推理token"]);
  const costAliases = new Set(["usage", "cost", "totalcost", "spend", "amount", "bill", "costusd", "spendusd", "costrmb", "costcny", "应付金额", "账单金额", "消费金额", "费用", "金额", "花费", "总费用"]);

  const findCol = (set) => {
    const idx = compactHeaders.findIndex((ch) => set.has(ch));
    return idx >= 0 ? idx : null;
  };

  const colModel = findCol(modelAliases);
  const colReq = findCol(reqAliases);
  const colIn = findCol(inAliases);
  const colOut = findCol(outAliases);
  const colCached = findCol(cachedAliases);
  const colCRead = findCol(cReadAliases);
  const colCWrite = findCol(cWriteAliases);
  const colReason = findCol(reasonAliases);
  const colCost = findCol(costAliases);

  if (colIn === null && colOut === null) return null;

  const summaryLabels = new Set(["total", "totals", "sum", "summary", "合计", "总计", "汇总", "小计"]);
  const groups = new Map();
  const costHeaderCompact = colCost !== null ? compactHeaders[colCost] : "";
  const headerSig = compactHeaders.join("\u0001");

  const cellNum = (r, idx) => {
    if (idx === null || idx >= r.length) return 0;
    const v = String(r[idx] ?? "").trim();
    if (!v || ["-", "n/a", "na", "null", "none"].includes(v.toLowerCase())) return 0;
    return parseScaledNumber(v);
  };

  for (const r of rows.slice(1)) {
    if (!r || r.every((c) => !String(c ?? "").trim())) continue;
    const rowCompact = r.map((c) => String(c ?? "").trim().replace(/^\ufeff/, "").replace(/^['"]|['"]$/g, "").toLowerCase().replace(/[\s_\-()/（）]+/g, ""));
    if (rowCompact.join("\u0001") === headerSig) continue;
    if ((colIn !== null && colIn < rowCompact.length && inAliases.has(rowCompact[colIn])) ||
        (colOut !== null && colOut < rowCompact.length && outAliases.has(rowCompact[colOut]))) continue;
    const firstClean = String(r[0] ?? "").trim().toLowerCase();
    const modelRaw = colModel !== null && colModel < r.length ? String(r[colModel] ?? "").trim() : "";
    if (summaryLabels.has(firstClean) || summaryLabels.has(modelRaw.toLowerCase())) continue;

    const inVal = cellNum(r, colIn);
    const outVal = cellNum(r, colOut);
    const cachedSubVal = cellNum(r, colCached);
    const cReadVal = cellNum(r, colCRead);
    const cWriteVal = cellNum(r, colCWrite);
    const reasonVal = cellNum(r, colReason);

    let rowIn = 0;
    let rowCached = 0;
    if (colCRead !== null || colCWrite !== null) {
      rowIn = inVal + cReadVal + cWriteVal;
      rowCached = cReadVal;
    } else {
      rowIn = Math.max(inVal, cachedSubVal);
      rowCached = Math.min(rowIn, cachedSubVal);
    }
    if (rowIn <= 0 && outVal <= 0) continue;

    let rowReqs = 1;
    if (colReq !== null) {
      const reqVal = cellNum(r, colReq);
      rowReqs = reqVal > 0 ? reqVal : 1;
    }
    const rowCostRmb = colCost !== null && colCost < r.length ? parseCurrencyRmb(r[colCost], costHeaderCompact, fxRate) : 0;
    const modelLabel = modelRaw || "unknown";
    const gKey = modelLabel.toLowerCase();
    if (!groups.has(gKey)) {
      groups.set(gKey, {
        model: modelLabel,
        requests: 0,
        input_tokens: 0,
        cached_input_tokens: 0,
        output_tokens: 0,
        reasoning_tokens: 0,
        reported_cost_rmb: 0,
      });
    }
    const grp = groups.get(gKey);
    grp.requests += rowReqs;
    grp.input_tokens += rowIn;
    grp.cached_input_tokens += rowCached;
    grp.output_tokens += outVal;
    grp.reasoning_tokens += reasonVal;
    grp.reported_cost_rmb += rowCostRmb;
  }

  if (groups.size === 0) {
    throw new Error("CSV bill contains zero positive token rows");
  }

  const sortedGroups = Array.from(groups.values()).sort(
    (a, b) => (b.reported_cost_rmb - a.reported_cost_rmb) || ((b.input_tokens + b.output_tokens) - (a.input_tokens + a.output_tokens))
  );

  let totalReqs = 0;
  let totalIn = 0;
  let totalCached = 0;
  let totalOut = 0;
  let totalReason = 0;
  let totalCostRmb = 0;
  const modelBreakdown = sortedGroups.map((g) => {
    const gIn = g.input_tokens;
    const gCached = Math.min(gIn, Math.max(0, g.cached_input_tokens));
    totalReqs += g.requests;
    totalIn += gIn;
    totalCached += gCached;
    totalOut += g.output_tokens;
    totalReason += g.reasoning_tokens;
    totalCostRmb += g.reported_cost_rmb;
    return {
      model: g.model,
      requests: Math.round(g.requests),
      input_tokens: Math.round(gIn),
      cached_input_tokens: Math.round(gCached),
      output_tokens: Math.round(g.output_tokens),
      reasoning_tokens: Math.round(g.reasoning_tokens),
      cache_hit_rate: gIn > 0 ? Math.round((gCached / gIn) * 10000) / 10000 : 0,
      output_includes_reasoning: g.reasoning_tokens > 0,
      reported_cost_rmb: Math.round(g.reported_cost_rmb * 10000) / 10000,
    };
  });

  const cacheHitRate = totalIn > 0 ? Math.round((totalCached / totalIn) * 10000) / 10000 : 0;
  const dailyRequests = Math.max(1, Math.round(totalReqs / days));
  const monthlyRequests = Math.max(1, Math.round((totalReqs / days) * 30));
  const avgInputTokens = totalIn > 0 ? Math.max(1, Math.round(totalIn / Math.max(1, totalReqs))) : 1500;
  const avgOutputTokens = totalOut > 0 ? Math.max(1, Math.round(totalOut / Math.max(1, totalReqs))) : 500;
  const monthlyInputM = Math.round((((totalIn / days) * 30) / 1e6) * 1e6) / 1e6;
  const monthlyOutputM = Math.round((((totalOut / days) * 30) / 1e6) * 1e6) / 1e6;

  return {
    detected_format: "csv_multimodel_bill",
    source_format: "csv_multimodel",
    deduplicated_chunks: 0,
    days_observed: days,
    distinct_models_count: modelBreakdown.length,
    total_requests: Math.round(totalReqs),
    monthly_requests: monthlyRequests,
    total_input_tokens: Math.round(totalIn),
    cached_input_tokens: Math.round(totalCached),
    total_output_tokens: Math.round(totalOut),
    monthly_input_m: monthlyInputM,
    monthly_output_m: monthlyOutputM,
    daily_requests: dailyRequests,
    avg_input_tokens: avgInputTokens,
    avg_output_tokens: avgOutputTokens,
    cache_hit_rate: cacheHitRate,
    output_includes_reasoning: totalReason > 0,
    calls_estimated: false,
    reported_cost_rmb: Math.round((totalCostRmb + Number.EPSILON) * 100) / 100,
    monthly_reported_cost_rmb: Math.round((((totalCostRmb / days) * 30) + Number.EPSILON) * 100) / 100,
    model_breakdown: modelBreakdown,
  };
}

function extractJsonRecordsRaw(text) {
  let rawRecords = null;
  let sourceFormat = null;

  if (text.startsWith("[") && text.endsWith("]")) {
    try {
      const parsed = JSON.parse(text);
      if (Array.isArray(parsed)) {
        rawRecords = parsed.filter((x) => x && typeof x === "object" && !Array.isArray(x));
        sourceFormat = "json_array_multimodel";
      }
    } catch {
      rawRecords = null;
    }
  } else if (text.startsWith("{") && text.endsWith("}")) {
    try {
      const single = JSON.parse(text);
      if (single && typeof single === "object" && !Array.isArray(single)) {
        for (const listKey of ["data", "records", "logs", "items", "generations"]) {
          const cand = single[listKey];
          if (Array.isArray(cand) && cand.some((x) => x && typeof x === "object" && !Array.isArray(x))) {
            rawRecords = cand.filter((x) => x && typeof x === "object" && !Array.isArray(x));
            sourceFormat = "json_array_multimodel";
            break;
          }
        }
        if (!rawRecords) {
          const msgObj = single.message;
          const respObj = single.response;
          if (
            (msgObj && typeof msgObj === "object" && ((msgObj.usage && typeof msgObj.usage === "object") || ["user", "assistant", "summary", "system"].includes(single.type))) ||
            (respObj && typeof respObj === "object" && respObj.body && typeof respObj.body === "object")
          ) {
            rawRecords = [single];
            sourceFormat = "jsonl_multimodel";
          }
        }
      }
    } catch {
      const lines = text
        .split(/\r?\n/)
        .map((ln) => ln.trim())
        .filter((ln) => ln && !ln.startsWith("#"));
      if (lines.length >= 2) {
        const parsedLines = [];
        let allJsonLines = true;
        for (const ln of lines) {
          if (ln.startsWith("{") && ln.endsWith("}")) {
            try {
              const obj = JSON.parse(ln);
              if (obj && typeof obj === "object" && !Array.isArray(obj)) parsedLines.push(obj);
              else allJsonLines = false;
            } catch {
              allJsonLines = false;
            }
          } else {
            allJsonLines = false;
          }
        }
        if (parsedLines.length >= 2 || (allJsonLines && parsedLines.length >= 1)) {
          rawRecords = parsedLines;
          sourceFormat = "jsonl_multimodel";
        }
      }
    }
  }
  if (!rawRecords || !sourceFormat) return null;
  return {rawRecords, sourceFormat};
}

function collectJsonRecordEntries(rawRecords, fxRate = 7.2) {
  const safeNum = (v) => {
    if (v === undefined || v === null || typeof v === "object" || typeof v === "boolean") return 0;
    try {
      return parseScaledNumber(v);
    } catch {
      return 0;
    }
  };
  const firstVal = (obj, keys) => {
    if (!obj || typeof obj !== "object") return null;
    for (const k of keys) {
      const val = obj[k];
      if (val !== undefined && val !== null && typeof val !== "object" && typeof val !== "boolean") return val;
    }
    return null;
  };

  const skipTypes = new Set(["user", "summary", "system", "file-history-snapshot", "queue-operation"]);
  const summaryLabels = new Set(["total", "totals", "sum", "summary", "合计", "总计", "汇总", "小计"]);
  const dedupedEntries = new Map();
  const anonEntries = [];
  let deduplicatedChunks = 0;

  for (const rec of rawRecords) {
    if (skipTypes.has(String(rec.type || "").trim().toLowerCase())) continue;
    const msg = rec.message && typeof rec.message === "object" ? rec.message : {};
    const resp = rec.response && typeof rec.response === "object" ? rec.response : {};
    const body = resp.body && typeof resp.body === "object" ? resp.body : {};
    const u =
      (msg.usage && typeof msg.usage === "object" ? msg.usage : null) ||
      (body.usage && typeof body.usage === "object" ? body.usage : null) ||
      (rec.usage && typeof rec.usage === "object" ? rec.usage : null) ||
      {};

    const modelRaw =
      firstVal(rec, ["model_permaslug", "model", "model_id", "model_name", "api_model_id"]) ||
      firstVal(msg, ["model", "model_id"]) ||
      firstVal(body, ["model", "model_id"]) ||
      "unknown";
    const modelLabel = String(modelRaw).trim() || "unknown";
    if (summaryLabels.has(modelLabel.toLowerCase())) continue;

    const merged = {...rec, ...body, ...msg, ...u};
    let rowIn = 0;
    let rowCached = 0;
    if ("cache_read_input_tokens" in merged || "cache_creation_input_tokens" in merged) {
      const uncached = safeNum(merged.input_tokens);
      const cRead = safeNum(merged.cache_read_input_tokens);
      const cWrite = safeNum(merged.cache_creation_input_tokens);
      rowIn = uncached + cRead + cWrite;
      rowCached = cRead;
    } else {
      const pDet = merged.prompt_tokens_details && typeof merged.prompt_tokens_details === "object" ? merged.prompt_tokens_details : {};
      const inDet = merged.input_tokens_details && typeof merged.input_tokens_details === "object" ? merged.input_tokens_details : {};
      const inVal = safeNum(firstVal(merged, ["prompt_tokens", "native_tokens_prompt", "tokens_prompt", "input_tokens", "total_input_tokens"]));
      const cRaw = pDet.cached_tokens ?? inDet.cached_tokens ?? firstVal(merged, ["native_tokens_cached", "cached_tokens", "cached_input_tokens", "cache_hit_tokens"]);
      const cVal = safeNum(cRaw);
      rowIn = Math.max(inVal, cVal);
      rowCached = Math.min(rowIn, cVal);
    }

    const outVal = safeNum(firstVal(merged, ["completion_tokens", "native_tokens_completion", "tokens_completion", "output_tokens", "total_output_tokens"]));
    const cDet = merged.completion_tokens_details && typeof merged.completion_tokens_details === "object" ? merged.completion_tokens_details : {};
    const oDet = merged.output_tokens_details && typeof merged.output_tokens_details === "object" ? merged.output_tokens_details : {};
    const rRaw = cDet.reasoning_tokens ?? oDet.reasoning_tokens ?? firstVal(merged, ["native_tokens_reasoning", "reasoning_tokens", "thinking_tokens"]);
    const reasonVal = safeNum(rRaw);

    if (rowIn <= 0 && outVal <= 0) continue;

    const reqRaw = firstVal(rec, ["requests", "total_requests", "calls", "api_calls", "num_requests", "request_count"]);
    const rowReqs = reqRaw !== null ? Math.max(1, safeNum(reqRaw)) : 1;

    const rmbCostRaw = firstVal(rec, ["cost_rmb", "spend_rmb", "cost_cny", "应付金额", "账单金额"]);
    let usdCostRaw = firstVal(rec, ["spend", "response_cost", "cost_usd", "costUSD", "total_cost", "cost"]);
    if (usdCostRaw === null && rec.usage !== undefined && rec.usage !== null && typeof rec.usage !== "object" && typeof rec.usage !== "boolean") {
      usdCostRaw = rec.usage;
    }
    const rowCostRmb = rmbCostRaw !== null
      ? parseCurrencyRmb(rmbCostRaw, "costrmb", fxRate)
      : (usdCostRaw !== null ? parseCurrencyRmb(usdCostRaw, "costusd", fxRate) : 0);

    let dedupeId = null;
    if (reqRaw === null) {
      if (msg.id) dedupeId = `msg:${msg.id}`;
      else if (body.id) dedupeId = `body:${body.id}`;
      else if (rec.generation_id) dedupeId = `gen:${rec.generation_id}`;
      else if (rec.request_id) dedupeId = `req:${rec.request_id}`;
      else if (rec.id) dedupeId = `id:${rec.id}`;
    }

    const entry = {
      model: modelLabel,
      requests: rowReqs,
      input_tokens: rowIn,
      cached_input_tokens: rowCached,
      output_tokens: outVal,
      reasoning_tokens: reasonVal,
      reported_cost_rmb: rowCostRmb,
    };

    if (dedupeId) {
      if (dedupedEntries.has(dedupeId)) {
        deduplicatedChunks += 1;
        const prev = dedupedEntries.get(dedupeId);
        for (const k of ["requests", "input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "reported_cost_rmb"]) {
          prev[k] = Math.max(prev[k], entry[k]);
        }
        if (prev.model === "unknown" && entry.model !== "unknown") prev.model = entry.model;
      } else {
        dedupedEntries.set(dedupeId, entry);
      }
    } else {
      anonEntries.push(entry);
    }
  }
  return {entries: [...dedupedEntries.values(), ...anonEntries], deduplicatedChunks};
}

function buildMultimodelPortfolioFromEntries(allEntries, days, sourceFormat, deduplicatedChunks = 0, mergedFilesCount = null) {
  const groups = new Map();
  for (const ent of allEntries) {
    const gKey = String(ent.model).toLowerCase();
    if (!groups.has(gKey)) {
      groups.set(gKey, {
        model: String(ent.model),
        requests: 0,
        input_tokens: 0,
        cached_input_tokens: 0,
        output_tokens: 0,
        reasoning_tokens: 0,
        reported_cost_rmb: 0,
      });
    }
    const grp = groups.get(gKey);
    grp.requests += Number(ent.requests || 0);
    grp.input_tokens += Number(ent.input_tokens || 0);
    grp.cached_input_tokens += Number(ent.cached_input_tokens || 0);
    grp.output_tokens += Number(ent.output_tokens || 0);
    grp.reasoning_tokens += Number(ent.reasoning_tokens || 0);
    grp.reported_cost_rmb += Number(ent.reported_cost_rmb || 0);
  }

  const sortedGroups = [...groups.values()].sort(
    (a, b) => (b.reported_cost_rmb - a.reported_cost_rmb) || ((b.input_tokens + b.output_tokens) - (a.input_tokens + a.output_tokens))
  );
  let totalReqs = 0;
  let totalIn = 0;
  let totalCached = 0;
  let totalOut = 0;
  let totalReason = 0;
  let totalCostRmb = 0;
  const modelBreakdown = sortedGroups.map((g) => {
    const gIn = g.input_tokens;
    const gCached = Math.min(gIn, Math.max(0, g.cached_input_tokens));
    totalReqs += g.requests;
    totalIn += gIn;
    totalCached += gCached;
    totalOut += g.output_tokens;
    totalReason += g.reasoning_tokens;
    totalCostRmb += g.reported_cost_rmb;
    return {
      model: g.model,
      requests: Math.round(g.requests),
      input_tokens: Math.round(gIn),
      cached_input_tokens: Math.round(gCached),
      output_tokens: Math.round(g.output_tokens),
      reasoning_tokens: Math.round(g.reasoning_tokens),
      cache_hit_rate: gIn > 0 ? Math.round((gCached / gIn) * 10000) / 10000 : 0,
      output_includes_reasoning: g.reasoning_tokens > 0,
      reported_cost_rmb: Math.round((g.reported_cost_rmb + Number.EPSILON) * 10000) / 10000,
    };
  });

  const cacheHitRate = totalIn > 0 ? Math.round((totalCached / totalIn) * 10000) / 10000 : 0;
  const dailyRequests = Math.max(1, Math.round(totalReqs / days));
  const monthlyRequests = Math.max(1, Math.round((totalReqs / days) * 30));
  const out = {
    detected_format: "csv_multimodel_bill",
    source_format: sourceFormat,
    deduplicated_chunks: deduplicatedChunks,
    days_observed: days,
    distinct_models_count: modelBreakdown.length,
    total_requests: Math.round(totalReqs),
    monthly_requests: monthlyRequests,
    total_input_tokens: Math.round(totalIn),
    cached_input_tokens: Math.round(totalCached),
    total_output_tokens: Math.round(totalOut),
    monthly_input_m: Math.round((((totalIn / days) * 30) / 1e6) * 1e6) / 1e6,
    monthly_output_m: Math.round((((totalOut / days) * 30) / 1e6) * 1e6) / 1e6,
    daily_requests: dailyRequests,
    avg_input_tokens: totalIn > 0 ? Math.max(1, Math.round(totalIn / Math.max(1, totalReqs))) : 1500,
    avg_output_tokens: totalOut > 0 ? Math.max(1, Math.round(totalOut / Math.max(1, totalReqs))) : 500,
    cache_hit_rate: cacheHitRate,
    output_includes_reasoning: totalReason > 0,
    calls_estimated: false,
    reported_cost_rmb: Math.round((totalCostRmb + Number.EPSILON) * 100) / 100,
    monthly_reported_cost_rmb: Math.round((((totalCostRmb / days) * 30) + Number.EPSILON) * 100) / 100,
    model_breakdown: modelBreakdown,
  };
  if (mergedFilesCount !== null) out.merged_files_count = mergedFilesCount;
  return out;
}

export function tryParseJsonRecordsBill(text, days, fxRate = 7.2) {
  const extracted = extractJsonRecordsRaw(text);
  if (!extracted) return null;
  const {entries, deduplicatedChunks} = collectJsonRecordEntries(extracted.rawRecords, fxRate);
  if (entries.length === 0) throw new Error("JSON/JSONL bill contains zero positive token records");
  return buildMultimodelPortfolioFromEntries(entries, days, extracted.sourceFormat, deduplicatedChunks);
}

export function mergeUsageSnippets(snippets, daysObserved = 30, fxRate = 7.2) {
  if (!Array.isArray(snippets)) throw new Error("usage_snippets must be an array");
  const cleaned = snippets.map((s) => String(s ?? "").trim()).filter(Boolean);
  if (cleaned.length === 0 || cleaned.length > 50) throw new Error("Invalid usage_snippets");
  const days = Number(daysObserved ?? 30);
  if (!Number.isFinite(days) || days <= 0 || days > 365) throw new Error("Invalid days_observed");
  const totalChars = cleaned.reduce((acc, s) => acc + s.length, 0);
  if (totalChars > 500000 || cleaned.some((s) => s.length > 120000)) throw new Error("Oversized usage_snippets");

  if (cleaned.length === 1) {
    const single = parseUsageSnippet(cleaned[0], days);
    return {...single, merged_files_count: 1};
  }

  const combinedJsonRecords = [];
  const otherEntries = [];
  for (const snippet of cleaned) {
    const ext = extractJsonRecordsRaw(snippet);
    if (ext) {
      combinedJsonRecords.push(...ext.rawRecords);
      continue;
    }
    let csvParsed = null;
    try {
      csvParsed = tryParseCsvBill(snippet, days, fxRate);
    } catch {
      csvParsed = null;
    }
    if (csvParsed) {
      for (const row of (csvParsed.model_breakdown || [])) {
        otherEntries.push({
          model: row.model,
          requests: Number(row.requests || 1),
          input_tokens: Number(row.input_tokens || 0),
          cached_input_tokens: Number(row.cached_input_tokens || 0),
          output_tokens: Number(row.output_tokens || 0),
          reasoning_tokens: Number(row.reasoning_tokens || 0),
          reported_cost_rmb: Number(row.reported_cost_rmb || 0),
        });
      }
      continue;
    }
    let singleParsed = null;
    try {
      singleParsed = parseUsageSnippet(snippet, days);
    } catch {
      continue;
    }
    if (singleParsed.detected_format === "csv_multimodel_bill") {
      for (const row of (singleParsed.model_breakdown || [])) {
        otherEntries.push(row);
      }
    } else {
      otherEntries.push({
        model: ["claude_code_cost", "anthropic_usage_json"].includes(singleParsed.detected_format) ? "claude-sonnet-4" : "deepseek-v3",
        requests: Math.max(1, Math.round(Number(singleParsed.daily_requests || 1) * days)),
        input_tokens: Number(singleParsed.total_input_tokens || 0),
        cached_input_tokens: Number(singleParsed.cached_input_tokens || 0),
        output_tokens: Number(singleParsed.total_output_tokens || 0),
        reasoning_tokens: singleParsed.output_includes_reasoning ? 1 : 0,
        reported_cost_rmb: 0,
      });
    }
  }

  const {entries: jsonEntries, deduplicatedChunks} = combinedJsonRecords.length > 0
    ? collectJsonRecordEntries(combinedJsonRecords, fxRate)
    : {entries: [], deduplicatedChunks: 0};
  const allEntries = [...jsonEntries, ...otherEntries];
  if (allEntries.length === 0) throw new Error("Merged usage_snippets contain zero positive token records");
  return buildMultimodelPortfolioFromEntries(allEntries, days, "multifile_merged", deduplicatedChunks, cleaned.length);
}

export function parseUsageSnippet(rawText, daysObserved = 30, defaultTokensPerCall = 4000) {
  const text = String(rawText ?? "").trim();
  if (!text || text.length > 32000) throw new Error("Invalid usage_snippet");
  let days = Number(daysObserved ?? 30);
  if (!Number.isFinite(days) || days <= 0 || days > 365) throw new Error("Invalid days_observed");

  const jsonRecordsParsed = tryParseJsonRecordsBill(text, days);
  if (jsonRecordsParsed) return jsonRecordsParsed;

  let totalInput = 0;
  let cachedInput = 0;
  let totalOutput = 0;
  let explicitRequests = null;
  let explicitDailyRequests = null;
  let outputIncludesReasoning = false;
  let detectedFormat = "text_summary";

  let jsonObj = null;
  if (text.includes("{") && text.includes("}")) {
    const startIdx = text.indexOf("{");
    const endIdx = text.lastIndexOf("}");
    if (endIdx > startIdx) {
      try {
        const parsed = JSON.parse(text.slice(startIdx, endIdx + 1));
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) jsonObj = parsed;
      } catch {
        jsonObj = null;
      }
    }
  }

  if (jsonObj) {
    const u = jsonObj.usage && typeof jsonObj.usage === "object" ? jsonObj.usage : {};
    const merged = {...jsonObj, ...u};
    if (merged.days_observed !== undefined && daysObserved === 30) {
      const dCand = Number(merged.days_observed);
      if (Number.isFinite(dCand) && dCand > 0 && dCand <= 365) days = dCand;
    }
    for (const rk of ["requests", "total_requests", "calls", "total_calls", "api_calls", "num_requests"]) {
      if (merged[rk] !== undefined && merged[rk] !== null) {
        explicitRequests = parseScaledNumber(merged[rk]);
        break;
      }
    }
    if (explicitRequests === null && merged.daily_requests !== undefined && merged.daily_requests !== null) {
      explicitDailyRequests = parseScaledNumber(merged.daily_requests);
    }
    if ("cache_read_input_tokens" in merged || "cache_creation_input_tokens" in merged) {
      detectedFormat = "anthropic_usage_json";
      const uncached = parseScaledNumber(merged.input_tokens ?? 0);
      const cRead = parseScaledNumber(merged.cache_read_input_tokens ?? 0);
      const cWrite = parseScaledNumber(merged.cache_creation_input_tokens ?? 0);
      totalInput = uncached + cRead + cWrite;
      cachedInput = cRead;
    } else {
      detectedFormat = "openai_usage_json";
      const pDetails = merged.prompt_tokens_details && typeof merged.prompt_tokens_details === "object" ? merged.prompt_tokens_details : {};
      const inDetails = merged.input_tokens_details && typeof merged.input_tokens_details === "object" ? merged.input_tokens_details : {};
      const rawIn = merged.prompt_tokens ?? merged.input_tokens;
      if (rawIn !== undefined && rawIn !== null) totalInput = parseScaledNumber(rawIn);
      else if (merged.monthly_input_m !== undefined && merged.monthly_input_m !== null) totalInput = parseScaledNumber(merged.monthly_input_m) * 1e6;
      const rawCached = pDetails.cached_tokens ?? inDetails.cached_tokens ?? merged.cached_tokens ?? merged.cached_input_tokens;
      if (rawCached !== undefined && rawCached !== null) {
        cachedInput = parseScaledNumber(rawCached);
        if (totalInput < cachedInput) totalInput = cachedInput;
      }
    }
    const rawOut = merged.completion_tokens ?? merged.output_tokens;
    if (rawOut !== undefined && rawOut !== null) totalOutput = parseScaledNumber(rawOut);
    else if (merged.monthly_output_m !== undefined && merged.monthly_output_m !== null) totalOutput = parseScaledNumber(merged.monthly_output_m) * 1e6;
    const cDetails = merged.completion_tokens_details && typeof merged.completion_tokens_details === "object" ? merged.completion_tokens_details : {};
    const oDetails = merged.output_tokens_details && typeof merged.output_tokens_details === "object" ? merged.output_tokens_details : {};
    const rTok = cDetails.reasoning_tokens ?? oDetails.reasoning_tokens ?? merged.reasoning_tokens;
    if (rTok !== undefined && rTok !== null && parseScaledNumber(rTok) > 0) outputIncludesReasoning = true;
  } else {
    const csvParsed = tryParseCsvBill(text, days);
    if (csvParsed) return csvParsed;
    const numPat = "([0-9][0-9,._]*\\s*(?:百万|亿|万|千|[kKmMbBwW])?)";
    const mIn = text.match(new RegExp("(?:total\\s+input(?:\\s+tokens?)?|uncached\\s+input|prompt\\s+tokens?|\\binput(?:\\s+tokens?)?|输入\\s*(?:token|tokens)?)\\s*[:：=]?\\s*" + numPat, "i"));
    const mCacheRead = text.match(new RegExp("(?:cache\\s*read(?:\\s+input)?(?:\\s+tokens?)?|cached(?:\\s+input)?(?:\\s+tokens?)?|缓存命中(?:\\s*token|\\s*tokens|\\s*输入)?|命中缓存)\\s*[:：=]?\\s*" + numPat, "i"));
    const mCacheWrite = text.match(new RegExp("(?:cache\\s*(?:write|creation)(?:\\s+tokens?)?|缓存写入)\\s*[:：=]?\\s*" + numPat, "i"));
    const mOut = text.match(new RegExp("(?:total\\s+output(?:\\s+tokens?)?|completion\\s+tokens?|\\boutput(?:\\s+tokens?)?|输出\\s*(?:token|tokens)?)\\s*[:：=]?\\s*" + numPat, "i"));
    const mReason = text.match(new RegExp("(?:reasoning\\s+tokens?|思考\\s*(?:token|tokens)?)\\s*[:：=]?\\s*" + numPat, "i"));
    const mReq = text.match(new RegExp("(?:total\\s+requests?|api\\s+calls?|total\\s+calls?|\\brequests?|\\bturns?|调用(?:次数|量)?|请求(?:次数|数)?)\\s*[:：=]?\\s*" + numPat, "i"));

    const rawInVal = mIn ? parseScaledNumber(mIn[1]) : 0;
    const cacheReadVal = mCacheRead ? parseScaledNumber(mCacheRead[1]) : 0;
    const cacheWriteVal = mCacheWrite ? parseScaledNumber(mCacheWrite[1]) : 0;
    totalOutput = mOut ? parseScaledNumber(mOut[1]) : 0;

    const isClaudeCodeStyle = /cache\s*read/i.test(text) && !/total\s+input/i.test(text);
    if (isClaudeCodeStyle) {
      detectedFormat = "claude_code_cost";
      totalInput = rawInVal + cacheReadVal + cacheWriteVal;
      cachedInput = cacheReadVal;
    } else if (rawInVal >= cacheReadVal && rawInVal > 0) {
      totalInput = rawInVal;
      cachedInput = cacheReadVal;
    } else {
      totalInput = rawInVal + cacheReadVal + cacheWriteVal;
      cachedInput = cacheReadVal;
    }
    if (mReason && parseScaledNumber(mReason[1]) > 0) outputIncludesReasoning = true;
    if (mReq) explicitRequests = parseScaledNumber(mReq[1]);
  }

  if (totalInput <= 0 && totalOutput <= 0) {
    throw new Error("Unable to find input/output token counts in usage_snippet");
  }
  cachedInput = Math.min(totalInput, Math.max(0, cachedInput));
  const cacheHitRate = totalInput > 0 ? Math.round((cachedInput / totalInput) * 10000) / 10000 : 0;

  let callsEstimated = false;
  let estTotalCalls = 1;
  let dailyRequests = 1;
  if (explicitDailyRequests !== null && explicitDailyRequests > 0) {
    dailyRequests = Math.max(1, Math.round(explicitDailyRequests));
    estTotalCalls = Math.max(1, explicitDailyRequests * days);
  } else if (explicitRequests !== null && explicitRequests > 0) {
    estTotalCalls = Math.max(1, explicitRequests);
    dailyRequests = Math.max(1, Math.round(estTotalCalls / days));
  } else {
    callsEstimated = true;
    const denom = Math.max(200, Math.round(defaultTokensPerCall || 4000));
    estTotalCalls = Math.max(1, totalInput > 0 ? Math.round(totalInput / denom) : Math.round(totalOutput / 800));
    dailyRequests = Math.max(1, Math.round(estTotalCalls / days));
  }

  const avgInputTokens = totalInput > 0 ? Math.max(1, Math.round(totalInput / estTotalCalls)) : 1500;
  const avgOutputTokens = totalOutput > 0 ? Math.max(1, Math.round(totalOutput / estTotalCalls)) : 500;
  const monthlyInputM = Math.round((((totalInput / days) * 30) / 1e6) * 1e6) / 1e6;
  const monthlyOutputM = Math.round((((totalOutput / days) * 30) / 1e6) * 1e6) / 1e6;

  return {
    detected_format: detectedFormat,
    days_observed: days,
    total_input_tokens: Math.round(totalInput),
    cached_input_tokens: Math.round(cachedInput),
    total_output_tokens: Math.round(totalOutput),
    monthly_input_m: monthlyInputM,
    monthly_output_m: monthlyOutputM,
    daily_requests: dailyRequests,
    avg_input_tokens: avgInputTokens,
    avg_output_tokens: avgOutputTokens,
    cache_hit_rate: cacheHitRate,
    output_includes_reasoning: outputIncludesReasoning,
    calls_estimated: callsEstimated,
  };
}

export function resolveCatalogModel(models, rawId) {
  const raw = String(rawId || "").trim();
  if (!raw) return null;
  const exact = models.find((item) => item.id === raw);
  if (exact) return exact;

  const normalized = raw
    .replace(/^aliyun\//i, "aliyun-bailian/")
    .replace(/^tencent\//i, "tencent-cloud/")
    .toLowerCase();

  const ciExact = models.find((item) => String(item.id || "").toLowerCase() === normalized);
  if (ciExact) return ciExact;

  const rawLower = raw.toLowerCase();
  const suffixMatches = models.filter((item) => {
    const idLower = String(item.id || "").toLowerCase();
    const apiLower = String(item.api_model_id || "").toLowerCase();
    return apiLower === rawLower || idLower.endsWith("/" + rawLower);
  });
  if (suffixMatches.length > 0) {
    suffixMatches.sort((a, b) => {
      const aCn = a.region === "cn_direct" ? 1 : 0;
      const bCn = b.region === "cn_direct" ? 1 : 0;
      if (aCn !== bCn) return bCn - aCn;
      const aPaid = a.is_free ? 0 : 1;
      const bPaid = b.is_free ? 0 : 1;
      if (aPaid !== bPaid) return bPaid - aPaid;
      return (Number(b.value_score) || 0) - (Number(a.value_score) || 0);
    });
    return suffixMatches[0];
  }
  return null;
}

export function planCoversModel(plan, model) {
  if (!plan || plan.offer_type !== "subscription" || !model) return false;
  const text = `${model.id || ""} ${model.api_model_id || ""} ${model.name || ""}`.toLowerCase();
  const cov = (plan.models_covered || []).map((x) => String(x).toLowerCase()).join(" ");
  if (text.includes("qwen") && cov.includes("qwen")) return true;
  if ((text.includes("hunyuan") || text.includes("tc-code")) && (cov.includes("hunyuan") || cov.includes("tc-code"))) return true;
  if (text.includes("doubao") && cov.includes("doubao")) return true;
  if (text.includes("kimi") && cov.includes("kimi")) return true;
  if (text.includes("glm") && cov.includes("glm")) return true;
  if (text.includes("minimax") && cov.includes("minimax")) return true;
  if ((text.includes("deepseek-v3") || text.includes("deepseek-chat")) && cov.includes("deepseek-v3")) return true;
  return false;
}

export function resolveModelFuzzy(models, rawId) {
  const strict = resolveCatalogModel(models, rawId);
  if (strict) return strict;
  if (!models || models.length === 0) return null;
  const raw = String(rawId || "deepseek-v3").trim().toLowerCase();
  const stripped = raw.replace(/-(?:20\d{2}-\d{2}-\d{2}|20\d{6}|\d{4})$/, "");
  const slugBase = stripped.split("/").slice(-1)[0];
  const aliasCands = [];
  if (stripped !== raw) aliasCands.push(stripped, slugBase);
  if (slugBase === "deepseek-reasoner" || slugBase === "r1") aliasCands.push("deepseek-r1");
  else if (slugBase === "deepseek-chat" || slugBase === "v3") aliasCands.push("deepseek-v3");
  else if (["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano", "o1-mini", "o3-mini", "o4-mini"].includes(slugBase)) {
    aliasCands.push("openai/gpt-5.4-mini", "openai/gpt-5-mini");
  } else if (slugBase.startsWith("gpt-4") || slugBase.startsWith("chatgpt-4o") || ["o1", "o3", "o3-pro"].includes(slugBase)) {
    aliasCands.push("openai/gpt-5.4", "openai/gpt-5.5");
  } else if (slugBase.includes("claude") && slugBase.includes("sonnet")) {
    aliasCands.push("anthropic/claude-sonnet-5.5", "anthropic/claude-sonnet-5");
  } else if (slugBase.includes("claude") && slugBase.includes("opus")) {
    aliasCands.push("anthropic/claude-opus-5.5", "anthropic/claude-opus-5");
  } else if (slugBase.includes("claude") && slugBase.includes("haiku")) {
    aliasCands.push("anthropic/claude-haiku-5.5");
  }
  for (const ca of aliasCands) {
    const hit = resolveCatalogModel(models, ca);
    if (hit) return hit;
  }

  const wantsFree = raw.includes("free");
  const qTokens = raw.replace(/[/-]/g, " ").split(/\s+/).filter(Boolean);
  let best = null;
  let bestRank = -1;
  for (const m of models) {
    const mid = String(m.id || "").toLowerCase();
    const apiMid = String(m.api_model_id || "").toLowerCase();
    const mname = String(m.name || "").toLowerCase();
    const hay = `${mid} ${apiMid} ${mname} ${String(m.provider || "").toLowerCase()}`;
    let score = 0;
    if (mid.includes(raw) || (apiMid && apiMid.includes(raw))) score = 700;
    else if (mname.includes(raw)) score = 600;
    else if (qTokens.length > 0 && qTokens.every((tok) => hay.includes(tok))) score = 500;
    else if (qTokens.length > 0) {
      const overlap = qTokens.filter((tok) => hay.includes(tok)).length;
      if (overlap > 0) score = overlap * 120;
    }
    if (score > 0) {
      if (!wantsFree && m.is_free) score -= 50;
      score += (Number(m.value_score) || 0) * 0.1;
      if (score > bestRank) {
        bestRank = score;
        best = m;
      }
    }
  }
  return best || models[0];
}

function resolveModelEnvKeyVar(model) {
  const pkey = String(model?.provider_config_key || "").toLowerCase();
  const base = String(model?.api_base_url || "").toLowerCase();
  if (pkey === "aliyun_bailian_url" || base.includes("dashscope.aliyuncs.com")) return "DASHSCOPE_API_KEY";
  if (pkey === "tencent_cps_url" || base.includes("lkeap.cloud.tencent.com")) return "TENCENT_LKEAP_API_KEY";
  if (pkey === "volcengine_ark_url" || base.includes("volces.com")) return "VOLCENGINE_ARK_API_KEY";
  if (pkey === "siliconflow_invite_url" || base.includes("siliconflow.cn")) return "SILICONFLOW_API_KEY";
  return "OPENROUTER_API_KEY";
}

function resolveModelApiBase(model) {
  const base = String(model?.api_base_url || "").trim();
  if (base) return base;
  return model?.region === "global" ? "https://openrouter.ai/api/v1" : "https://dashscope.aliyuncs.com/compatible-mode/v1";
}

function findSameFamilyCnCandidates(rawModelName, workhorses) {
  const rawLow = String(rawModelName || "").toLowerCase();
  if (rawLow.includes("deepseek-r1") || rawLow.includes("deepseek-reasoner") || rawLow.endsWith("/r1")) {
    return workhorses.filter((c) => String(c.id || "").toLowerCase().includes("deepseek-r1"));
  }
  if (rawLow.includes("deepseek-v3") || rawLow.includes("deepseek-chat")) {
    return workhorses.filter((c) => String(c.id || "").toLowerCase().includes("deepseek-v3"));
  }
  if (rawLow.includes("qwen3-coder") || rawLow.includes("qwen-coder")) {
    return workhorses.filter((c) => {
      const idLow = String(c.id || "").toLowerCase();
      return idLow.includes("qwen") && idLow.includes("coder");
    });
  }
  if (rawLow.includes("qwen")) return workhorses.filter((c) => String(c.id || "").toLowerCase().includes("qwen"));
  if (rawLow.includes("glm")) return workhorses.filter((c) => String(c.id || "").toLowerCase().includes("glm"));
  if (rawLow.includes("kimi") || rawLow.includes("moonshot")) return workhorses.filter((c) => String(c.id || "").toLowerCase().includes("kimi"));
  if (rawLow.includes("minimax")) return workhorses.filter((c) => String(c.id || "").toLowerCase().includes("minimax"));
  if (rawLow.includes("doubao")) return workhorses.filter((c) => String(c.id || "").toLowerCase().includes("doubao"));
  if (rawLow.includes("hunyuan")) return workhorses.filter((c) => String(c.id || "").toLowerCase().includes("hunyuan"));
  return [];
}

export function buildBillMigrationLiteLlmConfig(lineItems) {
  const yamlLines = [
    "# AI Cost Radar — Zero-Code Multi-Model Bill Migration (LiteLLM Proxy)",
    "# Compliance: Use standard Pay-As-You-Go API keys ONLY (NEVER use sk-sp- Coding Plan keys).",
    "model_list:",
  ];
  const requiredEnvVars = [];
  for (const item of lineItems) {
    const aliasEsc = String(item.raw_model || "default").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
    const apiMid = String(item.recommended_api_model_id || item.recommended_model_id || "deepseek-v3");
    const apiBase = String(item.recommended_api_base_url || "https://dashscope.aliyuncs.com/compatible-mode/v1");
    const envVar = String(item.recommended_env_key_var || "DASHSCOPE_API_KEY");
    if (!requiredEnvVars.includes(envVar)) requiredEnvVars.push(envVar);
    yamlLines.push(
      `  - model_name: "${aliasEsc}"`,
      "    litellm_params:",
      `      model: openai/${apiMid}`,
      `      api_base: ${apiBase}`,
      `      api_key: os.environ/${envVar}`
    );
  }
  yamlLines.push(
    "",
    "router_settings:",
    "  routing_strategy: simple-shuffle",
    "  num_retries: 2",
    "  timeout: 60"
  );
  const envLines = requiredEnvVars.map(
    (v) => `export ${v}="sk-your-${v.toLowerCase().replace("_api_key", "")}-payg-key"`
  );
  envLines.push(
    'export LITELLM_MASTER_KEY="sk-local-bill-migration-proxy"',
    "",
    "# 启动本地零改代码迁移网关（业务代码无需改 model 名，仅需设 OPENAI_BASE_URL=http://127.0.0.1:4000/v1）",
    "uvx --from 'litellm[proxy]' litellm --config config.yaml --port 4000"
  );
  const probeModel = String(lineItems[0]?.raw_model || "deepseek-v3").replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  const smokeTestCmd =
    `curl -fsS "http://127.0.0.1:4000/v1/chat/completions" ` +
    `-H "Authorization: Bearer sk-local-bill-migration-proxy" ` +
    `-H "Content-Type: application/json" ` +
    `-d '{"model":"${probeModel}","max_tokens":1,"messages":[{"role":"user","content":"ping"}]}'`;

  return {
    config_yaml: yamlLines.join("\n"),
    env_snippet: envLines.join("\n"),
    smoke_test_cmd: smokeTestCmd,
    required_env_vars: requiredEnvVars,
    distinct_providers_count: requiredEnvVars.length,
    compliance_warning_zh:
      "合规红线：此网关配置仅限填入各厂商标准「按量付费 API Key」（sk-...）；严禁将个人 Coding Plan 包月专属密钥（sk-sp-...）填入 LiteLLM 网关或团队共享服务。",
  };
}

export function auditCsvBill(catalog, parsedSummary, {usageMode = "interactive_ide", teamSize = 1} = {}) {
  const models = catalog.models || [];
  const days = Number(parsedSummary.days_observed || 30);
  const scale30d = 30 / days;
  const seats = Math.max(1, Math.min(50, Math.round(Number(teamSize) || 1)));
  const round2 = (v) => Math.round((v + Number.EPSILON) * 100) / 100;

  const workhorses = models.filter((m) => {
    if (m.region !== "cn_direct" || m.is_free) return false;
    if ((Number(m.context_length) || 0) < 64000) return false;
    const midLow = String(m.id || "").toLowerCase();
    return !["7b", "8b", "lite", "turbo", "mini", "flash"].some((tok) => midLow.includes(tok));
  });

  const lineItems = [];
  let hasGlobalClosed = false;

  for (const grp of parsedSummary.model_breakdown || []) {
    const rawModel = String(grp.model || "unknown");
    const rawLow = rawModel.toLowerCase();
    const mReqs = Math.max(1, Math.round(Number(grp.requests || 0) * scale30d));
    const mInM = (Number(grp.input_tokens || 0) * scale30d) / 1e6;
    const mOutM = (Number(grp.output_tokens || 0) * scale30d) / 1e6;
    const hitRate = Number(grp.cache_hit_rate || 0);
    const reportedMonthlyRmb = round2(Number(grp.reported_cost_rmb || 0) * scale30d);

    const matched = resolveModelFuzzy(models, rawModel);
    if (!matched) continue;
    const matchedIdLow = String(matched.id || "").toLowerCase();
    if (
      matched.region === "global" &&
      ["anthropic", "claude", "openai", "gpt-", "o1", "o3", "o4", "google", "gemini", "x-ai", "grok"].some(
        (v) => rawLow.includes(v) || matchedIdLow.includes(v)
      )
    ) {
      hasGlobalClosed = true;
    }

    const mFactor = matched.cache_hit_factor ?? (matched.region === "cn_direct" ? 0.2 : 0.5);
    const catalogPaygRmb = round2(
      mInM * ((1 - hitRate) + hitRate * mFactor) * Number(matched.input_rmb_per_1m || 0) +
      mOutM * Number(matched.output_rmb_per_1m || 0)
    );
    const baselineRmb = reportedMonthlyRmb > 0 ? reportedMonthlyRmb : catalogPaygRmb;

    const needsReasoning = Boolean(
      grp.output_includes_reasoning ||
      ["-r1", "/r1", "deepseek-r1", "o1", "o3", "o4", "qwq", "hunyuan-t1", "thinking", "reasoner"].some((k) => rawLow.includes(k))
    );
    const reqTag = needsReasoning ? "reasoning" : "coding";
    const taggedPool = workhorses.filter((c) => (c.tags || []).includes(reqTag));
    const pool = taggedPool.length > 0 ? taggedPool : workhorses;

    let bestCand = null;
    let bestCandRmb = baselineRmb;
    let bestCandScore = -1;
    for (const cand of pool) {
      const cFactor = cand.cache_hit_factor ?? 0.2;
      const cRmb = round2(
        mInM * ((1 - hitRate) + hitRate * cFactor) * Number(cand.input_rmb_per_1m || 0) +
        mOutM * Number(cand.output_rmb_per_1m || 0)
      );
      const cScore = Number(cand.value_score || 0);
      if (!bestCand || cRmb < bestCandRmb || (cRmb === bestCandRmb && cScore > bestCandScore)) {
        bestCand = cand;
        bestCandRmb = cRmb;
        bestCandScore = cScore;
      }
    }

    const sameFamPool = findSameFamilyCnCandidates(rawModel, workhorses);
    let sameFamBest = null;
    let sameFamRmb = null;
    let sameFamScore = -1;
    for (const sfCand of sameFamPool) {
      const sfFactor = sfCand.cache_hit_factor ?? 0.2;
      const sfCost = round2(
        mInM * ((1 - hitRate) + hitRate * sfFactor) * Number(sfCand.input_rmb_per_1m || 0) +
        mOutM * Number(sfCand.output_rmb_per_1m || 0)
      );
      const sfScore = Number(sfCand.value_score || 0);
      if (!sameFamBest || sfCost < sameFamRmb || (sfCost === sameFamRmb && sfScore > sameFamScore)) {
        sameFamBest = sfCand;
        sameFamRmb = sfCost;
        sameFamScore = sfScore;
      }
    }

    const recModel = bestCand && bestCandRmb < baselineRmb - 0.005 ? bestCand : matched;
    const optRmb = bestCand && bestCandRmb < baselineRmb - 0.005 ? round2(bestCandRmb) : round2(baselineRmb);
    const action = bestCand && bestCandRmb < baselineRmb - 0.005 ? "switch_cn_direct" : "keep_current";
    const savRmb = round2(Math.max(0, baselineRmb - optRmb));
    const savPct = baselineRmb > 0 ? Math.round(((savRmb / baselineRmb) * 100) * 10) / 10 : 0;

    lineItems.push({
      raw_model: rawModel,
      matched_model_id: matched.id,
      matched_model_name: matched.name,
      monthly_requests: mReqs,
      monthly_input_m: Math.round(mInM * 10000) / 10000,
      monthly_output_m: Math.round(mOutM * 10000) / 10000,
      cache_hit_rate: hitRate,
      reported_monthly_rmb: reportedMonthlyRmb,
      catalog_payg_rmb: catalogPaygRmb,
      baseline_monthly_rmb: round2(baselineRmb),
      recommended_model_id: recModel.id,
      recommended_model_name: recModel.name,
      recommended_api_model_id: String(recModel.api_model_id || recModel.id),
      recommended_api_base_url: resolveModelApiBase(recModel),
      recommended_env_key_var: resolveModelEnvKeyVar(recModel),
      recommended_signup_url: recModel.signup_url || recModel.affiliate_url || "",
      same_family_cn_model_id: sameFamBest ? sameFamBest.id : null,
      same_family_cn_model_name: sameFamBest ? sameFamBest.name : null,
      same_family_cn_api_model_id: sameFamBest ? String(sameFamBest.api_model_id || sameFamBest.id) : null,
      same_family_cn_api_base_url: sameFamBest ? resolveModelApiBase(sameFamBest) : null,
      same_family_cn_env_key_var: sameFamBest ? resolveModelEnvKeyVar(sameFamBest) : null,
      same_family_cn_monthly_rmb: sameFamRmb,
      optimized_payg_rmb: optRmb,
      savings_rmb: savRmb,
      savings_pct: savPct,
      action,
    });
  }

  const totalMReqs = lineItems.reduce((acc, x) => acc + x.monthly_requests, 0);
  const totalBaseRmb = round2(lineItems.reduce((acc, x) => acc + x.baseline_monthly_rmb, 0));
  const totalCatRmb = round2(lineItems.reduce((acc, x) => acc + x.catalog_payg_rmb, 0));
  const totalOptRmb = round2(lineItems.reduce((acc, x) => acc + x.optimized_payg_rmb, 0));
  const totalSavRmb = round2(Math.max(0, totalBaseRmb - totalOptRmb));
  const totalSavPct = totalBaseRmb > 0 ? Math.round(((totalSavRmb / totalBaseRmb) * 100) * 10) / 10 : 0;

  let codingPlanOption = null;
  if (usageMode === "interactive_ide") {
    const subOffers = (catalog.coding_plans || []).filter((p) => p.offer_type === "subscription");
    if (subOffers.length > 0) {
      const fitsLite = totalMReqs <= 18000 * seats;
      const fitsPro = totalMReqs <= 90000 * seats;
      const targetId = fitsLite ? "tencent-coding-plan" : "aliyun-coding-plan";
      const chosenOffer = subOffers.find((o) => o.id === targetId) || subOffers[0];
      const tierId = fitsLite && (chosenOffer.tiers || []).some((t) => t.tier_id === "lite" && t.purchasable) ? "lite" : "pro";
      const chosenTier = (chosenOffer.tiers || []).find((t) => t.tier_id === tierId) || (chosenOffer.tiers || []).slice(-1)[0];
      const unitRenew = Number(chosenTier?.renewal_rmb || 200);
      const unitFirst = chosenTier?.first_month_rmb != null ? Number(chosenTier.first_month_rmb) : unitRenew;
      const firstRmb = round2(unitFirst * seats);
      const renewRmb = round2(unitRenew * seats);
      const capMonthly = Number(chosenTier?.quota_monthly || 90000) * seats;
      const hasCrossCaveat = Boolean(
        hasGlobalClosed ||
        lineItems.some((it) => {
          const mObj = models.find((m) => m.id === it.matched_model_id);
          return !planCoversModel(chosenOffer, mObj);
        })
      );
      codingPlanOption = {
        plan_id: chosenOffer.id,
        plan_name: chosenOffer.name,
        official_source_url: chosenOffer.official_source_url || "",
        team_size: seats,
        tier_id: tierId,
        tier_name: chosenTier?.name || "Pro",
        fits_monthly_cap: fitsPro,
        combined_monthly_cap: capMonthly,
        first_month_rmb: firstRmb,
        renewal_rmb: renewRmb,
        vs_baseline_renewal_savings_rmb: fitsPro ? round2(totalBaseRmb - renewRmb) : null,
        cheaper_than_optimized_payg_on_renewal: Boolean(fitsPro && renewRmb < totalOptRmb),
        has_cross_model_caveat: hasCrossCaveat,
        caveat_zh: hasCrossCaveat
          ? "原账单含 Claude/GPT 等海外闭源或非套餐同系模型；国内 Coding Plan 仅覆盖千问/混元/豆包/Kimi/GLM/MiniMax/DeepSeek-V3，切换前请先评估代码质量差异。"
          : "原账单模型均在国内 Coding Plan 覆盖体系内。",
      };
    }
  }

  return {
    days_observed: days,
    usage_mode: usageMode,
    team_size: seats,
    line_items: lineItems,
    totals: {
      distinct_models_count: lineItems.length,
      monthly_requests: totalMReqs,
      baseline_monthly_rmb: totalBaseRmb,
      catalog_payg_monthly_rmb: totalCatRmb,
      optimized_payg_monthly_rmb: totalOptRmb,
      payg_savings_rmb: totalSavRmb,
      payg_savings_pct: totalSavPct,
      has_global_closed_models: hasGlobalClosed,
    },
    coding_plan_option: codingPlanOption,
    migration_litellm_config: buildBillMigrationLiteLlmConfig(lineItems),
  };
}

export function calculateBudget(catalog, params) {
  let daily = number(params, "daily_requests", 1000, 1000000);
  let input = number(params, "avg_input_tokens", 1500, 10000000);
  let output = number(params, "avg_output_tokens", 500, 10000000);
  let hit = number(params, "cache_hit_rate", 0, 1);
  const multiplier = number(params, "reasoning_multiplier", 1, 10);
  if (multiplier < 1) throw new Error("reasoning_multiplier must be at least 1");
  const incRaw = params.get("output_includes_reasoning") ?? "false";
  if (!["true", "false"].includes(incRaw)) throw new Error("Invalid output_includes_reasoning");
  let includesReasoning = incRaw === "true";
  const mode = params.get("usage_mode") || "interactive_ide";
  if (!["interactive_ide", "automated_backend"].includes(mode)) throw new Error("Invalid usage_mode");
  const peak = params.has("peak_5h_calls") ? number(params, "peak_5h_calls", 0, 10000000) : null;
  const seats = number(params, "team_size", 1, 50);
  if (seats < 1 || !Number.isInteger(seats)) throw new Error("Invalid team_size");
  if (![daily, input, output, ...(peak === null ? [] : [peak])].every(Number.isInteger)) throw new Error("Request and token counts must be integers");

  let explicitMonthlyRequests = null;
  let exactMonthlyInputM = null;
  let exactMonthlyOutputM = null;
  let parsedUsageSummary = null;
  let billAudit = null;

  if (params.has("usage_snippet") || params.has("usage_snippets")) {
    const daysObs = params.has("days_observed") ? number(params, "days_observed", 30, 365) : 30;
    const fxRate = Number(catalog.fx_rate_usd_to_rmb || 7.2);
    const repeatedSnippets = params.getAll("usage_snippet");
    let jsonArraySnippets = [];
    if (params.has("usage_snippets")) {
      let parsedArr;
      try {
        parsedArr = JSON.parse(params.get("usage_snippets"));
      } catch {
        throw new Error("Invalid usage_snippets JSON array");
      }
      if (!Array.isArray(parsedArr)) throw new Error("Invalid usage_snippets JSON array");
      jsonArraySnippets = parsedArr.map((x) => String(x ?? ""));
    }
    const allSnippets = [...jsonArraySnippets, ...repeatedSnippets];
    if (allSnippets.length > 1 || params.has("usage_snippets")) {
      parsedUsageSummary = mergeUsageSnippets(allSnippets, daysObs, fxRate);
    } else {
      const rawSnippet = params.get("usage_snippet");
      parsedUsageSummary = parseUsageSnippet(rawSnippet, daysObs);
    }
    daily = parsedUsageSummary.daily_requests;
    input = parsedUsageSummary.avg_input_tokens;
    output = parsedUsageSummary.avg_output_tokens;
    hit = parsedUsageSummary.cache_hit_rate;
    exactMonthlyInputM = parsedUsageSummary.monthly_input_m;
    exactMonthlyOutputM = parsedUsageSummary.monthly_output_m;
    if (parsedUsageSummary.output_includes_reasoning) includesReasoning = true;
    if (parsedUsageSummary.detected_format === "csv_multimodel_bill") {
      explicitMonthlyRequests = parsedUsageSummary.monthly_requests;
      billAudit = auditCsvBill(catalog, parsedUsageSummary, {usageMode: mode, teamSize: seats});
    }
  } else if (
    params.has("monthly_requests") ||
    params.has("monthly_input_m") ||
    params.has("monthly_output_m") ||
    params.has("cached_input_m")
  ) {
    let mReqs;
    if (params.has("monthly_requests")) {
      mReqs = number(params, "monthly_requests", 0, 30000000);
      if (mReqs < 1 || !Number.isInteger(mReqs)) throw new Error("Invalid monthly_requests");
    } else if (params.has("monthly_input_m") && number(params, "monthly_input_m", 0, 10000000) > 0) {
      const tmpInM = number(params, "monthly_input_m", 0, 10000000);
      mReqs = Math.max(1, Math.round((tmpInM * 1000000) / Math.max(1, input)));
    } else {
      mReqs = Math.max(1, daily * 30);
    }
    const mInM = params.has("monthly_input_m") ? number(params, "monthly_input_m", 0, 10000000) : (mReqs * input) / 1000000;
    const mOutM = params.has("monthly_output_m") ? number(params, "monthly_output_m", 0, 10000000) : (mReqs * output) / 1000000;
    if (params.has("cached_input_m")) {
      const cInM = number(params, "cached_input_m", 0, 10000000);
      if ((mInM > 0 && cInM > mInM) || (mInM === 0 && cInM > 0)) throw new Error("Invalid cached_input_m");
      hit = mInM > 0 ? Math.round((cInM / mInM) * 10000) / 10000 : 0;
    }
    explicitMonthlyRequests = mReqs;
    exactMonthlyInputM = mInM;
    exactMonthlyOutputM = mOutM;
    daily = Math.max(1, mReqs % 30 !== 0 ? Math.ceil(mReqs / 30) : mReqs / 30);
    input = Math.max(0, Math.round((mInM * 1000000) / mReqs));
    output = Math.max(0, Math.round((mOutM * 1000000) / mReqs));
    parsedUsageSummary = {
      detected_format: "monthly_bill_totals",
      monthly_requests: mReqs,
      monthly_input_m: Math.round(mInM * 1000000) / 1000000,
      monthly_output_m: Math.round(mOutM * 1000000) / 1000000,
      daily_requests: daily,
      avg_input_tokens: input,
      avg_output_tokens: output,
      cache_hit_rate: hit,
    };
  }

  let id = params.get("model_id");
  let model = null;
  if (
    parsedUsageSummary &&
    parsedUsageSummary.detected_format === "csv_multimodel_bill" &&
    (!id || id.trim().toLowerCase() === "auto")
  ) {
    const firstModel = parsedUsageSummary.model_breakdown?.[0]?.model || "deepseek-v3";
    model = resolveModelFuzzy(catalog.models || [], firstModel);
  } else {
    model = resolveCatalogModel(catalog.models || [], id);
  }
  if (!model) throw new Error("Unknown model_id; pass an id or api_model_id from /api/models_live.json");

  const monthly = explicitMonthlyRequests ?? (daily * 30);
  const perSeatMonthly = monthly > 0 ? Math.ceil(monthly / seats) : 0;
  const effectiveMultiplier = includesReasoning || !(model.tags || []).includes("reasoning") ? 1 : multiplier;
  const factor = model.cache_hit_factor ?? 1;
  const round = (value) => Math.round((value + Number.EPSILON) * 1000000) / 1000000;
  const monthlyInM = exactMonthlyInputM ?? ((monthly * input) / 1000000);
  const monthlyOutM = exactMonthlyOutputM ?? ((monthly * output) / 1000000);
  const bill = (currency) => {
    const inputCost = monthlyInM * model[`input_${currency}_per_1m`] * (1 - hit + hit * factor);
    const outputCost = monthlyOutM * model[`output_${currency}_per_1m`] * effectiveMultiplier;
    return {input_cost: round(inputCost), output_cost: round(outputCost), total_cost: round(inputCost + outputCost)};
  };
  const rmb = bill("rmb");
  const usd = bill("usd");
  const plans = (catalog.coding_plans || []).filter((plan) => plan.offer_type === "subscription").map((plan) => {
    const coversSelectedModel = planCoversModel(plan, model);
    const tiers = (plan.tiers || []).map((tier) => {
      const capMonthly = tier.quota_monthly * seats;
      const capWeekly = tier.quota_weekly * seats;
      const cap5h = tier.quota_5h * seats;
      const monthlyFits = monthly <= capMonthly;
      const averageWeekFits = daily * 7 <= capWeekly;
      const peakFits = peak === null ? null : peak <= cap5h;
      const basicFits = tier.purchasable && mode === "interactive_ide" && monthlyFits && averageWeekFits;
      const eligible = basicFits ? peakFits : false;
      const effectiveFirstRmb = round((tier.first_month_rmb ?? tier.renewal_rmb) * seats);
      const totalRenewalRmb = round(tier.renewal_rmb * seats);
      return {
        ...tier,
        seats_count: seats,
        combined_quota_monthly: capMonthly,
        combined_quota_weekly: capWeekly,
        combined_quota_5h: cap5h,
        total_first_month_rmb: effectiveFirstRmb,
        total_renewal_rmb: totalRenewalRmb,
        monthly_fits: monthlyFits,
        estimated_week_fits: averageWeekFits,
        peak_5h_fits: peakFits,
        eligible_by_provided_usage: eligible,
        excess_monthly_requests: Math.max(0, monthly - capMonthly),
        first_month_saving_rmb: eligible ? round(rmb.total_cost - effectiveFirstRmb) : null,
        renewal_saving_rmb: eligible ? round(rmb.total_cost - totalRenewalRmb) : null,
        estimated_first_month_saving_rmb: basicFits ? round(rmb.total_cost - effectiveFirstRmb) : null,
        estimated_renewal_saving_rmb: basicFits ? round(rmb.total_cost - totalRenewalRmb) : null,
      };
    });
    const proTier = (plan.tiers || []).find((t) => t.tier_id === "pro" && t.purchasable)
      || (plan.tiers || []).filter((t) => t.purchasable).slice(-1)[0]
      || null;
    let overflowHybrid = null;
    if (
      proTier &&
      mode === "interactive_ide" &&
      monthly > proTier.quota_monthly * seats &&
      (peak === null || peak <= proTier.quota_5h * seats)
    ) {
      const coveredCalls = proTier.quota_monthly * seats;
      const overflowCalls = monthly - coveredCalls;
      const overflowPaygRmb = Math.round((rmb.total_cost * (overflowCalls / monthly) + Number.EPSILON) * 100) / 100;
      const firstPlanRmb = Math.round(((proTier.first_month_rmb ?? proTier.renewal_rmb) * seats + Number.EPSILON) * 100) / 100;
      const renewalPlanRmb = Math.round((proTier.renewal_rmb * seats + Number.EPSILON) * 100) / 100;
      const firstTotalRmb = Math.round((firstPlanRmb + overflowPaygRmb + Number.EPSILON) * 100) / 100;
      const renewalTotalRmb = Math.round((renewalPlanRmb + overflowPaygRmb + Number.EPSILON) * 100) / 100;
      const firstSavingRmb = Math.round((rmb.total_cost - firstTotalRmb + Number.EPSILON) * 100) / 100;
      const renewalSavingRmb = Math.round((rmb.total_cost - renewalTotalRmb + Number.EPSILON) * 100) / 100;
      overflowHybrid = {
        seats_count: seats,
        covered_calls: coveredCalls,
        overflow_calls: overflowCalls,
        overflow_payg_rmb: overflowPaygRmb,
        first_month_plan_rmb: firstPlanRmb,
        renewal_plan_rmb: renewalPlanRmb,
        first_month_total_rmb: firstTotalRmb,
        renewal_total_rmb: renewalTotalRmb,
        first_month_saving_rmb: firstSavingRmb,
        renewal_saving_rmb: renewalSavingRmb,
        saves_on_renewal: renewalSavingRmb > 0,
      };
    }
    return {
      id: plan.id,
      name: plan.name,
      featured_partner: Boolean(plan.featured_partner),
      covers_selected_model: coversSelectedModel,
      official_source_url: plan.official_source_url,
      models_covered: plan.models_covered,
      interactive_only: plan.interactive_only,
      endpoints: plan.endpoints,
      seats_count: seats,
      overflow_hybrid: overflowHybrid,
      tiers,
    };
  });
  const sameFamilyCandidates = [];
  const overflowHybridCandidates = [];
  for (const plan of plans) {
    if (!plan.covers_selected_model) continue;
    const matchedTier = plan.tiers.find(
      (tier) => tier.purchasable && mode === "interactive_ide" && tier.monthly_fits && tier.estimated_week_fits && tier.peak_5h_fits !== false
    );
    if (matchedTier) {
      const renewalSaving = round(rmb.total_cost - matchedTier.total_renewal_rmb);
      if (renewalSaving > 0) {
        sameFamilyCandidates.push({id: plan.id, renewalSaving, featured: plan.featured_partner ? 1 : 0});
      }
    }
    if (plan.overflow_hybrid && plan.overflow_hybrid.saves_on_renewal) {
      overflowHybridCandidates.push({
        id: plan.id,
        name: plan.name,
        hybrid: plan.overflow_hybrid,
        featured: plan.featured_partner ? 1 : 0,
      });
    }
  }
  sameFamilyCandidates.sort((a, b) => (b.renewalSaving - a.renewalSaving) || (b.featured - a.featured));
  const recommendedSameFamilyPlanId = sameFamilyCandidates.length > 0 ? sameFamilyCandidates[0].id : null;
  overflowHybridCandidates.sort(
    (a, b) =>
      (b.hybrid.renewal_saving_rmb - a.hybrid.renewal_saving_rmb) ||
      (b.hybrid.first_month_saving_rmb - a.hybrid.first_month_saving_rmb) ||
      (b.featured - a.featured)
  );
  const bestHybrid = overflowHybridCandidates.length > 0 ? overflowHybridCandidates[0] : null;
  const recommendedOverflowHybridPlanId = bestHybrid ? bestHybrid.id : null;
  const totalProCap = 90000 * seats;
  const totalPro5hCap = 6000 * seats;
  let summary = seats > 1
    ? `按 ${seats} 人团队 30 天预计合计 ${monthly} 次（人均约 ${perSeatMonthly} 次），共享按量月费约 ¥${rmb.total_cost.toFixed(2)}。`
    : `按 30 天预计 ${monthly} 次，按量月费约 ¥${rmb.total_cost.toFixed(2)}。`;
  if (mode === "automated_backend") summary += "自动化后端不适用 Coding Plan。";
  else if (monthly > totalProCap) {
    summary += seats > 1
      ? `超出 ${seats} 席 Pro 合计月额度 ${monthly - totalProCap} 次；不能按 ¥${200 * seats} 封顶。`
      : `超出 Pro 月额度 ${monthly - 90000} 次；不能按 ¥200 封顶。`;
    if (bestHybrid) {
      summary += `可采用「${seats} 份 Pro 打底前 ${bestHybrid.hybrid.covered_calls} 次＋超额 ${bestHybrid.hybrid.overflow_calls} 次按量」组合（首月约 ¥${bestHybrid.hybrid.first_month_total_rmb.toFixed(2)}，续费约 ¥${bestHybrid.hybrid.renewal_total_rmb.toFixed(2)}，净省 ¥${bestHybrid.hybrid.renewal_saving_rmb.toFixed(2)}/月）。`;
    } else {
      summary += "当前模型单价较低，全程纯按量 API 比「Pro＋溢出按量」更划算。";
    }
  }
  else if (peak !== null && peak > totalPro5hCap) summary += `超出 ${seats > 1 ? seats + " 席合计 " : ""}Pro 的 5 小时 ${totalPro5hCap} 次窗口。`;
  else summary += (seats > 1 ? `${seats} 席独立 Pro 月额度足够；` : "Pro 月额度足够；") + (peak === null ? "5 小时峰值待确认。" : "仍需核对真实每周集中用量。") ;
  summary += "套餐可用模型与按量模型未必相同；节省额仅为费用比较，非质量等价承诺。";
  const share = new URLSearchParams({
    calls: String(daily),
    in: String(input),
    out: String(output),
    cache: String(hit),
    reason: String(multiplier > 1 ? multiplier : 0),
    inc_cot: includesReasoning ? "1" : "0",
    mode,
    baseline: model.id,
    src: "coze",
    qv: catalog.quote_verified_date,
  });
  if (peak !== null) share.set("peak5h", String(peak));
  if (seats > 1) share.set("seats", String(seats));
  const outPayload = {status: "ok", summary_cn: summary, model_id: model.id, team_size: seats, per_seat_monthly_requests: perSeatMonthly, monthly_requests: monthly,
    monthly_rmb: rmb.total_cost, monthly_usd: usd.total_cost, input_cost_rmb: rmb.input_cost, output_cost_rmb: rmb.output_cost,
    cache_hit_rate: hit, effective_reasoning_multiplier: effectiveMultiplier,
    recommended_same_family_plan_id: recommendedSameFamilyPlanId,
    recommended_overflow_hybrid_plan_id: recommendedOverflowHybridPlanId,
    coding_plans: plans,
    quote_verified_date: catalog.quote_verified_date, last_live_verified_at: catalog.last_live_verified_at,
    web_calculator_url: `https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/?${share}`};
  if (parsedUsageSummary) outPayload.parsed_usage_summary = parsedUsageSummary;
  if (billAudit) outPayload.bill_audit = billAudit;
  return outPayload;
}

export async function onRequestGet({request, env}) {
  const json = (body, status = 200) => new Response(JSON.stringify(body), {status,
    headers: {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}});
  const response = await env.ASSETS.fetch(new URL("/api/models_live.json", request.url));
  if (!response.ok) return json({error: "Price catalog unavailable"}, 503);
  let catalog;
  try { catalog = await response.json(); }
  catch { return json({error: "Price catalog unavailable"}, 503); }
  try { return json(calculateBudget(catalog, new URL(request.url).searchParams)); }
  catch (error) { return json({error: error.message}, 400); }
}
