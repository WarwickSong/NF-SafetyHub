const SafetyHub = {
  version: "0.4.6",
  async api(path, options = {}) {
    const response = await fetch(path, { headers: { Accept: "application/json", ...(options.headers || {}) }, ...options });
    if (!response.ok) {
      let detail = "";
      try {
        const payload = await response.json();
        detail = payload.detail || payload.message || "";
      } catch (error) {
        detail = await response.text().catch(() => "");
      }
      const message = detail ? `${response.status} ${response.statusText}: ${detail}` : `${response.status} ${response.statusText}`;
      throw new Error(message);
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
  if (page === "apiKeys") return setupApiKeysPage();
  if (page === "dataGovernance") return loadDataGovernance();
  if (page === "reports") return setupReportsPage();
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
  await Promise.all([loadDashboardStats(), loadDashboardRuntime()]);
}

async function loadDashboardStats() {
  const stats = await SafetyHub.api("/admin/api/stats");
  setText("todayRequests", stats.today_requests);
  setText("todayHits", stats.today_hits);
  setText("todayBlocks", stats.today_blocks);
  setText("totalRequests", stats.total_requests);
  const trend = document.getElementById("trend");
  if (trend) trend.innerHTML = stats.recent_trend.map((item) => `<div class="trend-item"><span>${item.date}</span><strong>请求 ${item.requests}</strong><strong>命中 ${item.hits}</strong><strong>拦截 ${item.blocked}</strong></div>`).join("");
}

async function loadDashboardRuntime() {
  try {
    renderRuntimeStatus(await SafetyHub.api("/admin/api/runtime"));
  } catch (error) {
    renderRuntimeStatus(null, error);
  }
}

function renderRuntimeStatus(runtime, error) {
  const target = document.getElementById("runtimeStatus");
  if (!target) return;
  if (!runtime) {
    target.innerHTML = `<div class="trend-item"><span>运行状态</span><strong>暂不可用</strong><strong>${error ? escapeHtml(error.message) : "请刷新重试"}</strong></div>`;
    return;
  }
  const v1 = runtime.v1_concurrency || {};
  const queue = runtime.archive_queue || {};
  const upstream = runtime.upstream || {};
  const diskItems = (runtime.disk_space || []).map(renderDiskSpaceItem);
  target.innerHTML = [
    `<div class="trend-item"><span>Worker</span><strong>PID ${runtime.worker_pid}</strong><strong>配置 ${runtime.configured_workers}</strong></div>`,
    `<div class="trend-item"><span>/v1 队列</span><strong>在途 ${SafetyHub.text(v1.inflight)}</strong><strong>排队 ${SafetyHub.text(v1.queue_size)}</strong><strong>上限 ${v1.max_inflight}/${v1.max_queue_size}</strong></div>`,
    `<div class="trend-item"><span>归档队列</span><strong>待写 ${SafetyHub.text(queue.queue_size)}</strong><strong>丢弃 ${SafetyHub.text(queue.dropped)}</strong><strong>已处理 ${SafetyHub.text(queue.processed)}</strong></div>`,
    `<div class="trend-item"><span>上游连接</span><strong>max ${upstream.max_connections}</strong><strong>keepalive ${upstream.max_keepalive_connections}</strong><strong>pool ${upstream.timeout_pool}s</strong></div>`,
    ...diskItems
  ].join("");
}

function renderDiskSpaceItem(item) {
  if (!item.available) {
    return `<div class="trend-item"><span>${escapeHtml(item.name)}</span><strong>不可用</strong><strong>${escapeHtml(item.path)}</strong><strong>${escapeHtml(item.error)}</strong></div>`;
  }
  return `<div class="trend-item"><span>${escapeHtml(item.name)}</span><strong>已用 ${formatBytes(item.used_bytes)} / ${formatBytes(item.total_bytes)}</strong><strong>剩余 ${formatBytes(item.free_bytes)}</strong><strong>${Number(item.used_percent || 0).toFixed(2)}%</strong><small>${escapeHtml(item.path)}</small></div>`;
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB", "PB"];
  const exponent = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1);
  const size = value / Math.pow(1024, exponent);
  return `${size.toFixed(size >= 10 || exponent === 0 ? 0 : 1)} ${units[exponent]}`;
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
  if (!payload.items.length) {
    table.innerHTML = `<tr><td colspan="6">暂无训练样本。新通过的 Chat 请求会写入训练数据池；拦截证据请查看“拦截审计”。</td></tr>`;
    document.getElementById("archiveDetail").textContent = "";
    return;
  }
  table.innerHTML = payload.items.map((item) => `<tr data-id="${item.id}"><td>${item.id}</td><td>${item.request_id}</td><td>${SafetyHub.text(item.model)}</td><td><span class="tag">${item.action_taken}</span></td><td>${item.is_desensitized ? "已脱敏" : "原样"}</td><td>${SafetyHub.time(item.created_at)}</td></tr>`).join("");
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
  const payload = await SafetyHub.api("/admin/api/observations/recent?limit=5");
  const list = document.getElementById("observationsList");
  if (!payload.items.length) {
    list.innerHTML = `<article class="stack-item"><h3>暂无上线观测样本</h3><p>新通过的 Chat 请求进入训练数据池后，会在这里展示最近样本。</p></article>`;
    return;
  }
  list.innerHTML = payload.items.map((item) => `<article class="stack-item" data-id="${item.id}"><h3>${item.request_id}</h3><p>${item.model || "-"} · ${item.action_taken} · ${SafetyHub.time(item.created_at)}</p><button class="button small secondary" data-load-observation="${item.id}">加载样本内容</button><pre class="observation-detail">${SafetyHub.json({ id: item.id, request_id: item.request_id, action_taken: item.action_taken, is_desensitized: item.is_desensitized })}</pre></article>`).join("");
  list.querySelectorAll("button[data-load-observation]").forEach((button) => button.addEventListener("click", async () => {
    const detail = await SafetyHub.api(`/admin/api/archives/${button.dataset.loadObservation}`);
    const article = button.closest("article");
    const pre = article?.querySelector(".observation-detail");
    if (pre) pre.textContent = SafetyHub.json({ original: detail.messages_original, desensitized: detail.messages_desensitized, response: detail.response });
    button.remove();
  }));
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
  try {
    const payload = await SafetyHub.api(`/admin/api/rules/${encodeURIComponent(ruleId)}/toggle`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled })
    });
    setRulesMessage(`${payload.rule.id} 已${payload.rule.enabled ? "启用" : "停用"}，热加载${payload.reloaded ? "已完成" : "未触发"}`);
    await loadRules();
  } catch (error) {
    setRulesMessage(`操作失败：${error ? error.message : "未知错误"}。若为内网部署，请检查 rules_config.yaml 是否对应用运行用户可写。`);
  }
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

const apiKeyListState = {
  page: 1,
  limit: 20,
  total: 0,
  search: "",
  status: ""
};

async function setupApiKeysPage() {
  document.getElementById("createApiKey")?.addEventListener("click", createApiKey);
  document.getElementById("bulkReplaceApiKeys")?.addEventListener("click", bulkReplaceApiKeys);
  bindApiKeyListControls();
  ensureApiKeyModal();
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeApiKeyModal();
  });
  const reuseUpstreamKey = document.getElementById("reuseUpstreamKey");
  if (reuseUpstreamKey) reuseUpstreamKey.onchange = toggleSafetyHubKeyInput;
  const createMode = document.getElementById("apiKeyCreateMode");
  if (createMode) createMode.onchange = toggleSafetyHubKeyInput;
  toggleSafetyHubKeyInput();
  await loadApiKeys();
}

function bindApiKeyListControls() {
  const applyButton = document.getElementById("applyApiKeyFilters");
  if (applyButton && applyButton.dataset.bound !== "true") {
    applyButton.dataset.bound = "true";
    applyButton.addEventListener("click", () => applyApiKeyFilters());
  }
  const resetButton = document.getElementById("resetApiKeyFilters");
  if (resetButton && resetButton.dataset.bound !== "true") {
    resetButton.dataset.bound = "true";
    resetButton.addEventListener("click", () => resetApiKeyFilters());
  }
  const searchInput = document.getElementById("apiKeySearch");
  if (searchInput && searchInput.dataset.bound !== "true") {
    searchInput.dataset.bound = "true";
    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") applyApiKeyFilters();
    });
  }
  const statusSelect = document.getElementById("apiKeyStatus");
  if (statusSelect && statusSelect.dataset.bound !== "true") {
    statusSelect.dataset.bound = "true";
    statusSelect.addEventListener("change", () => applyApiKeyFilters());
  }
  const pageSizeSelect = document.getElementById("apiKeyPageSize");
  if (pageSizeSelect && pageSizeSelect.dataset.bound !== "true") {
    pageSizeSelect.dataset.bound = "true";
    pageSizeSelect.addEventListener("change", () => {
      apiKeyListState.limit = normalizeApiKeyLimit(pageSizeSelect.value);
      apiKeyListState.page = 1;
      loadApiKeys();
    });
  }
}

function applyApiKeyFilters() {
  apiKeyListState.search = inputValue("apiKeySearch");
  apiKeyListState.status = inputValue("apiKeyStatus");
  apiKeyListState.limit = normalizeApiKeyLimit(document.getElementById("apiKeyPageSize")?.value);
  apiKeyListState.page = 1;
  return loadApiKeys();
}

function resetApiKeyFilters() {
  const searchInput = document.getElementById("apiKeySearch");
  const statusSelect = document.getElementById("apiKeyStatus");
  const pageSizeSelect = document.getElementById("apiKeyPageSize");
  if (searchInput) searchInput.value = "";
  if (statusSelect) statusSelect.value = "";
  if (pageSizeSelect) pageSizeSelect.value = "20";
  apiKeyListState.page = 1;
  apiKeyListState.limit = 20;
  apiKeyListState.total = 0;
  apiKeyListState.search = "";
  apiKeyListState.status = "";
  return loadApiKeys();
}

async function loadApiKeys(page) {
  apiKeyListState.page = Math.max(1, Number(page || apiKeyListState.page || 1));
  apiKeyListState.limit = normalizeApiKeyLimit(apiKeyListState.limit);
  const params = new URLSearchParams();
  params.set("limit", String(apiKeyListState.limit));
  params.set("offset", String((apiKeyListState.page - 1) * apiKeyListState.limit));
  appendParam(params, "search", apiKeyListState.search);
  appendParam(params, "status", apiKeyListState.status);
  const payload = await SafetyHub.api(`/admin/api/api-keys?${params}`);
  apiKeyListState.total = payload.pagination?.total || 0;
  const totalPages = getApiKeyTotalPages();
  if (apiKeyListState.page > totalPages) return loadApiKeys(totalPages);
  const table = document.getElementById("apiKeysTable");
  table.innerHTML = payload.items.length ? payload.items.map((item) => renderApiKeyRow(item)).join("") : `<tr><td colspan="7">暂无匹配的 APIKey。</td></tr>`;
  table.querySelectorAll("button[data-action]").forEach((button) => button.addEventListener("click", async (event) => {
    event.stopPropagation();
    const row = button.closest("tr");
    const action = button.dataset.action;
    if (action === "copy") return copyApiKey(row.dataset.id);
    if (action === "reveal") return revealApiKey(row, button);
    if (action === "replace") return replaceApiKey(row.dataset.id);
    if (action === "revoke") return revokeApiKey(row.dataset.id);
    if (action === "delete") return deleteApiKey(row.dataset.id, button);
    if (action === "edit") return enterEditMode(row);
    if (action === "save") return saveApiKey(row);
    if (action === "cancel") return loadApiKeys();
  }));
  renderApiKeyPagination();
}

function normalizeApiKeyLimit(value) {
  const limit = Number(value);
  return [20, 50, 100].includes(limit) ? limit : 20;
}

function getApiKeyTotalPages() {
  return Math.max(1, Math.ceil(apiKeyListState.total / apiKeyListState.limit));
}

function renderApiKeyPagination() {
  const target = document.getElementById("apiKeyPaginationTop");
  if (!target) return;
  const totalPages = getApiKeyTotalPages();
  const start = apiKeyListState.total === 0 ? 0 : (apiKeyListState.page - 1) * apiKeyListState.limit + 1;
  const end = Math.min(apiKeyListState.total, apiKeyListState.page * apiKeyListState.limit);
  target.innerHTML = `<div class="pagination-summary">共 ${apiKeyListState.total} 条，当前 ${start}-${end} 条，第 ${apiKeyListState.page} / ${totalPages} 页</div>
    <div class="pagination-actions">
      <button class="button small secondary" data-api-key-page="prev">上一页</button>
      <label class="page-jump">跳到 <input id="apiKeyPageInput" type="number" min="1" max="${totalPages}" value="${apiKeyListState.page}"> 页</label>
      <button class="button small secondary" data-api-key-page="go">跳转</button>
      <button class="button small secondary" data-api-key-page="next">下一页</button>
    </div>`;
  target.querySelector('[data-api-key-page="prev"]').disabled = apiKeyListState.page <= 1;
  target.querySelector('[data-api-key-page="next"]').disabled = apiKeyListState.page >= totalPages;
  target.querySelector('[data-api-key-page="prev"]').addEventListener("click", () => loadApiKeys(apiKeyListState.page - 1));
  target.querySelector('[data-api-key-page="next"]').addEventListener("click", () => loadApiKeys(apiKeyListState.page + 1));
  target.querySelector('[data-api-key-page="go"]').addEventListener("click", () => jumpApiKeyPage(totalPages));
  target.querySelector("#apiKeyPageInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") jumpApiKeyPage(totalPages);
  });
}

function jumpApiKeyPage(totalPages) {
  const input = document.getElementById("apiKeyPageInput");
  const page = Math.min(totalPages, Math.max(1, Number(input?.value || 1)));
  return loadApiKeys(page);
}

function renderApiKeyRow(item) {
  const masked = `${item.key_prefix}******${item.key_suffix}`;
  const upstream = SafetyHub.text(item.upstream_key_prefix);
  const mode = item.is_decoupled ? "K-Decoupled" : "K-Sync";
  const expires = item.expires_at ? new Date(item.expires_at).toISOString().slice(0, 16) : "";
  const deleteButton = item.status === "revoked" ? '<button class="button small secondary" data-action="delete">删除</button>' : "";
  const itemJson = encodeURIComponent(JSON.stringify({
    name: item.name || "",
    owner_user_id: item.owner_user_id || "",
    owner_department: item.owner_department || "",
    cost_center: item.cost_center || "",
    expires_at: item.expires_at || ""
  }));
  return `<tr data-id="${item.id}" data-masked="${masked}" data-item="${itemJson}">
    <td data-field="name">
      <div class="cell-display"><strong>${SafetyHub.text(item.name)}</strong></div>
      <div class="cell-edit"><input data-edit="name" value="${escapeAttr(item.name || "")}" placeholder="名称"></div>
    </td>
    <td data-field="owner">
      <div class="cell-display">
        <div>${SafetyHub.text(item.owner_user_id)}</div>
        <div class="cell-sub">${SafetyHub.text(item.owner_department)} · ${SafetyHub.text(item.cost_center)}</div>
      </div>
      <div class="cell-edit cell-edit-stack">
        <input data-edit="owner_user_id" value="${escapeAttr(item.owner_user_id || "")}" placeholder="所属用户">
        <input data-edit="owner_department" value="${escapeAttr(item.owner_department || "")}" placeholder="部门（可选）">
        <input data-edit="cost_center" value="${escapeAttr(item.cost_center || "")}" placeholder="成本中心（可选）">
      </div>
    </td>
    <td>
      <span data-key-display>${masked}</span>
      <div class="cell-actions">
        <button class="button small secondary" data-action="copy">复制</button>
        <button class="button small secondary" data-action="reveal">显示</button>
      </div>
    </td>
    <td>
      <span class="tag">${mode}</span>
      <div class="cell-sub">上游：${upstream}</div>
      <div class="cell-sub">${SafetyHub.text(item.provider_name)}</div>
    </td>
    <td><span class="tag ${item.status === "active" ? "success" : item.status === "revoked" ? "danger" : "neutral"}">${item.status}</span></td>
    <td data-field="expires_at">
      <div class="cell-display">${item.expires_at ? SafetyHub.time(item.expires_at) : "-"}</div>
      <div class="cell-edit"><input type="datetime-local" data-edit="expires_at" value="${expires}"></div>
    </td>
    <td>
      <div class="cell-actions cell-actions-stack">
        <div class="cell-display-actions">
          <button class="button small secondary" data-action="edit">编辑</button>
          <button class="button small secondary" data-action="replace">替换上游</button>
          <button class="button small secondary" data-action="revoke">吊销</button>
          ${deleteButton}
        </div>
        <div class="cell-edit-actions">
          <button class="button small" data-action="save">保存</button>
          <button class="button small secondary" data-action="cancel">取消</button>
        </div>
      </div>
    </td>
  </tr>`;
}

function escapeAttr(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function enterEditMode(row) {
  row.classList.add("editing");
}

async function saveApiKey(row) {
  const original = JSON.parse(decodeURIComponent(row.dataset.item || "%7B%7D"));
  const fields = {};
  row.querySelectorAll("input[data-edit]").forEach((input) => {
    const name = input.dataset.edit;
    const value = input.value.trim();
    if (name === "expires_at") {
      const normalized = value ? new Date(value).toISOString() : null;
      const baseline = original.expires_at || null;
      if (normalized !== baseline) fields[name] = normalized;
      return;
    }
    if (value !== (original[name] || "")) {
      if (name === "name" || name === "owner_user_id") {
        if (!value) return;
      }
      fields[name] = value || null;
    }
  });
  if (Object.keys(fields).length === 0) {
    setApiKeyMessage("没有需要保存的修改。");
    row.classList.remove("editing");
    return;
  }
  setApiKeyMessage("保存中...");
  try {
    await SafetyHub.api(`/admin/api/api-keys/${encodeURIComponent(row.dataset.id)}/update`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fields)
    });
    setApiKeyMessage("APIKey 已更新。");
    await loadApiKeys();
  } catch (error) {
    // 任何失败（401 会话失效、422 校验错误、500 等）都要把状态恢复并提示用户，
    // 否则按钮会一直停在“保存中...”，看起来像页面卡死。
    setApiKeyMessage(`保存失败：${error.message}`);
    row.classList.remove("editing");
  }
}

async function createApiKey() {
  const button = document.getElementById("createApiKey");
  if (button?.disabled) return;
  showApiKeyModal("APIKey 创建", "正在创建 APIKey，请稍候...");
  setButtonBusy(button, true, "创建中...");
  try {
    const reuseUpstreamKey = document.getElementById("reuseUpstreamKey")?.checked !== false;
    const createMode = document.getElementById("apiKeyCreateMode")?.value || "manual";
    const payload = await SafetyHub.api("/admin/api/api-keys", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: inputValue("apiKeyName"),
        owner_user_id: inputValue("apiKeyOwner"),
        upstream_key: createMode === "manual" ? inputValue("apiKeyValue") : "",
        reuse_upstream_key: reuseUpstreamKey,
        create_mode: createMode
      })
    });
    document.getElementById("apiKeyValue").value = "";
    showApiKeyModal(
      "APIKey 创建成功",
      payload.safetyhub_key ? "APIKey 已创建，请复制并妥善保存。" : "APIKey 已创建，列表仅展示前后缀，可按需点击显示或复制完整 Key。",
      payload.safetyhub_key
    );
    await loadApiKeys();
  } catch (error) {
    showApiKeyModal("APIKey 创建失败", error.message);
  } finally {
    setButtonBusy(button, false);
  }
}

function toggleSafetyHubKeyInput() {
  const reuseUpstreamKey = document.getElementById("reuseUpstreamKey")?.checked !== false;
  const createMode = document.getElementById("apiKeyCreateMode")?.value || "manual";
  const keyInput = document.getElementById("apiKeyValue");
  const hint = document.getElementById("safetyhubGenerateHint");
  if (keyInput) keyInput.disabled = createMode === "provider";
  if (hint) hint.classList.toggle("active", !reuseUpstreamKey || createMode === "provider");
}

async function revealSecret(apiKeyId) {
  return SafetyHub.api(`/admin/api/api-keys/${encodeURIComponent(apiKeyId)}/reveal`, { method: "POST" });
}

async function copyApiKey(apiKeyId) {
  try {
    const payload = await revealSecret(apiKeyId);
    const copied = await copyText(payload.key);
    setApiKeyMessage(copied ? "完整 Key 已复制，本次操作已记录审计。" : "浏览器未允许自动复制，完整 Key 已显示，请手动复制。");
    if (!copied) showApiKeyModal("请手动复制 APIKey", "浏览器未允许自动写入剪贴板，请从下方复制完整 Key。", payload.key);
  } catch (error) {
    setApiKeyMessage(`复制失败：${error.message}`);
  }
}

async function revealApiKey(row, button) {
  const display = row.querySelector("[data-key-display]");
  if (button.dataset.visible === "true") {
    display.textContent = row.dataset.masked;
    button.dataset.visible = "false";
    button.textContent = "显示";
    return;
  }
  const payload = await revealSecret(row.dataset.id);
  display.textContent = payload.key;
  button.dataset.visible = "true";
  button.textContent = "隐藏";
  setApiKeyMessage("完整 Key 已显示，本次操作已记录审计。");
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
  setApiKeyMessage("APIKey 已吊销，可在列表中点击删除移除本地记录。");
  await loadApiKeys();
}

async function deleteApiKey(apiKeyId, button) {
  if (button?.disabled) return;
  if (!window.confirm("确认从 SafetyHub 删除这条已吊销的 APIKey 记录？此操作不会恢复。")) return;
  setButtonBusy(button, true, "删除中...");
  setApiKeyMessage("删除中...");
  try {
    await SafetyHub.api(`/admin/api/api-keys/${encodeURIComponent(apiKeyId)}/delete`, { method: "POST" });
    setApiKeyMessage("APIKey 本地记录已删除。");
    await loadApiKeys();
  } catch (error) {
    setApiKeyMessage(`删除失败：${error.message}`);
    setButtonBusy(button, false);
  }
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

function ensureApiKeyModal() {
  if (document.getElementById("apiKeyModal")) {
    bindApiKeyModalEvents();
    return;
  }
  document.body.insertAdjacentHTML("beforeend", `<div class="modal" id="apiKeyModal" role="dialog" aria-modal="true" aria-labelledby="apiKeyModalTitle" hidden>
    <div class="modal-panel">
      <div class="modal-header">
        <h2 id="apiKeyModalTitle">APIKey 创建</h2>
        <button class="modal-close" type="button" data-modal-close aria-label="关闭">×</button>
      </div>
      <p class="modal-message" id="apiKeyModalMessage"></p>
      <div class="secret-box" id="apiKeySecretWrap" hidden>
        <span>完整 APIKey</span>
        <code id="apiKeyModalSecret"></code>
      </div>
      <div class="modal-actions">
        <button class="button secondary" type="button" id="apiKeyModalCopy" hidden>复制 Key</button>
        <button class="button" type="button" data-modal-close>关闭</button>
      </div>
    </div>
  </div>`);
  bindApiKeyModalEvents();
}

function bindApiKeyModalEvents() {
  document.querySelectorAll("[data-modal-close]").forEach((button) => {
    if (button.dataset.bound === "true") return;
    button.dataset.bound = "true";
    button.addEventListener("click", closeApiKeyModal);
  });
  const modal = document.getElementById("apiKeyModal");
  if (modal && modal.dataset.bound !== "true") {
    modal.dataset.bound = "true";
    modal.addEventListener("click", (event) => {
      if (event.target.id === "apiKeyModal") closeApiKeyModal();
    });
  }
  const copyButton = document.getElementById("apiKeyModalCopy");
  if (copyButton && copyButton.dataset.bound !== "true") {
    copyButton.dataset.bound = "true";
    copyButton.addEventListener("click", copyCreatedApiKey);
  }
}

function showApiKeyModal(title, message, secret) {
  ensureApiKeyModal();
  const modal = document.getElementById("apiKeyModal");
  const titleElement = document.getElementById("apiKeyModalTitle");
  const messageElement = document.getElementById("apiKeyModalMessage");
  const secretWrap = document.getElementById("apiKeySecretWrap");
  const secretElement = document.getElementById("apiKeyModalSecret");
  const copyButton = document.getElementById("apiKeyModalCopy");
  if (!modal) return;
  if (titleElement) titleElement.textContent = title;
  if (messageElement) messageElement.textContent = message;
  if (secretWrap) secretWrap.hidden = !secret;
  if (secretElement) secretElement.textContent = secret || "";
  if (copyButton) {
    copyButton.hidden = !secret;
    copyButton.dataset.key = secret || "";
    copyButton.textContent = "复制 Key";
  }
  modal.hidden = false;
  modal.removeAttribute("hidden");
  modal.classList.add("active");
}

function closeApiKeyModal() {
  const modal = document.getElementById("apiKeyModal");
  if (!modal) return;
  modal.hidden = true;
  modal.setAttribute("hidden", "");
  modal.classList.remove("active");
}

async function copyCreatedApiKey() {
  const button = document.getElementById("apiKeyModalCopy");
  const key = button?.dataset.key || "";
  if (!key) return;
  const copied = await copyText(key);
  button.textContent = copied ? "已复制" : "请手动复制";
}

async function copyText(text) {
  if (!text) return false;
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch (error) {
      return copyTextFallback(text);
    }
  }
  return copyTextFallback(text);
}

function copyTextFallback(text) {
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (error) {
    copied = false;
  }
  textarea.remove();
  return copied;
}

function setButtonBusy(button, busy, label) {
  if (!button) return;
  if (!button.dataset.defaultText) button.dataset.defaultText = button.textContent;
  button.disabled = busy;
  button.textContent = busy ? label : button.dataset.defaultText;
}

async function loadDataGovernance() {
  bindDataGovernanceControls();
  await Promise.all([loadDataGovernanceSummary(), loadCoverageStatus()]);
}

function bindDataGovernanceControls() {
  const previewButton = document.getElementById("previewDataCleanup");
  const cleanupButton = document.getElementById("runDataCleanup");
  const coverageButton = document.getElementById("runCoverageAnalysis");
  if (previewButton && previewButton.dataset.bound !== "true") {
    previewButton.dataset.bound = "true";
    previewButton.addEventListener("click", () => previewDataCleanup());
  }
  if (cleanupButton && cleanupButton.dataset.bound !== "true") {
    cleanupButton.dataset.bound = "true";
    cleanupButton.addEventListener("click", () => runDataCleanup());
  }
  if (coverageButton && coverageButton.dataset.bound !== "true") {
    coverageButton.dataset.bound = "true";
    coverageButton.addEventListener("click", () => runCoverageAnalysis());
  }
}

async function loadDataGovernanceSummary() {
  const target = document.getElementById("dataGovernanceSummary");
  if (!target) return;
  const summary = await SafetyHub.api("/admin/api/data-governance/summary");
  target.innerHTML = [
    `<div class="governance-summary-card"><span>训练数据</span><div><strong>总量 ${summary.training_total}</strong><strong>有效 ${summary.training_active}</strong><strong>待分析 ${summary.training_pending_analysis}</strong><strong>被覆盖 ${summary.training_covered}</strong><strong>过期 ${summary.training_expired}</strong></div></div>`,
    `<div class="governance-summary-card"><span>审计数据</span><div><strong>总量 ${summary.audit_total}</strong><strong>过期 ${summary.audit_expired}</strong></div></div>`,
    `<div class="governance-summary-card"><span>治理任务</span><div><strong>${summary.running_job ? `运行中 #${summary.running_job.id}` : "无运行任务"}</strong><strong>${summary.running_job ? `已处理 ${summary.running_job.processed_count}` : "可手动启动"}</strong></div></div>`,
    `<div class="governance-summary-card"><span>追溯期</span><div><strong>训练 ${summary.archive_retention_days} 天</strong><strong>审计 ${summary.audit_retention_days} 天</strong></div></div>`
  ].join("");
}

function coveragePayload() {
  const maxMinutes = Math.min(60, Math.max(1, Number(inputValue("coverageMaxMinutes") || 10)));
  return {
    max_records: Math.min(100000, Math.max(1, Number(inputValue("coverageMaxRecords") || 5000))),
    max_seconds: maxMinutes * 60,
    batch_size: Math.min(5000, Math.max(1, Number(inputValue("coverageBatchSize") || 200))),
    batch_sleep_ms: Math.min(5000, Math.max(0, Number(inputValue("coverageBatchSleepMs") || 200)))
  };
}

function coverageResultText(response) {
  const parts = [
    `任务 #${SafetyHub.text(response.job_id)}`,
    `状态：${SafetyHub.text(response.status)}`,
    `已处理：${SafetyHub.text(response.processed_count)}`,
    `已标记：${SafetyHub.text(response.marked_count)}`,
    `游标：${SafetyHub.text(response.cursor_value)}`
  ];
  if (response.error) parts.push("任务返回异常，请查看服务日志。");
  return parts.join("\n");
}

async function loadCoverageStatus() {
  const target = document.getElementById("coverageStatus");
  if (!target) return;
  const status = await SafetyHub.api("/admin/api/data-governance/coverage/status");
  if (!status.id) {
    target.innerHTML = `<div class="governance-status-card"><span>当前任务</span><strong>暂无任务</strong><strong>可手动启动</strong></div>`;
    return;
  }
  target.innerHTML = `<div class="governance-status-card"><span>最近任务 #${status.id}</span><strong>${status.status}</strong><strong>已处理 ${status.processed_count}</strong><strong>标记 ${status.marked_count}</strong><strong>游标 ${status.cursor_value || "-"}</strong></div>`;
}

async function runCoverageAnalysis() {
  const result = document.getElementById("coverageResult");
  result.textContent = "正在执行覆盖分析...";
  try {
    const response = await SafetyHub.api("/admin/api/data-governance/coverage/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(coveragePayload())
    });
    result.textContent = coverageResultText(response);
    await Promise.all([loadDataGovernanceSummary(), loadCoverageStatus()]);
  } catch (error) {
    result.textContent = "覆盖分析启动失败，请稍后重试或查看服务日志。";
  }
}

function dataCleanupPayload() {
  return {
    include_training_covered: document.getElementById("cleanupTrainingCovered")?.checked === true,
    include_training_expired: document.getElementById("cleanupTrainingExpired")?.checked !== false,
    include_audit_expired: document.getElementById("cleanupAuditExpired")?.checked !== false,
    limit: Math.min(10000, Math.max(1, Number(inputValue("cleanupLimit") || 1000)))
  };
}

async function previewDataCleanup() {
  const result = document.getElementById("dataGovernanceResult");
  result.textContent = "正在预览...";
  const payload = await SafetyHub.api("/admin/api/data-governance/cleanup/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(dataCleanupPayload())
  });
  result.textContent = SafetyHub.json(payload);
  await loadDataGovernanceSummary();
}

async function runDataCleanup() {
  const result = document.getElementById("dataGovernanceResult");
  const payload = dataCleanupPayload();
  if (!payload.include_training_covered && !payload.include_training_expired && !payload.include_audit_expired) {
    result.textContent = "请至少选择一种清理范围。";
    return;
  }
  result.textContent = "正在执行清理...";
  const response = await SafetyHub.api("/admin/api/data-governance/cleanup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  result.textContent = SafetyHub.json(response);
  await loadDataGovernanceSummary();
}

async function loadSettings() {
  await loadAdminSettings();
  document.getElementById("saveTrainingCapture")?.addEventListener("click", saveTrainingCaptureSetting);
  const health = await SafetyHub.api("/admin/api/health");
  document.getElementById("adminHealth").textContent = SafetyHub.json(health);
  const ops = await SafetyHub.api("/admin/api/admin-ops?limit=50");
  document.getElementById("adminOpsTable").innerHTML = ops.items.map((item) => `<tr><td>${item.id}</td><td>${item.admin_user || "-"}</td><td>${item.operation}</td><td>${item.resource_type}:${item.resource_id}</td><td>${SafetyHub.time(item.created_at)}</td></tr>`).join("");
}

async function setupReportsPage() {
  bindReportsControls();
  initializeReportPeriod();
  await loadReports();
}

function bindReportsControls() {
  const generateButton = document.getElementById("generateReport");
  if (generateButton && generateButton.dataset.bound !== "true") {
    generateButton.dataset.bound = "true";
    generateButton.addEventListener("click", generateReport);
  }
  const sampleButton = document.getElementById("sampleRuntime");
  if (sampleButton && sampleButton.dataset.bound !== "true") {
    sampleButton.dataset.bound = "true";
    sampleButton.addEventListener("click", sampleRuntime);
  }
  const filterButton = document.getElementById("applyReportFilters");
  if (filterButton && filterButton.dataset.bound !== "true") {
    filterButton.dataset.bound = "true";
    filterButton.addEventListener("click", loadReports);
  }
  const typeSelect = document.getElementById("reportType");
  if (typeSelect && typeSelect.dataset.bound !== "true") {
    typeSelect.dataset.bound = "true";
    typeSelect.addEventListener("change", initializeReportPeriod);
  }
}

function initializeReportPeriod() {
  const input = document.getElementById("reportPeriod");
  if (!input || input.value) return;
  const date = new Date();
  date.setDate(date.getDate() - 1);
  input.value = date.toISOString().slice(0, 10);
}

async function loadReports() {
  const params = new URLSearchParams();
  appendParam(params, "report_type", inputValue("reportFilterType"));
  appendParam(params, "status", inputValue("reportFilterStatus"));
  const payload = await SafetyHub.api(`/admin/api/reports?${params}`);
  const table = document.getElementById("reportsTable");
  if (!table) return;
  table.innerHTML = payload.items.length ? payload.items.map(renderReportRow).join("") : `<tr><td colspan="7">暂无报表。</td></tr>`;
}

function renderReportRow(item) {
  const summary = item.summary || {};
  const files = item.files || {};
  const period = `${SafetyHub.time(item.period_start)} 至 ${SafetyHub.time(item.period_end)}`;
  const downloads = ["pdf", "xlsx", "csv"].filter((format) => files[format]).map((format) => `<a class="button small secondary" href="/admin/api/reports/${item.id}/download?format=${format}">${format.toUpperCase()}</a>`).join(" ") || "-";
  return `<tr><td>${item.id}</td><td>${reportTypeLabel(item.report_type)}</td><td>${period}</td><td><span class="tag ${item.status === "failed" ? "danger" : ""}">${item.status}</span></td><td>请求 ${SafetyHub.text(summary.total_requests)} / 事件 ${SafetyHub.text(summary.security_events)} / 拦截 ${SafetyHub.text(summary.blocked)}</td><td>${SafetyHub.time(item.generated_at || item.created_at)}</td><td>${downloads}</td></tr>`;
}

async function generateReport() {
  const result = document.getElementById("reportGenerateResult");
  const payload = reportGeneratePayload();
  if (!payload.period) {
    result.textContent = "请选择周期。";
    return;
  }
  result.textContent = "正在生成报表...";
  try {
    const response = await SafetyHub.api("/admin/api/reports/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    result.textContent = `生成完成：报表 #${response.item.id}`;
    await loadReports();
  } catch (error) {
    result.textContent = `生成失败：${error.message}`;
  }
}

function reportGeneratePayload() {
  const reportType = inputValue("reportType") || "daily";
  const dateValue = inputValue("reportPeriod");
  let period = dateValue;
  if (reportType === "weekly" && dateValue) {
    period = isoWeekValue(dateValue);
  }
  if (reportType === "monthly" && dateValue) {
    period = dateValue.slice(0, 7);
  }
  return { report_type: reportType, period, include_sensitive: document.getElementById("reportIncludeSensitive")?.checked === true };
}

function isoWeekValue(dateValue) {
  const date = new Date(`${dateValue}T00:00:00Z`);
  const day = date.getUTCDay() || 7;
  date.setUTCDate(date.getUTCDate() + 4 - day);
  const yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
  const week = Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  return `${date.getUTCFullYear()}-W${String(week).padStart(2, "0")}`;
}

async function sampleRuntime() {
  const result = document.getElementById("reportGenerateResult");
  result.textContent = "正在写入运行状态采样...";
  await SafetyHub.api("/admin/api/reports/runtime-samples", { method: "POST" });
  result.textContent = "运行状态采样已写入。";
}

function reportTypeLabel(value) {
  return { daily: "日报", weekly: "周报", monthly: "月报" }[value] || value;
}

async function loadAdminSettings() {
  const settings = await SafetyHub.api("/admin/api/settings");
  const checkbox = document.getElementById("trainingCaptureEnabled");
  if (checkbox) checkbox.checked = Boolean(settings.training_capture_enabled);
  setTrainingCaptureStatus(settings.training_capture_enabled);
}

async function saveTrainingCaptureSetting() {
  const checkbox = document.getElementById("trainingCaptureEnabled");
  const status = document.getElementById("trainingCaptureStatus");
  if (!checkbox || !status) return;
  status.textContent = "保存中...";
  const response = await SafetyHub.api("/admin/api/settings/training-capture", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled: checkbox.checked })
  });
  setTrainingCaptureStatus(response.training_capture_enabled, "已保存");
}

function setTrainingCaptureStatus(enabled, prefix = "当前状态") {
  const status = document.getElementById("trainingCaptureStatus");
  if (status) status.textContent = `${prefix}：${enabled ? "已开启" : "已关闭"}`;
}

async function loadPlaceholder() {
  const endpoint = document.body.dataset.endpoint;
  const payload = await SafetyHub.api(endpoint);
  document.getElementById("placeholderMessage").textContent = payload.message;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
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
