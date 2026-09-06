const API = "/api/v1/demo";

const $ = (selector) => document.querySelector(selector);
const state = { file: null, snapshot: null, symbols: [] };

const currency = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  minimumFractionDigits: 2,
});

const compactCurrency = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  maximumFractionDigits: 0,
});

function finiteNumber(value, fallback = 0) {
  if (value && typeof value === "object") {
    const nested = firstDefined(value, ["amount", "value", "net", "percent"]);
    return nested === undefined ? fallback : finiteNumber(nested, fallback);
  }
  const parsed = typeof value === "string" ? Number(value.replace(/[%¥,]/g, "")) : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function firstDefined(source, keys, fallback = undefined) {
  for (const key of keys) {
    if (source?.[key] !== undefined && source[key] !== null) return source[key];
  }
  return fallback;
}

function formatDate(value) {
  if (!value) return "演示快照";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

async function request(path, options = {}) {
  const response = await fetch(`${API}${path}`, options);
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    try {
      const body = await response.json();
      message = body.detail?.message || body.detail || body.message || body.error || message;
    } catch (_) { /* Response is not JSON. */ }
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return response;
}

function setBusy(button, busy, busyText) {
  if (busy) {
    button.dataset.label = button.textContent;
    button.textContent = busyText;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
  } else {
    button.textContent = button.dataset.label || button.textContent;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  }
}

function showError(target, error) {
  target.textContent = error instanceof Error ? error.message : String(error);
  target.hidden = false;
}

function clearError(target) {
  target.textContent = "";
  target.hidden = true;
}

function setJourney(currentStep) {
  document.querySelectorAll("[data-step-indicator]").forEach((item) => {
    const step = Number(item.dataset.stepIndicator);
    item.classList.toggle("is-active", step === currentStep);
    item.classList.toggle("is-complete", step < currentStep);
  });
}

function selectFile(file) {
  const error = $("#import-error");
  clearError(error);
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".csv") && file.type !== "text/csv") {
    showError(error, "请选择 CSV 文件。为保护隐私，请只使用 synthetic / demo 数据。");
    return;
  }
  state.file = file;
  $("#file-label").textContent = file.name;
  $("#import-file").disabled = false;
  $("#import-status").textContent = `${Math.max(1, Math.round(file.size / 1024))} KB · 已就绪`;
}

async function loadDemo() {
  const button = $("#load-demo");
  clearError($("#import-error"));
  setBusy(button, true, "正在载入…");
  try {
    const response = await request("/sample-csv");
    let csv;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const body = await response.json();
      csv = body.csv || body.content || body.data;
    } else {
      csv = await response.text();
    }
    if (!csv) throw new Error("演示 CSV 内容为空。请确认 API 已加载 synthetic dataset。");
    selectFile(new File([csv], "wealthpilot-demo.csv", { type: "text/csv" }));
    await importSnapshot();
  } catch (error) {
    showError($("#import-error"), error);
  } finally {
    setBusy(button, false);
  }
}

function snapshotView(snapshot) {
  const assetsValue = firstDefined(snapshot, ["assets", "total_assets", "asset_total"]);
  const liabilitiesValue = firstDefined(snapshot, ["liabilities", "total_liabilities", "liability_total"]);
  const cashFlowValue = firstDefined(snapshot, ["cash_flow", "monthly_cash_flow", "net_cash_flow"], {});
  const assets = finiteNumber(assetsValue);
  const liabilities = finiteNumber(liabilitiesValue);
  const netWorth = finiteNumber(firstDefined(snapshot, ["net_worth", "netWorth"], assets - liabilities));
  const income = finiteNumber(firstDefined(
    snapshot,
    ["monthly_income", "income", "cash_inflow"],
    firstDefined(cashFlowValue, ["inflow", "income"], 0),
  ));
  const spending = finiteNumber(firstDefined(
    snapshot,
    ["monthly_expenses", "monthly_spending", "expenses", "cash_outflow"],
    firstDefined(cashFlowValue, ["outflow", "expenses"], 0),
  ));
  const cashFlow = finiteNumber(
    typeof cashFlowValue === "object"
      ? firstDefined(cashFlowValue, ["net", "amount", "value"], income - spending)
      : cashFlowValue,
    income - spending,
  );
  const months = finiteNumber(firstDefined(snapshot, ["emergency_fund_months", "emergency_months", "cash_runway_months"]));
  const currencyCode = firstDefined(
    snapshot,
    ["currency"],
    firstDefined(assetsValue, ["currency"], firstDefined(liabilitiesValue, ["currency"], "CNY")),
  );
  const money = currencyCode === "CNY" ? currency : compactCurrency;

  $("#metric-assets").textContent = money.format(assets);
  $("#metric-liabilities").textContent = money.format(liabilities);
  $("#metric-net-worth").textContent = money.format(netWorth);
  $("#metric-cash-flow").textContent = `${cashFlow >= 0 ? "+" : ""}${money.format(cashFlow)}`;
  $("#metric-cash-flow").style.color = cashFlow >= 0 ? "var(--forest-bright)" : "var(--rose)";
  $("#metric-monthly-spend").textContent = money.format(spending);
  $("#metric-emergency-months").textContent = firstDefined(snapshot, ["emergency_fund_months", "emergency_months", "cash_runway_months"]) == null
    ? "数据不足"
    : `${months.toFixed(1)} 个月`;
  $("#cash-flow-detail").textContent = income || spending
    ? `月收入 ${money.format(income)} · 月支出 ${money.format(spending)}`
    : "收入与支出的确定性汇总";
  $("#snapshot-as-of").textContent = formatDate(firstDefined(snapshot, ["as_of", "snapshot_at", "generated_at"]));
}

async function importSnapshot() {
  if (!state.file) return;
  const button = $("#import-file");
  clearError($("#import-error"));
  setBusy(button, true, "正在计算…");
  try {
    const form = new FormData();
    form.append("file", state.file, state.file.name);
    const response = await request("/import", { method: "POST", body: form });
    const payload = await response.json();
    if (!payload.snapshot) throw new Error("API 未返回 FinancialSnapshot。");
    state.snapshot = payload.snapshot;
    snapshotView(state.snapshot);
    $("#snapshot-section").hidden = false;
    $("#research-section").hidden = false;
    setJourney(2);
    await loadSymbols();
    $("#snapshot-section").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (error) {
    showError($("#import-error"), error);
  } finally {
    setBusy(button, false);
    button.disabled = !state.file;
  }
}

function normalizeSymbol(item) {
  if (typeof item === "string") return { symbol: item, name: item };
  return {
    symbol: String(firstDefined(item, ["symbol", "code", "ticker"], "")),
    name: String(firstDefined(item, ["name", "display_name", "company_name"], "")),
  };
}

async function loadSymbols() {
  try {
    const response = await request("/symbols");
    const payload = await response.json();
    const items = Array.isArray(payload) ? payload : payload.symbols || payload.items || [];
    const symbols = items.map(normalizeSymbol).filter((item) => item.symbol);
    if (!symbols.length) return;
    state.symbols = symbols;
    const select = $("#symbol-select");
    select.replaceChildren(...symbols.map((item) => {
      const option = document.createElement("option");
      option.value = item.symbol;
      option.textContent = `${item.symbol} · ${item.name}`;
      return option;
    }));
    if (symbols.some((item) => item.symbol === "600519")) select.value = "600519";
  } catch (_) {
    // The default 600519 option keeps the demo usable if optional symbol discovery fails.
  }
}

function listValues(memo, keys) {
  const value = firstDefined(memo, keys, []);
  if (Array.isArray(value)) return value;
  return value ? [value] : [];
}

function itemText(item) {
  if (typeof item === "string") return item;
  return firstDefined(item, ["summary", "text", "description", "claim", "value", "title"], JSON.stringify(item));
}

function suitabilityText(value) {
  const labels = {
    SUITABLE: "在当前财务安全边界内具备适配空间；仍需遵守建议仓位上限。",
    CAUTION: "适配性有限，应谨慎评估风险并严格控制仓位。",
    UNSUITABLE: "当前财务安全边界不支持建立该证券仓位。",
    INSUFFICIENT_DATA: "当前数据不足，无法形成可靠的个人适配结论。",
  };
  return labels[String(value)] || itemText(value);
}

function fillList(target, items, emptyText) {
  const values = items.length ? items : [emptyText];
  target.replaceChildren(...values.map((item) => {
    const li = document.createElement("li");
    li.textContent = itemText(item);
    return li;
  }));
}

function fillEvidence(items) {
  const evidence = items.length ? items : [{ title: "资料覆盖", summary: "当前研究未返回额外证据摘要。" }];
  $("#evidence-list").replaceChildren(...evidence.map((item, index) => {
    const article = document.createElement("article");
    article.className = "evidence-item";
    const title = document.createElement("strong");
    title.textContent = typeof item === "object"
      ? firstDefined(item, ["title", "source", "label"], `证据 ${index + 1}`)
      : `证据 ${index + 1}`;
    const copy = document.createElement("p");
    copy.textContent = itemText(item);
    article.append(title, copy);
    return article;
  }));
}

function renderMemo(memo, requestedSymbol) {
  const symbol = String(firstDefined(memo, ["symbol", "ticker", "code"], requestedSymbol));
  const selected = state.symbols.find((item) => item.symbol === symbol);
  const name = firstDefined(memo, ["name", "company_name", "display_name"], selected?.name || "研究标的");
  const summary = firstDefined(memo, ["research_summary", "summary", "current_judgment", "conclusion"], "研究完成，请结合下方风险与证据审慎判断。");
  const suitability = firstDefined(memo, ["personal_suitability", "suitability", "suitability_summary"], "适配结论未提供。");
  const warning = firstDefined(memo, ["risk_warning", "warning"], "证券投资可能损失本金；本结果不构成投资建议。");
  const rawAllocation = firstDefined(memo, ["recommended_maximum_allocation", "recommended_max_allocation", "max_allocation", "maximum_position"], null);
  const allocationAvailable = rawAllocation !== null && rawAllocation !== undefined;
  let allocation = allocationAvailable
    ? finiteNumber(
      typeof rawAllocation === "object"
        ? firstDefined(rawAllocation, ["percent", "ratio", "value"], 0)
        : rawAllocation,
    )
    : 0;
  if (allocation > 0 && allocation <= 1 && !(typeof rawAllocation === "object" && "percent" in rawAllocation)) allocation *= 100;
  allocation = Math.max(0, Math.min(100, allocation));

  $("#result-symbol").textContent = symbol;
  $("#result-name").textContent = String(name);
  $("#research-summary").textContent = String(summary);
  $("#suitability-copy").textContent = String(suitabilityText(suitability));
  $("#risk-warning").textContent = String(itemText(warning));
  $("#max-allocation").textContent = allocationAvailable
    ? `${allocation.toLocaleString("zh-CN", { minimumFractionDigits: 0, maximumFractionDigits: 2 })}%`
    : "数据不足";
  $("#allocation-gauge").style.setProperty("--allocation", String(allocation));
  const allocationAmount = rawAllocation && typeof rawAllocation === "object"
    ? firstDefined(rawAllocation, ["amount"], null)
    : null;
  $("#max-allocation-amount").textContent = allocationAmount == null
    ? "由确定性适配引擎计算"
    : `金额上限 ${currency.format(finiteNumber(allocationAmount))}`;
  $("#research-as-of").textContent = formatDate(firstDefined(memo, ["as_of", "data_as_of", "research_as_of", "generated_at"]));
  const model = firstDefined(memo, ["model_version", "model", "gateway_model"], null);
  $("#model-version").textContent = model && typeof model === "object"
    ? `${model.provider || "Model Gateway"} · ${model.model || "cached/demo"}`
    : model || "Model Gateway · cached/demo";
  $("#coverage-badge").textContent = firstDefined(memo, ["coverage", "data_coverage", "coverage_summary"], "缓存演示数据");

  fillList($("#positives-list"), listValues(memo, ["key_positives", "positives", "strengths"]), "暂无明确积极因素。 ");
  fillList($("#risks-list"), listValues(memo, ["key_risks", "risks", "risk_factors"]), "暂无额外风险条目；仍需注意市场波动风险。");
  fillEvidence(listValues(memo, ["evidence", "evidence_summary", "data_summary", "evidence_data_summary"]));

  $("#result-section").hidden = false;
  setJourney(3);
  $("#result-section").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function runResearch(event) {
  event.preventDefault();
  if (!state.snapshot) {
    showError($("#research-error"), "请先导入 synthetic CSV 并生成财务快照。");
    return;
  }
  const button = $("#run-research");
  const symbol = $("#symbol-select").value;
  const question = $("#research-question").value.trim();
  clearError($("#research-error"));
  $("#result-section").hidden = true;
  $("#research-loading").hidden = false;
  setBusy(button, true, "研究生成中…");
  const stages = ["读取缓存研究资料…", "经 Model Gateway 生成结构化解释…", "运行确定性风险与适配计算…"];
  let stage = 0;
  const interval = window.setInterval(() => {
    stage = Math.min(stage + 1, stages.length - 1);
    $("#loading-stage").textContent = stages[stage];
  }, 900);
  try {
    const response = await request("/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ symbol, question, snapshot: state.snapshot }),
    });
    const payload = await response.json();
    if (!payload.memo) throw new Error("Research Service 未返回结构化 memo。");
    renderMemo(payload.memo, symbol);
  } catch (error) {
    showError($("#research-error"), error);
    $("#research-section").scrollIntoView({ behavior: "smooth", block: "start" });
  } finally {
    window.clearInterval(interval);
    $("#loading-stage").textContent = stages[0];
    $("#research-loading").hidden = true;
    setBusy(button, false);
  }
}

async function checkHealth() {
  const target = $("#api-status");
  try {
    await request("/health");
    target.className = "api-status is-online";
    target.lastElementChild.textContent = "演示服务在线";
  } catch (_) {
    target.className = "api-status is-offline";
    target.lastElementChild.textContent = "等待演示服务";
  }
}

function setup() {
  $("#choose-file").addEventListener("click", () => $("#csv-file").click());
  $("#csv-file").addEventListener("change", (event) => selectFile(event.target.files[0]));
  $("#load-demo").addEventListener("click", loadDemo);
  $("#import-file").addEventListener("click", importSnapshot);
  $("#research-form").addEventListener("submit", runResearch);

  const zone = $("#upload-zone");
  ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.add("is-dragging");
  }));
  ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
  }));
  zone.addEventListener("drop", (event) => selectFile(event.dataTransfer.files[0]));
  checkHealth();
}

setup();
