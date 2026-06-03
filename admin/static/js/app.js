const SafetyHub = {
  version: "0.4.0",
  async api(path, options = {}) {
    const response = await fetch(path, { headers: { Accept: "application/json", ...(options.headers || {}) }, ...options });
    if (!response.ok) {
      throw new Error(`${response.status} ${response.statusText}`);
    }
    return response.json();
  },
  text(value) {
    if (value === null || value === undefined || value === "") {
      return "-";
    }
    return String(value);
  },
  time(value) {
    return value ? new Date(value).toLocaleString() : "-";
  },
  json(value) {
    return JSON.stringify(value, null, 2);
  }
};

window.SafetyHub = SafetyHub;

document.addEventListener("DOMContentLoaded", () => {
  const page = document.body.dataset.page;
  document.querySelectorAll("[data-refresh]").forEach((button) => button.addEventListener("click", () => loadPage(page)));
  loadPage(page).catch(showError);
});

async function loadPage(page) {
  if (page === "login") return setupLogin();
  if (page === "dashboard") return loadDashboard();
  if (page === "archives") return loadArchives();
  if (page === "audits") return loadAudits();
  if (page === "observations") return loadObservations();
  if (page === "rules") return loadRules();
  if (page === "apiKeys") return loadApiKeys();
  if (page === "settings") return loadSettings();
  if (page === "placeholder") return loadPlaceholder();
}

function setupLogin() {
  const form = document.getElementById("loginForm");
  const message = document.getElementById("loginMessage");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    message.textContent = "登录中...";
    try {
      await SafetyHub.api("/admin/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: inputValue("loginUsername"), password: inputValue("loginPassword") })
      });
      const next = new URLSearchParams(window.location.search).get("next") || "/admin/index.html";
      window.location.href = next.startsWith("/admin/") ? next : "/admin/index.html";
    } catch (error) {
      message.textContent = "登录失败，请检查账号密码。";
    }
  });
}

async function loadDashboard() {
  const stats = await SafetyHub.api("/admin/api/stats");
  setText("todayRequests", stats.today_requests);
  setText("todayHits", stats.today_hits);
  setText("todayBlocks", stats.today_blocks);
  setText("totalRequests", stats.total_requests);
  const trend = document.getElementById("trend");
  trend.innerHTML = stats.recent_trend.map((item) => `<div class="trend-item"><span>${item.date}</span><strong>请求 ${item.requests}</strong><strong>命中 ${item.hits}</strong><strong>拦截 ${item.blocked}</strong></div>`).join("");
}

async function loadArchives() {
  document.getElementById("applyArchiveFilters")?.addEventListener("click", loadArchives, { once: true });
  const params = new URLSearchParams();
  appendParam(params, "user_id", inputValue("filterUser"));
  appendParam(params, "model", inputValue("filterModel"));
  appendParam(params, "action_taken", inputValue("filterAction"));
  appendParam(params, "keyword", inputValue("filterKeyword"));
  const payload = await SafetyHub.api(`/admin/api/archives?${params}`);
  const table = document.getElementById("archivesTable");
  table.innerHTML = payload.items.map((item) => `<tr data-id="${item.id}"><td>${item.id}</td><td>${item.request_id}</td><td>${SafetyHub.text(item.model)}</td><td><span class="tag">${item.action_taken}</span></td><td>${item.matched_rule_ids.join(", ") || "-"}</td><td>${SafetyHub.time(item.created_at)}</td></tr>`).join("");
  table.querySelectorAll("tr").forEach((row) => row.addEventListener("click", async () => {
    const detail = await SafetyHub.api(`/admin/api/archives/${row.dataset.id}`);
    document.getElementById("archiveDetail").textContent = SafetyHub.json(detail);
  }));
}

async function loadAudits() {
  document.getElementById("applyAuditFilters")?.addEventListener("click", loadAudits, { once: true });
  const params = new URLSearchParams();
  appendParam(params, "rule_id", inputValue("filterRuleId"));
  appendParam(params, "rule_level", inputValue("filterRuleLevel"));
  appendParam(params, "scanner_type", inputValue("filterScannerType"));
  const payload = await SafetyHub.api(`/admin/api/audits?${params}`);
  const table = document.getElementById("auditsTable");
  table.innerHTML = payload.items.map((item) => `<tr data-id="${item.id}"><td>${item.id}</td><td>${item.request_id}</td><td>${item.rule_id}</td><td><span class="tag danger">${item.rule_level}</span></td><td>${item.action_taken}</td><td>${SafetyHub.time(item.created_at)}</td></tr>`).join("");
  table.querySelectorAll("tr").forEach((row) => row.addEventListener("click", async () => {
    const detail = await SafetyHub.api(`/admin/api/audits/${row.dataset.id}`);
    document.getElementById("auditDetail").textContent = SafetyHub.json(detail);
  }));
}

async function loadObservations() {
  const payload = await SafetyHub.api("/admin/api/observations/recent?limit=20");
  const list = document.getElementById("observationsList");
  list.innerHTML = payload.items.map((item) => `<article class="stack-item"><h3>${item.request_id}</h3><p>${item.model || "-"} · ${item.action_taken}</p><pre>${SafetyHub.json({ original: item.messages_original, desensitized: item.messages_desensitized, response: item.response })}</pre></article>`).join("");
}

async function loadRules() {
  document.getElementById("reloadRules")?.addEventListener("click", reloadRules, { once: true });
  const payload = await SafetyHub.api("/admin/api/rules");
  const table = document.getElementById("rulesTable");
  table.innerHTML = payload.items.map((item) => `<tr><td>${item.id}</td><td>${item.name}</td><td>${item.type}</td><td><span class="tag">${item.level}</span></td><td>${item.enabled ? "是" : "否"}</td><td>${item.description}</td><td><button class="button small ${item.enabled ? "secondary" : ""}" data-rule-id="${item.id}" data-enabled="${!item.enabled}">${item.enabled ? "停用" : "启用"}</button></td></tr>`).join("");
  table.querySelectorAll("button[data-rule-id]").forEach((button) => button.addEventListener("click", async () => {
    await toggleRule(button.dataset.ruleId, button.dataset.enabled === "true");
  }));
}

async function toggleRule(ruleId, enabled) {
  setRulesMessage("保存中...");
  const payload = await SafetyHub.api(`/admin/api/rules/${encodeURIComponent(ruleId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled })
  });
  setRulesMessage(`${payload.rule.id} 已${payload.rule.enabled ? "启用" : "停用"}，热加载${payload.reloaded ? "已完成" : "未触发"}`);
  await loadRules();
}

async function reloadRules() {
  setRulesMessage("热加载中...");
  const payload = await SafetyHub.api("/admin/api/rules/reload", { method: "POST" });
  setRulesMessage(payload.reloaded ? "规则热加载已完成。" : "当前进程未挂载 scanner，未触发热加载。");
}

function setRulesMessage(message) {
  const element = document.getElementById("rulesMessage");
  if (element) element.textContent = message;
}

async function loadApiKeys() {
  document.getElementById("createApiKey")?.addEventListener("click", createApiKey, { once: true });
  const reuseUpstreamKey = document.getElementById("reuseUpstreamKey");
  if (reuseUpstreamKey) reuseUpstreamKey.onchange = toggleSafetyHubKeyInput;
  document.getElementById("bulkReplaceApiKeys")?.addEventListener("click", bulkReplaceApiKeys, { once: true });
  toggleSafetyHubKeyInput();
  const payload = await SafetyHub.api("/admin/api/api-keys");
  const table = document.getElementById("apiKeysTable");
  table.innerHTML = payload.items.map((item) => `<tr data-id="${item.id}"><td>${SafetyHub.text(item.name)}</td><td>${SafetyHub.text(item.owner_user_id)}</td><td>${item.key_prefix}******${item.key_suffix}</td><td><span class="tag">${item.is_decoupled ? "K-Decoupled" : "K-Sync"}</span></td><td>${SafetyHub.text(item.upstream_key_prefix)}</td><td>由中转站管理</td><td>${item.status}</td><td>${SafetyHub.time(item.created_at)}</td><td><button class="button small secondary" data-action="replace">替换上游</button> <button class="button small secondary" data-action="revoke">吊销</button></td></tr>`).join("");
  table.querySelectorAll("button[data-action]").forEach((button) => button.addEventListener("click", async (event) => {
    event.stopPropagation();
    const row = button.closest("tr");
    if (button.dataset.action === "replace") await replaceApiKey(row.dataset.id);
    if (button.dataset.action === "revoke") await revokeApiKey(row.dataset.id);
  }));
}

async function createApiKey() {
  setApiKeyMessage("创建中...");
  const reuseUpstreamKey = document.getElementById("reuseUpstreamKey")?.checked !== false;
  const payload = await SafetyHub.api("/admin/api/api-keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: inputValue("apiKeyName"),
      owner_user_id: inputValue("apiKeyOwner"),
      upstream_key: inputValue("apiKeyValue"),
      reuse_upstream_key: reuseUpstreamKey
    })
  });
  document.getElementById("apiKeyValue").value = "";
  setApiKeyMessage(reuseUpstreamKey ? "APIKey 已创建，列表仅展示前后缀。客户端可继续使用该中转站 Key 访问 SafetyHub。" : `APIKey 已创建，SafetyHub Key 仅展示一次：${payload.safetyhub_key}`);
  await loadApiKeys();
}

function toggleSafetyHubKeyInput() {
  const reuseUpstreamKey = document.getElementById("reuseUpstreamKey")?.checked !== false;
  const hint = document.getElementById("safetyhubGenerateHint");
  if (!hint) return;
  hint.classList.toggle("active", !reuseUpstreamKey);
}

async function replaceApiKey(apiKeyId) {
  const newKey = window.prompt("请输入新的中转站 Key。客户端使用的 SafetyHub Key 不会变化。");
  if (!newKey) return;
  await SafetyHub.api(`/admin/api/api-keys/${encodeURIComponent(apiKeyId)}/replace-upstream-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ new_upstream_key: newKey })
  });
  setApiKeyMessage("上游 Key 已替换，模式已切换为 K-Decoupled。");
  await loadApiKeys();
}

async function revokeApiKey(apiKeyId) {
  await SafetyHub.api(`/admin/api/api-keys/${encodeURIComponent(apiKeyId)}/revoke`, { method: "POST" });
  setApiKeyMessage("APIKey 已吊销。");
  await loadApiKeys();
}

async function bulkReplaceApiKeys() {
  const payload = await SafetyHub.api("/admin/api/api-keys/bulk-replace-upstream-keys", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csv_content: document.getElementById("bulkReplaceCsv")?.value || "" })
  });
  document.getElementById("bulkReplaceResult").textContent = SafetyHub.json(payload);
  await loadApiKeys();
}

function setApiKeyMessage(message) {
  const element = document.getElementById("apiKeyMessage");
  if (element) element.textContent = message;
}

async function loadSettings() {
  const health = await SafetyHub.api("/admin/api/health");
  document.getElementById("adminHealth").textContent = SafetyHub.json(health);
  const ops = await SafetyHub.api("/admin/api/admin-ops?limit=50");
  document.getElementById("adminOpsTable").innerHTML = ops.items.map((item) => `<tr><td>${item.id}</td><td>${item.admin_user || "-"}</td><td>${item.operation}</td><td>${item.resource_type}:${item.resource_id}</td><td>${SafetyHub.time(item.created_at)}</td></tr>`).join("");
}

async function loadPlaceholder() {
  const endpoint = document.body.dataset.endpoint;
  const payload = await SafetyHub.api(endpoint);
  document.getElementById("placeholderMessage").textContent = payload.message;
}

function setText(id, value) {
  const element = document.getElementById(id);
  if (element) element.textContent = SafetyHub.text(value);
}

function inputValue(id) {
  return document.getElementById(id)?.value.trim() || "";
}

function appendParam(params, key, value) {
  if (value) params.set(key, value);
}

function showError(error) {
  const main = document.querySelector("main.content");
  if (!main) return;
  const box = document.createElement("section");
  box.className = "card error";
  box.textContent = `加载失败：${error.message}`;
  main.prepend(box);
}
