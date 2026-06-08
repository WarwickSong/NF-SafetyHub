const SafetyHub = {
  version: "0.4.5",
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
  const payload = await SafetyHub.api("/admin/api/observations/recent?limit=5");
  const list = document.getElementById("observationsList");
  list.innerHTML = payload.items.map((item) => `<article class="stack-item" data-id="${item.id}"><h3>${item.request_id}</h3><p>${item.model || "-"} · ${item.action_taken} · ${SafetyHub.time(item.created_at)}</p><button class="button small secondary" data-load-observation="${item.id}">加载完整内容</button><pre class="observation-detail">${SafetyHub.json({ id: item.id, request_id: item.request_id, action_taken: item.action_taken, matched_rule_ids: item.matched_rule_ids, latency_ms: item.latency_ms })}</pre></article>`).join("");
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

async function setupApiKeysPage() {
  document.getElementById("createApiKey")?.addEventListener("click", createApiKey);
  document.getElementById("bulkReplaceApiKeys")?.addEventListener("click", bulkReplaceApiKeys);
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

async function loadApiKeys() {
  const payload = await SafetyHub.api("/admin/api/api-keys");
  const table = document.getElementById("apiKeysTable");
  table.innerHTML = payload.items.map((item) => renderApiKeyRow(item)).join("");
  table.querySelectorAll("button[data-action]").forEach((button) => button.addEventListener("click", async (event) => {
    event.stopPropagation();
    const row = button.closest("tr");
    const action = button.dataset.action;
    if (action === "copy") return copyApiKey(row.dataset.id);
    if (action === "reveal") return revealApiKey(row, button);
    if (action === "replace") return replaceApiKey(row.dataset.id);
    if (action === "revoke") return revokeApiKey(row.dataset.id);
    if (action === "delete") return deleteApiKey(row.dataset.id);
    if (action === "edit") return enterEditMode(row);
    if (action === "save") return saveApiKey(row);
    if (action === "cancel") return loadApiKeys();
  }));
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
    <td>${item.status}</td>
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
  await SafetyHub.api(`/admin/api/api-keys/${encodeURIComponent(row.dataset.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(fields)
  });
  setApiKeyMessage("APIKey 已更新。");
  await loadApiKeys();
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

async function deleteApiKey(apiKeyId) {
  if (!window.confirm("确认从 SafetyHub 删除这条已吊销的 APIKey 记录？此操作不会恢复。")) return;
  try {
    await SafetyHub.api(`/admin/api/api-keys/${encodeURIComponent(apiKeyId)}`, { method: "DELETE" });
    setApiKeyMessage("APIKey 本地记录已删除。");
    await loadApiKeys();
  } catch (error) {
    setApiKeyMessage(`删除失败：${error.message}`);
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
