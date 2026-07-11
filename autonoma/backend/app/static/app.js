// Autonoma command-center dashboard — vanilla JS, zero build step.
const API = "/api/v1";
const $ = (s) => document.querySelector(s);
const el = (t, c) => { const e = document.createElement(t); if (c) e.className = c; return e; };

async function api(path, opts) {
  const r = await fetch(API + path, {
    headers: { "Content-Type": "application/json" }, ...opts,
  });
  if (!r.ok && r.status !== 204) throw new Error((await r.text()) || r.status);
  return r.status === 204 ? null : r.json();
}

// ---- Accent theming ----
document.querySelectorAll(".swatch").forEach((b) =>
  b.addEventListener("click", () => {
    document.documentElement.setAttribute("data-accent", b.dataset.accent);
    localStorage.setItem("accent", b.dataset.accent);
  })
);
const savedAccent = localStorage.getItem("accent");
if (savedAccent) document.documentElement.setAttribute("data-accent", savedAccent);

// ---- Live event stream (WebSocket, falls back to polling) ----
let ws;
function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}${API}/monitor/events/ws`);
  ws.onopen = () => $("#conn").className = "conn online";
  ws.onclose = () => { $("#conn").className = "conn offline"; setTimeout(connect, 2000); };
  ws.onmessage = (ev) => handleEvent(JSON.parse(ev.data));
}

const AUDIT_KINDS = new Set(["audit"]);
function handleEvent(e) {
  if (e.event_type === "audit") pushAudit(e, "");
  else pushAudit(e, kindClass(e.event_type));
  // Any state-changing event refreshes the relevant panels (debounced).
  scheduleRefresh();
}
function kindClass(t) {
  if (t.includes("error") || t.includes("failed") || t.includes("stuck")) return "err";
  if (t.includes("approval") || t.includes("waiting")) return "appr";
  return "";
}

function pushAudit(e, cls) {
  const feed = $("#audit-feed");
  const row = el("div", "audit-row " + cls);
  const time = (e.timestamp || "").split("T")[1]?.replace("Z", "") || "";
  const msg = e.message || e.detail || e.action || "";
  const extra = e.verified === false ? " ⚠unverified" : e.verified === true ? " ✓" : "";
  row.innerHTML = `<span class="t">${time}</span><span class="ty">${e.event_type}</span><span class="m">${escape(msg)}${extra}</span>`;
  feed.prepend(row);
  while (feed.children.length > 120) feed.removeChild(feed.lastChild);
}
function escape(s) { return String(s).replace(/[<>&]/g, (c) => ({ "<": "&lt;", ">": "&gt;", "&": "&amp;" }[c])); }

let refreshTimer;
function scheduleRefresh() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(refreshAll, 250);
}

// ---- Panels ----
async function refreshTasks() {
  const tasks = await api("/monitor/tasks");
  const wrap = $("#task-cards");
  wrap.innerHTML = "";
  if (!tasks.length) { wrap.innerHTML = '<div class="empty">No tasks yet. Create one to begin.</div>'; return; }
  for (const t of tasks) {
    const card = el("div", "task-card");
    const collab = t.coordination_mode === "collaborative";
    card.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:start">
        <div class="tc-title">${escape(t.title)}</div>
        <span class="status ${t.status}">${t.status.replace("_", " ")}</span>
      </div>
      <div class="tc-id">${t.task_id}</div>
      <div class="tc-row"><span>step ${t.current_step ?? "–"}</span><span>${t.current_skill ?? "no skill"}${t.current_skill_version ? " v" + t.current_skill_version : ""}</span></div>
      <div class="tc-row"><span>agents: ${(t.assigned_agents || []).join(", ") || "–"}</span><span>${t.input_behavior_mode}</span></div>
      <div class="tc-row"><span>last: ${escape(t.last_action ?? "–")}</span><span>next: ${escape(t.next_action ?? "–")}</span></div>
      <div class="progress"><i style="width:${Math.round((t.progress || 0) * 100)}%"></i></div>
      <div class="tc-meta">
        <span class="badge ${collab ? "collab" : ""}">${collab ? "collaborative" : "independent"}</span>
        ${t.error ? `<span class="badge" style="color:var(--err);border-color:var(--err)">error</span>` : ""}
      </div>
      <div class="tc-actions"></div>`;
    const actions = card.querySelector(".tc-actions");
    const running = !["completed", "cancelled", "failed"].includes(t.status);
    if (running) {
      addBtn(actions, t.status === "paused" ? "Resume" : "Pause", "mini ghost", async (ev) => {
        ev.stopPropagation();
        await api(`/tasks/${t.task_id}/${t.status === "paused" ? "resume" : "pause"}`, { method: "POST" });
        refreshTasks();
      });
      addBtn(actions, "Cancel", "mini danger", async (ev) => {
        ev.stopPropagation(); await api(`/tasks/${t.task_id}/cancel`, { method: "POST" }); refreshTasks();
      });
    }
    card.addEventListener("click", () => drill(t.task_id));
    wrap.appendChild(card);
  }
}
function addBtn(parent, label, cls, fn) { const b = el("button", "btn " + cls); b.textContent = label; b.onclick = fn; parent.appendChild(b); }

async function refreshAgents() {
  const data = await api("/monitor/agents");
  const list = $("#agent-list"); list.innerHTML = "";
  for (const a of data.agents) {
    const row = el("div", "agent");
    row.innerHTML = `
      <div class="agent-top">
        <span class="aid"><span class="dot ${a.status}"></span>${a.agent_id}</span>
        <span class="role-tag">${a.role === "watchdog" ? "🛡 watchdog" : ""}</span>
      </div>
      <div class="asub">${a.status}${a.current_task ? " · " + a.current_task : ""}</div>
      <div class="asub">${a.assigned_skill ? "skill " + a.assigned_skill + " v" + a.assigned_skill_version : "no skill"} · vfails ${a.verification_failures}</div>`;
    list.appendChild(row);
  }
  const activeCount = data.agents.filter((a) => a.status !== "stopped").length;
  if (activeCount) $("#agent-count").value = String(Math.min(3, activeCount));
  $("#lock-holder").textContent = "lock: " + (data.input_lock_holder || "free");
  $("#cost-line").textContent = data.cost.limit_usd
    ? `session cost $${data.cost.spent_usd} / $${data.cost.limit_usd}`
    : `session cost $${data.cost.spent_usd} (no ceiling)`;
  renderApprovals(data.pending_approvals);
}

function renderApprovals(list) {
  const wrap = $("#approvals");
  $("#approval-count").textContent = list.length;
  if (!list.length) { wrap.innerHTML = '<div class="empty">No pending approvals</div>'; return; }
  wrap.innerHTML = "";
  // Sequential queue: show only the first (active) request prominently.
  list.forEach((a, i) => {
    const c = el("div", "approval");
    c.innerHTML = `<div class="risk">⚠ ${a.risk}${i > 0 ? " (queued)" : ""}</div>
      <div class="msg">${escape(a.message)}</div>
      <div class="asub" style="font-size:11px;color:var(--muted)">${a.agent_id} · ${a.task_id}</div>
      <div class="ap-actions"></div>`;
    const acts = c.querySelector(".ap-actions");
    if (i === 0) {
      addBtn(acts, "Approve", "mini", async () => { await api(`/approvals/${a.request_id}/grant`, { method: "POST" }); refreshAgents(); });
      addBtn(acts, "Deny", "mini danger", async () => { await api(`/approvals/${a.request_id}/deny`, { method: "POST" }); refreshAgents(); });
    }
    wrap.appendChild(c);
  });
}

async function refreshHardware() {
  const agents = +$("#agent-count").value;
  const [opts, current] = await Promise.all([
    api(`/inference-mode/options?agents=${agents}`),
    api(`/inference-mode/current`),
  ]);
  $("#sys-info").textContent = opts.detected_system.ram_gb
    ? `${opts.detected_system.cpu_cores} cores · ${opts.detected_system.ram_gb} GB RAM` : "specs unknown";
  const wrap = $("#hw-cards"); wrap.innerHTML = "";
  for (const m of opts.modes) {
    const active = m.mode === current.inference_mode;
    const card = el("div", "hw" + (active ? " active" : ""));
    const warn = (m.recommendation || "").toLowerCase().startsWith("warning");
    card.innerHTML = `<h4>${m.mode.replace("_", "-")}</h4>
      <dl>
        <dt>CPU</dt><dd>${m.min_cpu_cores} cores</dd>
        <dt>RAM</dt><dd>${m.min_ram_gb} GB</dd>
        <dt>GPU</dt><dd>${m.gpu}${m.min_vram_gb ? " · " + m.min_vram_gb + "GB" : ""}</dd>
        <dt>Disk</dt><dd>${m.disk_space_gb} GB</dd>
        <dt>Network</dt><dd>${m.network_dependency}</dd>
        <dt>Cost</dt><dd>${escape(m.relative_cost)}</dd>
      </dl>
      <div class="rec ${warn ? "warnrec" : ""}">${escape(m.recommendation)}</div>`;
    wrap.appendChild(card);
  }
  $("#inference-mode").value = current.inference_mode;
}

async function refreshSkills() {
  const skills = await api("/skills?status=active");
  $("#skill-count").textContent = skills.length;
  const wrap = $("#skill-list"); wrap.innerHTML = "";
  if (!skills.length) { wrap.innerHTML = '<div class="empty">No active skills. Load an example skill.</div>'; return; }
  for (const s of skills) {
    const row = el("div", "skill");
    row.innerHTML = `<div><div class="sname">${escape(s.name)}</div><div class="sver">${s.skill_id} · v${s.version} · ${s.skill_type}</div></div>
      <span class="badge">${s.status}</span>`;
    wrap.appendChild(row);
  }
  // Populate the create-task skill picker.
  const picker = $("#t-skill"); picker.innerHTML = "";
  skills.forEach((s) => { const o = el("option"); o.value = s.skill_id; o.textContent = `${s.name} (v${s.version})`; picker.appendChild(o); });
}

async function refreshAll() {
  try { await Promise.all([refreshTasks(), refreshAgents(), refreshHardware(), refreshSkills()]); }
  catch (e) { console.warn(e); }
}

// ---- Drill-down ----
async function drill(taskId) {
  const [task, timeline, logs] = await Promise.all([
    api(`/tasks/${taskId}`), api(`/tasks/${taskId}/timeline`), api(`/tasks/${taskId}/logs`),
  ]);
  $("#drill-title").textContent = task.title + " — " + task.task_id;
  const body = $("#drill-body");
  const tlRows = timeline.map((r) => {
    const v = r.status === "success" ? "v-ok" : r.status === "failed" ? "v-fail" : "v-no";
    return `<div class="timeline-row"><span>step ${r.step ?? "–"}</span><span>${escape(r.action || "")} — ${escape(r.message || "")}</span><span class="${v}">${r.status}</span></div>`;
  }).join("") || '<div class="empty">No timeline yet</div>';
  const logRows = logs.map((l) => `<div class="timeline-row"><span>${(l.timestamp||"").split("T")[1]?.replace("Z","")||""}</span><span>${escape(l.message)}</span><span>${l.level}</span></div>`).join("");
  body.innerHTML = `
    <div class="drill-section"><h4>State</h4>
      <div class="asub">status: <b>${task.status}</b> · progress ${Math.round((task.progress||0)*100)}% · mode ${task.input_behavior_mode} · ${task.coordination_mode}</div>
      ${task.error ? `<div class="asub" style="color:var(--err)">error: ${escape(task.error)}</div>` : ""}
    </div>
    <div class="drill-section"><h4>Action Timeline</h4>${tlRows}</div>
    <div class="drill-section"><h4>Logs</h4>${logRows}</div>`;
  $("#drill-modal").hidden = false;
}
$("#drill-close").onclick = () => ($("#drill-modal").hidden = true);

// ---- Controls ----
$("#agent-count").addEventListener("change", async (e) => {
  await api("/agents/config", { method: "POST", body: JSON.stringify({ count: +e.target.value }) });
  refreshAgents(); refreshHardware();
});
$("#inference-mode").addEventListener("change", async (e) => {
  try {
    await api("/inference-mode", { method: "POST", body: JSON.stringify({ inference_mode: e.target.value }) });
  } catch (err) { alert(err.message); }
  refreshHardware();
});
$("#behavior-mode").addEventListener("change", () => localStorage.setItem("behavior", $("#behavior-mode").value));
const savedBehavior = localStorage.getItem("behavior"); if (savedBehavior) $("#behavior-mode").value = savedBehavior;

// New task modal
$("#new-task-btn").onclick = () => ($("#task-modal").hidden = false);
$("#t-cancel").onclick = () => ($("#task-modal").hidden = true);
$("#t-create").onclick = async () => {
  let input = {};
  try { input = JSON.parse($("#t-input").value || "{}"); } catch { return alert("Input must be valid JSON"); }
  const skillId = $("#t-skill").value;
  if (!skillId) return alert("Create a skill first (see example skills in README).");
  try {
    await api("/tasks", { method: "POST", body: JSON.stringify({
      title: $("#t-title").value || "Untitled task",
      skill_refs: [{ skill_id: skillId }],
      input, coordination_mode: $("#t-coord").value,
      input_behavior_mode: $("#behavior-mode").value,
    }) });
    $("#task-modal").hidden = true; $("#t-title").value = ""; refreshAll();
  } catch (e) { alert(e.message); }
};

connect();
refreshAll();
setInterval(refreshAgents, 4000); // periodic re-poll ensures liveness even if idle
