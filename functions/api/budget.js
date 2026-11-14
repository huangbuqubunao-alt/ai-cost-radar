// Public, stateless price arithmetic. Never calls a paid model API or records input.
function number(params, key, fallback, max) {
  const raw = params.get(key);
  const value = raw === null ? fallback : Number(raw);
  if (raw === "" || !Number.isFinite(value) || value < 0 || value > max) {
    throw new Error(`Invalid ${key}`);
  }
  return value;
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

export function calculateBudget(catalog, params) {
  const id = params.get("model_id");
  const model = resolveCatalogModel(catalog.models || [], id);
  if (!model) throw new Error("Unknown model_id; pass an id or api_model_id from /api/models_live.json");
  const daily = number(params, "daily_requests", 1000, 1000000);
  const input = number(params, "avg_input_tokens", 1500, 10000000);
  const output = number(params, "avg_output_tokens", 500, 10000000);
  const hit = number(params, "cache_hit_rate", 0, 1);
  const multiplier = number(params, "reasoning_multiplier", 1, 10);
  if (multiplier < 1) throw new Error("reasoning_multiplier must be at least 1");
  const incRaw = params.get("output_includes_reasoning") ?? "false";
  if (!["true", "false"].includes(incRaw)) throw new Error("Invalid output_includes_reasoning");
  const includesReasoning = incRaw === "true";
  const mode = params.get("usage_mode") || "interactive_ide";
  if (!["interactive_ide", "automated_backend"].includes(mode)) throw new Error("Invalid usage_mode");
  const peak = params.has("peak_5h_calls") ? number(params, "peak_5h_calls", 0, 10000000) : null;
  const seats = number(params, "team_size", 1, 50);
  if (seats < 1 || !Number.isInteger(seats)) throw new Error("Invalid team_size");
  if (![daily, input, output, ...(peak === null ? [] : [peak])].every(Number.isInteger)) throw new Error("Request and token counts must be integers");
  const monthly = daily * 30;
  const perSeatMonthly = monthly > 0 ? Math.ceil(monthly / seats) : 0;
  const effectiveMultiplier = includesReasoning || !(model.tags || []).includes("reasoning") ? 1 : multiplier;
  const factor = model.cache_hit_factor ?? 1;
  const round = (value) => Math.round((value + Number.EPSILON) * 1000000) / 1000000;
  const bill = (currency) => {
    const inputCost = monthly * input / 1000000 * model[`input_${currency}_per_1m`] * (1 - hit + hit * factor);
    const outputCost = monthly * output / 1000000 * model[`output_${currency}_per_1m`] * effectiveMultiplier;
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
  return {status: "ok", summary_cn: summary, model_id: model.id, team_size: seats, per_seat_monthly_requests: perSeatMonthly, monthly_requests: monthly,
    monthly_rmb: rmb.total_cost, monthly_usd: usd.total_cost, input_cost_rmb: rmb.input_cost, output_cost_rmb: rmb.output_cost,
    cache_hit_rate: hit, effective_reasoning_multiplier: effectiveMultiplier,
    recommended_same_family_plan_id: recommendedSameFamilyPlanId,
    recommended_overflow_hybrid_plan_id: recommendedOverflowHybridPlanId,
    coding_plans: plans,
    quote_verified_date: catalog.quote_verified_date, last_live_verified_at: catalog.last_live_verified_at,
    web_calculator_url: `https://ai-cost-radar-nlu.pages.dev/coding-plan-2026/?${share}`};
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
