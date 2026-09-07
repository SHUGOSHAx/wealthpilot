const PERSONAL_API = "/api/v1/personal";
const DEMO_API = "/api/v1/demo";
const ROUTES = {
  overview: ["PERSONAL OVERVIEW", "财务总览"],
  transactions: ["AUTHORITATIVE RECORDS", "交易流水"],
  import: ["REVIEW BEFORE COMMIT", "导入数据"],
  research: ["CONTEXT-AWARE RESEARCH", "证券研究"],
  settings: ["LOCAL CONTROL", "设置与数据"],
};
const CATEGORIES = ["工资收入", "投资收入", "住房", "餐饮", "交通", "购物", "医疗", "教育", "娱乐", "转账", "其他"];
const state = { route: "overview", overview: null, transactions: [], preview: null, importFile: null, snapshots: [], history: [], settings: null, editingTransaction: null };
const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => [...document.querySelectorAll(selector)];
const cny = new Intl.NumberFormat("zh-CN", { style: "currency", currency: "CNY", minimumFractionDigits: 2 });

function first(source, keys, fallback = undefined) {
  for (const key of keys) if (source?.[key] !== undefined && source[key] !== null) return source[key];
  return fallback;
}

function number(value) {
  if (value && typeof value === "object") return number(first(value, ["amount", "value", "net", "percent"], NaN));
  const parsed = typeof value === "string" ? Number(value.replace(/[,%¥]/g, "")) : Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function money(value, { sign = false } = {}) {
  const amount = number(value);
  if (amount === null) return "—";
  return `${sign && amount > 0 ? "+" : ""}${cny.format(amount)}`;
}

function dateTime(value, fallback = "—") {
  if (!value) return fallback;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? String(value) : new Intl.DateTimeFormat("zh-CN", { dateStyle: "medium", timeStyle: "short" }).format(parsed);
}

function textItem(value) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  return String(first(value, ["text", "summary", "description", "claim", "value", "title", "label"], "—"));
}

function unwrap(payload, keys) {
  for (const key of keys) if (payload?.[key] !== undefined) return payload[key];
  return payload;
}

class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function request(path, options = {}, base = PERSONAL_API) {
  const response = await fetch(`${base}${path}`, options);
  if (!response.ok) {
    let message = `请求失败（HTTP ${response.status}）`;
    try {
      const body = await response.json();
      const detail = body.detail;
      message = detail?.message || detail || body.message || body.error || message;
      if (typeof message !== "string") message = JSON.stringify(message);
    } catch (_) { /* A non-JSON error body must not leak details. */ }
    throw new ApiError(response.status, message);
  }
  return response;
}

async function jsonRequest(path, options = {}, base = PERSONAL_API) {
  return (await request(path, options, base)).json();
}

function clearError(target) { target.hidden = true; target.textContent = ""; }
function showError(target, error) { target.textContent = error instanceof Error ? error.message : String(error); target.hidden = false; }
function setBusy(button, busy, label) {
  if (busy) { button.dataset.previousLabel = button.textContent; button.textContent = label; button.disabled = true; button.setAttribute("aria-busy", "true"); }
  else { button.textContent = button.dataset.previousLabel || button.textContent; button.disabled = false; button.removeAttribute("aria-busy"); }
}

function node(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined) element.textContent = String(content);
  return element;
}

function itemArray(payload, keys = ["items"]) {
  const value = unwrap(payload, keys);
  return Array.isArray(value) ? value : [];
}

async function checkService() {
  const target = $("#api-status");
  try {
    await request("/settings");
    target.className = "api-status is-online";
    target.lastElementChild.textContent = "个人服务在线";
  } catch (_) {
    target.className = "api-status is-offline";
    target.lastElementChild.textContent = "个人服务离线";
  }
}

function routeFromHash() {
  const name = location.hash.replace(/^#/, "");
  return ROUTES[name] ? name : "overview";
}

async function navigate() {
  state.route = routeFromHash();
  $$("[data-page]").forEach((page) => { page.hidden = page.dataset.page !== state.route; page.classList.toggle("is-active", page.dataset.page === state.route); });
  $$("[data-route]").forEach((link) => link.classList.toggle("is-active", link.dataset.route === state.route));
  $("#page-eyebrow").textContent = ROUTES[state.route][0];
  $("#page-title").textContent = ROUTES[state.route][1];
  document.title = `${ROUTES[state.route][1]} · WealthPilot`;
  clearError($("#global-error"));
  const loaders = { overview: loadOverview, transactions: loadTransactions, research: loadResearchPage, settings: loadSettings };
  try { if (loaders[state.route]) await loaders[state.route](); } catch (error) { showError($("#global-error"), error); }
  $("#workspace").focus({ preventScroll: true });
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function overviewSnapshot(payload) {
  const overview = unwrap(payload, ["overview"]);
  return first(overview, ["snapshot", "financial_snapshot", "current_snapshot"], overview);
}

function isEmptyOverview(payload, snapshot) {
  return payload?.has_data === false || payload?.empty === true || !snapshot || Object.keys(snapshot).length === 0 || first(snapshot, ["status"]) === "EMPTY";
}

async function loadOverview() {
  $("#overview-loading").hidden = false; $("#first-run").hidden = true; $("#overview-content").hidden = true;
  try {
    const payload = await jsonRequest("/overview");
    const snapshot = overviewSnapshot(payload);
    state.overview = payload;
    if (isEmptyOverview(payload, snapshot)) { $("#first-run").hidden = false; return; }
    renderOverview(payload, snapshot);
    $("#overview-content").hidden = false;
  } catch (error) {
    if (error.status === 404) $("#first-run").hidden = false;
    else throw error;
  } finally { $("#overview-loading").hidden = true; }
}

function renderOverview(payload, snapshot) {
  const cashFlow = first(snapshot, ["cash_flow", "cash_flow_summary"], {});
  const inflow = first(cashFlow, ["inflow", "total_inflows"]);
  const outflow = first(cashFlow, ["outflow", "total_outflows"]);
  const months = number(first(snapshot, ["emergency_fund_months", "emergency_months"]));
  $("#overview-net-worth").textContent = money(first(snapshot, ["net_worth"]));
  $("#overview-assets").textContent = money(first(snapshot, ["assets", "total_assets"]));
  $("#overview-liabilities").textContent = money(first(snapshot, ["liabilities", "total_liabilities"]));
  $("#overview-cash-flow").textContent = money(first(cashFlow, ["net", "net_cash_flow"], first(snapshot, ["monthly_cash_flow"])), { sign: true });
  $("#overview-cash-flow").classList.toggle("is-negative", number(first(cashFlow, ["net"], 0)) < 0);
  $("#cash-flow-breakdown").textContent = `${money(inflow)} 收入 · ${money(outflow)} 支出`;
  $("#monthly-expenses").textContent = money(first(snapshot, ["monthly_expenses"]));
  $("#investable-capital").textContent = money(first(snapshot, ["investable_capital"]));
  $("#emergency-months").textContent = months === null ? "—" : months.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
  $("#buffer-ring").style.setProperty("--progress", String(Math.min(100, Math.max(0, (months || 0) / 6 * 100))));
  const status = months === null ? "数据不足" : months >= 6 ? "储备充足" : months >= 3 ? "需要关注" : "储备偏低";
  $("#buffer-status").textContent = status; $("#buffer-status").className = `status-badge${months !== null && months < 6 ? " is-warning" : ""}`;
  $("#overview-as-of").textContent = dateTime(first(snapshot, ["as_of", "generated_at", "updated_at"]));
  const accounts = itemArray(first(snapshot, ["accounts"], []));
  $("#asset-account-count").textContent = accounts.length ? `${accounts.length} 个账户` : "所有账户";
  $("#account-list").replaceChildren(...(accounts.length ? accounts : [{ name: "暂无账户", balance: null }]).map((account) => {
    const row = node("div", "snapshot-item"); row.append(node("strong", "", first(account, ["name"], "未命名账户")), node("span", "", first(account, ["asset_class", "account_type"], "—")), node("b", "", money(first(account, ["balance"])))); return row;
  }));
  const allocation = first(snapshot, ["asset_allocation"], {}); const allocationLabels = { CASH: "现金", EQUITY: "权益", FIXED_INCOME: "固定收益", REAL_ESTATE: "房产", OTHER: "其他", UNKNOWN: "待分类" };
  $("#allocation-list").replaceChildren(...(Object.entries(allocation).length ? Object.entries(allocation) : [["UNKNOWN", null]]).map(([kind, value]) => {
    const row = node("div", "snapshot-item"); row.append(node("strong", "", allocationLabels[kind] || kind), node("span", "", kind), node("b", "", money(value))); return row;
  }));
  const recent = itemArray(payload, ["recent_transactions", "transactions"]).slice(0, 5);
  renderRecentTransactions(recent);
  const snapshotId = first(snapshot, ["snapshot_id", "id"], "当前快照");
  $("#research-context").textContent = `${snapshotId} · ${dateTime(first(snapshot, ["as_of"]), "最新")}`;
}

function transactionFields(item) {
  const rawAmount = first(item, ["amount", "signed_amount", "value"]);
  const amount = number(rawAmount);
  const direction = String(first(item, ["direction", "flow_direction", "type"], amount !== null && amount < 0 ? "OUTFLOW" : "INFLOW")).toUpperCase();
  return {
    id: String(first(item, ["transaction_id", "id"], "")), date: first(item, ["date", "occurred_at", "booked_at"], "—"),
    merchant: String(first(item, ["merchant_normalized", "merchant", "description", "counterparty", "name"], "未命名交易")),
    description: String(first(item, ["description", "note", "memo"], "")), category: String(first(item, ["category", "category_name"], "未分类")),
    source: String(first(item, ["source", "source_name", "account", "account_name"], "本地导入")), amount: rawAmount, direction,
    flags: first(item, ["flags"], {}), updatedAt: first(item, ["updated_at", "corrected_at"]), raw: item,
  };
}

function renderRecentTransactions(items) {
  const target = $("#recent-transactions");
  if (!items.length) { target.className = "transaction-list empty-box"; target.textContent = "暂无交易"; return; }
  target.className = "transaction-list";
  target.replaceChildren(...items.map((raw) => {
    const item = transactionFields(raw); const row = node("div", "transaction-item");
    row.append(node("strong", "", item.merchant), node("span", "", `${String(item.date).slice(0, 10)} · ${item.category}`));
    const amount = node("b", item.direction === "OUTFLOW" ? "outflow" : "", money(item.amount, { sign: item.direction === "INFLOW" })); row.append(amount); return row;
  }));
}

async function loadTransactions() {
  $("#transactions-loading").hidden = false; $("#transactions-table-wrap").hidden = true; $("#transactions-empty").hidden = true;
  try {
    const payload = await jsonRequest("/transactions");
    state.transactions = itemArray(payload, ["transactions", "items"]);
    populateCategoryFilter(); renderTransactions();
  } finally { $("#transactions-loading").hidden = true; }
}

function populateCategoryFilter() {
  const current = $("#transaction-category-filter").value;
  const categories = [...new Set(state.transactions.map((item) => transactionFields(item).category))].filter(Boolean).sort();
  $("#transaction-category-filter").replaceChildren(new Option("全部分类", ""), ...categories.map((value) => new Option(value, value)));
  $("#transaction-category-filter").value = categories.includes(current) ? current : "";
}

function filteredTransactions() {
  const query = $("#transaction-search").value.trim().toLowerCase(); const category = $("#transaction-category-filter").value; const direction = $("#transaction-direction-filter").value;
  return state.transactions.filter((raw) => { const item = transactionFields(raw); const haystack = `${item.merchant} ${item.description} ${item.category}`.toLowerCase(); return (!query || haystack.includes(query)) && (!category || item.category === category) && (!direction || item.direction === direction); });
}

function renderTransactions() {
  const items = filteredTransactions(); $("#transaction-count").textContent = `${items.length} 条`; $("#transactions-empty").hidden = items.length > 0; $("#transactions-table-wrap").hidden = !items.length;
  $("#transactions-body").replaceChildren(...items.map((raw) => {
    const item = transactionFields(raw); const row = document.createElement("tr");
    const merchant = node("td"); merchant.append(node("strong", "", item.merchant)); if (item.description && item.description !== item.merchant) merchant.append(node("small", "table-subtext", item.description));
    const category = node("td"); category.append(node("span", "category-tag", item.category)); const source = node("td"); source.append(node("span", "source-tag", item.source));
    const amount = node("td", "amount-cell", money(item.amount, { sign: item.direction === "INFLOW" })); if (item.direction === "OUTFLOW") amount.classList.add("negative");
    const action = node("td"); const button = node("button", "edit-row", "✎"); button.type = "button"; button.setAttribute("aria-label", `修正 ${item.merchant}`); button.addEventListener("click", () => openTransactionDialog(item)); action.append(button);
    row.append(node("td", "", String(item.date).slice(0, 10)), merchant, category, source, amount, action); return row;
  }));
}

function flagValue(flags, key) { return Array.isArray(flags) ? flags.includes(key) : Boolean(flags?.[key]); }
function openTransactionDialog(item) {
  state.editingTransaction = item; $("#transaction-dialog-meta").textContent = `${String(item.date).slice(0, 10)} · ${money(item.amount)}`;
  $("#edit-merchant").value = item.merchant; $("#edit-category").value = item.category; $("#edit-exclude").checked = flagValue(item.flags, "reimbursement") || flagValue(item.flags, "exclude_from_cash_flow"); $("#edit-transfer").checked = flagValue(item.flags, "transfer") || flagValue(item.flags, "internal_transfer"); clearError($("#transaction-error")); $("#transaction-dialog").showModal();
}

async function saveTransaction(event) {
  event.preventDefault(); if (!state.editingTransaction?.id) return;
  const button = $("#save-transaction"); setBusy(button, true, "保存中…"); clearError($("#transaction-error"));
  const body = { merchant: $("#edit-merchant").value.trim(), category: $("#edit-category").value.trim(), flags: { reimbursement: $("#edit-exclude").checked, transfer: $("#edit-transfer").checked } };
  try {
    const payload = await jsonRequest(`/transactions/${encodeURIComponent(state.editingTransaction.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const updated = unwrap(payload, ["transaction", "item"]); state.transactions = state.transactions.map((item) => transactionFields(item).id === state.editingTransaction.id ? updated : item); $("#transaction-dialog").close(); renderTransactions(); state.overview = null;
  } catch (error) { showError($("#transaction-error"), error); } finally { setBusy(button, false); }
}

function chooseImportFile(file) {
  clearError($("#import-error")); if (!file) return;
  if (!file.name.toLowerCase().endsWith(".csv")) { showError($("#import-error"), "请选择 CSV 文件。"); return; }
  state.importFile = file; $("#import-file-name").textContent = `${file.name} · ${Math.max(1, Math.round(file.size / 1024))} KB`; $("#preview-import").disabled = false;
}

async function loadSample() {
  const button = $("#load-sample"); setBusy(button, true, "载入中…"); clearError($("#import-error"));
  try { const response = await request("/sample-csv", {}, DEMO_API); chooseImportFile(new File([await response.blob()], "wealthpilot-synthetic-sample.csv", { type: "text/csv" })); }
  catch (error) { showError($("#import-error"), error); } finally { setBusy(button, false); }
}

async function previewImport() {
  if (!state.importFile) return; const button = $("#preview-import"); setBusy(button, true, "解析中…"); clearError($("#import-error")); $("#preview-loading").hidden = false; $("#import-preview").hidden = true; $("#import-success").hidden = true;
  try { const form = new FormData(); form.append("file", state.importFile, state.importFile.name); const payload = await (await request("/imports/preview", { method: "POST", body: form })).json(); state.preview = unwrap(payload, ["preview", "import_preview"]); renderImportPreview(); }
  catch (error) { showError($("#import-error"), error); } finally { $("#preview-loading").hidden = true; setBusy(button, false); }
}

function previewFields(raw) {
  const item = transactionFields(raw); const status = String(first(raw, ["status", "disposition", "match_status"], raw.duplicate ? "DUPLICATE" : "NEW")).toUpperCase();
  return { ...item, status, include: first(raw, ["include", "selected"], status !== "DUPLICATE"), confidence: first(raw, ["confidence", "category_confidence"]), raw };
}

function previewItems() { return itemArray(state.preview || {}, ["transactions", "items", "records"]); }
function previewCounts(items) {
  const declared = first(state.preview, ["summary", "counts"], {}); const count = (key, status) => first(declared, key, items.filter((raw) => previewFields(raw).status === status).length);
  return { added: count(["new", "new_count", "added"], "NEW"), duplicate: count(["duplicate", "duplicates", "duplicate_count"], "DUPLICATE"), conflict: count(["conflict", "conflicts", "conflict_count"], "CONFLICT"), review: count(["needs_review", "review", "review_count"], "NEEDS_REVIEW") };
}

function renderImportPreview() {
  const items = previewItems(); const counts = previewCounts(items); const batchId = first(state.preview, ["batch_id", "import_batch_id", "id"], "—");
  $("#preview-batch-id").textContent = `批次 ${batchId}`; $("#preview-new").textContent = counts.added; $("#preview-duplicate").textContent = counts.duplicate; $("#preview-conflict").textContent = counts.conflict; $("#preview-review").textContent = counts.review;
  $("#preview-body").replaceChildren(...items.map((raw) => buildPreviewRow(previewFields(raw)))); $("#confirm-reviewed").checked = false; $("#confirm-import").disabled = true; $("#import-preview").hidden = false;
}

function buildPreviewRow(item) {
  const row = document.createElement("tr"); row.dataset.transactionId = item.id;
  const status = node("td"); status.append(node("span", `row-status ${item.status.toLowerCase().replace("needs_", "")}`, item.status === "NEEDS_REVIEW" ? "待确认" : { NEW: "新增", DUPLICATE: "重复", CONFLICT: "冲突" }[item.status] || item.status));
  const description = node("td"); description.append(node("strong", "", String(item.date).slice(0, 10)), node("small", "table-subtext", item.description || item.merchant));
  const merchantCell = node("td"); const merchant = document.createElement("input"); merchant.value = item.merchant; merchant.setAttribute("aria-label", "商户"); merchantCell.append(merchant);
  const categoryCell = node("td"); const category = document.createElement("input"); category.value = item.category; category.setAttribute("aria-label", "分类"); category.setAttribute("list", "category-options"); categoryCell.append(category);
  const amount = node("td", "amount-cell", money(item.amount)); const action = node("td");
  const treatment = document.createElement("select"); treatment.setAttribute("aria-label", "交易处理标记");
  treatment.replaceChildren(new Option("普通", "normal"), new Option("内部转账", "transfer"), new Option("退款", "refund"), new Option("报销项", "reimbursement"));
  treatment.value = flagValue(item.flags, "transfer") ? "transfer" : flagValue(item.flags, "refund") ? "refund" : flagValue(item.flags, "reimbursement") ? "reimbursement" : "normal";
  treatment.disabled = item.status === "DUPLICATE";
  const save = node("button", "save-preview-row", item.status === "DUPLICATE" ? "重复跳过" : "保存修改"); save.type = "button"; save.disabled = item.status === "DUPLICATE";
  save.addEventListener("click", () => updatePreviewRow(item, { merchant: merchant.value.trim(), category: category.value.trim(), treatment: treatment.value }, save));
  action.append(treatment, save); row.append(status, description, merchantCell, categoryCell, amount, action); return row;
}

async function updatePreviewRow(item, changes, button) {
  const batchId = first(state.preview, ["batch_id", "import_batch_id", "id"]); if (!batchId || !item.id) return;
  setBusy(button, true, "保存中…"); clearError($("#confirm-error"));
  const flags = { transfer: changes.treatment === "transfer", refund: changes.treatment === "refund", reimbursement: changes.treatment === "reimbursement" };
  try { const payload = await jsonRequest(`/imports/${encodeURIComponent(batchId)}/transactions/${encodeURIComponent(item.id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ merchant: changes.merchant, category: changes.category, flags }) }); const updated = unwrap(payload, ["transaction", "item"]); const items = previewItems().map((raw) => previewFields(raw).id === item.id ? updated : raw); if (state.preview.transactions) state.preview.transactions = items; else state.preview.items = items; renderImportPreview(); }
  catch (error) { showError($("#confirm-error"), error); } finally { setBusy(button, false); }
}

async function confirmImport() {
  const batchId = first(state.preview, ["batch_id", "import_batch_id", "id"]); if (!batchId) return; const button = $("#confirm-import"); setBusy(button, true, "确认中…"); clearError($("#confirm-error"));
  try { const payload = await jsonRequest(`/imports/${encodeURIComponent(batchId)}/confirm`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirmed: true }) }); const imported = first(payload, ["imported_count", "created_count"], "已选交易"); $("#import-success-copy").textContent = `${imported} 已写入，本地 FinancialSnapshot 已重新生成。`; $("#import-preview").hidden = true; $("#import-success").hidden = false; state.overview = null; state.transactions = []; }
  catch (error) { showError($("#confirm-error"), error); } finally { setBusy(button, false); }
}

function resetImport() { state.preview = null; state.importFile = null; $("#import-file-input").value = ""; $("#import-file-name").textContent = "拖入 CSV，或选择本机文件"; $("#preview-import").disabled = true; $("#import-preview").hidden = true; $("#import-success").hidden = true; }

async function loadResearchPage() { await Promise.allSettled([loadResearchHistory(), ensureOverviewContext()]); }
async function ensureOverviewContext() { if (!state.overview) { try { state.overview = await jsonRequest("/overview"); } catch (_) { return; } } const snapshot = overviewSnapshot(state.overview); if (snapshot && !isEmptyOverview(state.overview, snapshot)) $("#research-context").textContent = `最新快照 · ${dateTime(first(snapshot, ["as_of"]), "已就绪")}`; }

async function loadResearchHistory() {
  const payload = await jsonRequest("/research/history"); state.history = itemArray(payload, ["history", "research", "items"]); const target = $("#research-history");
  if (!state.history.length) { target.className = "history-list empty-box"; target.textContent = "暂无研究记录"; return; }
  target.className = "history-list"; target.replaceChildren(...state.history.map((raw) => { const memo = unwrap(raw, ["memo", "result"]); const button = node("button", "history-item"); button.type = "button"; button.append(node("strong", "", `${first(memo, ["symbol"], "—")} · ${first(memo, ["company_name", "name"], "研究备忘录")}`), node("span", "", textItem(first(memo, ["research_summary", "summary"], "查看历史结果"))), node("time", "", dateTime(first(raw, ["created_at", "updated_at"], first(memo, ["as_of"]))))); button.addEventListener("click", () => renderMemo(memo)); return button; }));
}

async function runResearch(event) {
  event.preventDefault(); const button = $("#run-research"); setBusy(button, true, "研究中…"); clearError($("#research-error")); $("#research-loading").hidden = false; $("#research-result").hidden = true;
  try { const payload = await jsonRequest("/research", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbol: $("#research-symbol").value.trim(), question: $("#research-question").value.trim() }) }); renderMemo(unwrap(payload, ["memo", "result"])); await loadResearchHistory(); }
  catch (error) { showError($("#research-error"), error); } finally { $("#research-loading").hidden = true; setBusy(button, false); }
}

function suitability(value) { return ({ SUITABLE: "在当前财务安全边界内具备适配空间；仍需遵守建议仓位上限。", CAUTION: "适配性有限，应谨慎评估并严格控制仓位。", UNSUITABLE: "当前财务安全边界不支持建立该证券仓位。", INSUFFICIENT_DATA: "数据不足，无法形成可靠的个人适配结论。" })[String(value)] || textItem(value); }
function list(value) { return Array.isArray(value) ? value : value ? [value] : []; }
function fillMemoList(target, items, emptyText) { target.replaceChildren(...(items.length ? items : [emptyText]).map((item) => node("li", "", textItem(item)))); }

function renderMemo(memo) {
  if (!memo) return; const allocation = first(memo, ["recommended_max_allocation", "recommended_maximum_allocation", "maximum_position"]); const percent = allocation && typeof allocation === "object" ? number(first(allocation, ["percent", "ratio"])) : number(allocation); const model = first(memo, ["model", "model_version"], {});
  $("#memo-symbol").textContent = first(memo, ["symbol", "code"], "—"); $("#memo-name").textContent = first(memo, ["company_name", "name"], "研究标的"); $("#memo-as-of").textContent = dateTime(first(memo, ["as_of", "data_as_of"]));
  $("#memo-model").textContent = typeof model === "object" ? `${first(model, ["provider"], "Model Gateway")} · ${first(model, ["model"], "local")}` : String(model || "Model Gateway"); $("#memo-summary").textContent = textItem(first(memo, ["research_summary", "summary", "conclusion"], "—")); $("#memo-suitability").textContent = suitability(first(memo, ["personal_suitability", "suitability"], "INSUFFICIENT_DATA"));
  $("#memo-allocation").textContent = percent === null ? "数据不足" : `${percent.toLocaleString("zh-CN", { maximumFractionDigits: 2 })}%`; $("#memo-allocation-amount").textContent = allocation && typeof allocation === "object" && first(allocation, ["amount"]) !== undefined ? `金额上限 ${money(first(allocation, ["amount"]))}` : "确定性计算";
  fillMemoList($("#memo-positives"), list(first(memo, ["key_positives", "positives"])), "暂无明确积极因素");
  const risks = [...list(first(memo, ["key_risks", "risks"])), ...list(first(memo, ["limitations"]))];
  fillMemoList($("#memo-risks"), risks, "暂无额外风险条目");
  const provider = first(memo, ["data_provider"], "公开数据提供方");
  const researchRisk = first(memo, ["research_risk_level"], "UNKNOWN");
  $("#memo-coverage").textContent = textItem(first(memo, ["data_summary", "coverage", "data_coverage"], `${provider} · 研究风险 ${researchRisk}`));
  const evidence = list(first(memo, ["evidence", "evidence_summary"])); $("#memo-evidence").replaceChildren(...(evidence.length ? evidence : [{ label: "资料覆盖", value: "未提供额外证据摘要" }]).map((item) => { const card = node("article", "evidence-item"); const detail = typeof item === "object" && item.source ? `${first(item, ["as_of"], "时点未知")} · ${first(item, ["quality"], "质量未标记")}` : textItem(item); card.append(node("strong", "", first(item, ["label", "title", "source"], "证据")), node("span", "", detail)); return card; }));
  $("#memo-warning").textContent = textItem(first(memo, ["risk_warning", "warning"], "证券投资可能损失本金，本结果不构成投资建议。")); $("#research-result").hidden = false; $("#research-result").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadSettings() { const results = await Promise.allSettled([jsonRequest("/settings"), jsonRequest("/snapshots")]); if (results[0].status === "fulfilled") { state.settings = unwrap(results[0].value, ["settings"]); renderSettings(); } else throw results[0].reason; if (results[1].status === "fulfilled") { state.snapshots = itemArray(results[1].value, ["snapshots", "items"]); renderSnapshots(); } }
function renderSettings() { const model = first(state.settings, ["model", "model_gateway"], state.settings); $("#setting-provider").textContent = first(model, ["provider", "provider_name"], "未配置"); $("#setting-model").textContent = first(model, ["model", "model_name"], "—"); const status = String(first(model, ["status", "state"], "UNKNOWN")); $("#setting-model-status").textContent = status; $("#setting-model-status").className = `status-badge${["READY", "ONLINE", "OK"].includes(status.toUpperCase()) ? "" : " is-warning"}`; const data = first(state.settings, ["data", "storage"], {}); $("#setting-data-copy").textContent = first(data, ["description"], "你的快照、流水与研究历史保存在本地个人数据目录。"); }
function renderSnapshots() { const target = $("#snapshot-history"); if (!state.snapshots.length) { target.className = "snapshot-list empty-box"; target.textContent = "暂无快照记录"; return; } target.className = "snapshot-list"; target.replaceChildren(...state.snapshots.map((raw) => { const item = unwrap(raw, ["snapshot"]); const row = node("div", "snapshot-item"); row.append(node("strong", "", first(item, ["snapshot_id", "id"], "FinancialSnapshot")), node("span", "", `净资产 ${money(first(item, ["net_worth"]))}`), node("time", "", dateTime(first(item, ["as_of", "created_at"])))); return row; })); }

async function backupData() { const button = $("#backup-data"); setBusy(button, true, "准备备份…"); $("#data-action-status").textContent = ""; try { const response = await request("/data/backup", { method: "POST" }); const blob = await response.blob(); const disposition = response.headers.get("content-disposition") || ""; const name = disposition.match(/filename="?([^";]+)"?/)?.[1] || `wealthpilot-backup-${new Date().toISOString().slice(0, 10)}.wpbackup`; const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = name; link.click(); URL.revokeObjectURL(url); $("#data-action-status").textContent = "备份已下载。请妥善保管文件。"; } catch (error) { $("#data-action-status").textContent = error.message; } finally { setBusy(button, false); } }
async function restoreData(file) { if (!file) return; const button = $("#choose-restore"); setBusy(button, true, "恢复中…"); $("#data-action-status").textContent = ""; try { const form = new FormData(); form.append("file", file, file.name); await request("/data/restore", { method: "POST", body: form }); $("#data-action-status").textContent = "恢复完成，正在刷新本地数据…"; state.overview = null; state.transactions = []; state.history = []; await loadSettings(); } catch (error) { $("#data-action-status").textContent = error.message; } finally { $("#restore-file").value = ""; setBusy(button, false); } }

function showProvenance() { const snapshot = overviewSnapshot(state.overview || {}); const source = first(snapshot, ["source", "provenance"], {}); const entries = [["快照 ID", first(snapshot, ["snapshot_id", "id"], "—")], ["计算时点", dateTime(first(snapshot, ["as_of", "generated_at"]))], ["来源", first(source, ["name", "filename", "type"], "本地确认交易")], ["来源摘要", first(source, ["sha256", "content_hash", "record_count"], "—")], ["计算方法", first(snapshot, ["calculation_method", "formula_version"], "Deterministic financial engine")]]; $("#provenance-content").replaceChildren(...entries.map(([term, value]) => { const row = node("div"); row.append(node("dt", "", term), node("dd", "", value)); return row; })); $("#provenance-dialog").showModal(); }

function setupEvents() {
  window.addEventListener("hashchange", navigate); $("#refresh-page").addEventListener("click", navigate); $("#overview-provenance").addEventListener("click", showProvenance); $("[data-close-dialog]").addEventListener("click", () => $("#provenance-dialog").close());
  $("#overview-demo").addEventListener("click", async () => { location.hash = "import"; await loadSample(); });
  [$("#transaction-search"), $("#transaction-category-filter"), $("#transaction-direction-filter")].forEach((control) => control.addEventListener("input", renderTransactions));
  $("#transaction-form").addEventListener("submit", saveTransaction);
  $("#choose-import-file").addEventListener("click", () => $("#import-file-input").click()); $("#import-file-input").addEventListener("change", (event) => chooseImportFile(event.target.files[0])); $("#load-sample").addEventListener("click", loadSample); $("#preview-import").addEventListener("click", previewImport); $("#discard-preview").addEventListener("click", resetImport); $("#confirm-reviewed").addEventListener("change", (event) => { $("#confirm-import").disabled = !event.target.checked; }); $("#confirm-import").addEventListener("click", confirmImport);
  const drop = $("#drop-zone"); ["dragenter", "dragover"].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.add("is-dragging"); })); ["dragleave", "drop"].forEach((name) => drop.addEventListener(name, (event) => { event.preventDefault(); drop.classList.remove("is-dragging"); })); drop.addEventListener("drop", (event) => chooseImportFile(event.dataTransfer.files[0]));
  $("#research-form").addEventListener("submit", runResearch); $("#refresh-history").addEventListener("click", loadResearchHistory); $("#backup-data").addEventListener("click", backupData); $("#choose-restore").addEventListener("click", () => $("#restore-file").click()); $("#restore-file").addEventListener("change", (event) => restoreData(event.target.files[0]));
  $("#mobile-menu").addEventListener("click", () => { location.hash = "overview"; });
}

function setupCategoryOptions() { const datalist = document.createElement("datalist"); datalist.id = "category-options"; datalist.replaceChildren(...CATEGORIES.map((value) => new Option(value))); document.body.append(datalist); }
setupCategoryOptions(); setupEvents(); checkService(); navigate();
