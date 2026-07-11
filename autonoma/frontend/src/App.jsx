import { useCallback, useEffect, useState } from "react";
import { api, useLiveEvents } from "./api.js";

const STATUSES = ["queued", "running", "waiting_approval", "paused", "completed", "cancelled", "failed"];

function useRefetch(fn, deps) {
  const [data, setData] = useState(null);
  const run = useCallback(() => { fn().then(setData).catch(() => {}); }, deps);
  useEffect(() => { run(); }, [run]);
  return [data, run];
}

export default function App() {
  const { events, tick, connected } = useLiveEvents();
  const [tasks, refetchTasks] = useRefetch(() => api("/monitor/tasks"), []);
  const [agents, refetchAgents] = useRefetch(() => api("/monitor/agents"), []);
  const [modes, setModes] = useState(null);
  const [current, setCurrent] = useState(null);

  const loadInference = useCallback(() => {
    api(`/inference-mode/options?agents=${agents?.agents?.filter(a => a.status !== "stopped").length || 1}`).then(setModes);
    api("/inference-mode/current").then(setCurrent);
  }, [agents]);

  useEffect(() => { loadInference(); }, [loadInference]);
  // Any live event refreshes the panels.
  useEffect(() => { refetchTasks(); refetchAgents(); }, [tick]);

  return (
    <div className="app">
      <header>
        <div className="brand"><span className="logo">◈</span> AUTONOMA <em>SPA</em></div>
        <div className="right">
          <AccentPicker />
          <span className={"conn " + (connected ? "on" : "off")}>● live</span>
        </div>
      </header>

      <main>
        <section className="col2">
          <Panel title="Task Monitor">
            <div className="cards">
              {(tasks || []).map((t) => <TaskCard key={t.task_id} t={t} onChange={refetchTasks} />)}
              {tasks && !tasks.length && <Empty>No tasks yet.</Empty>}
            </div>
          </Panel>
        </section>

        <Panel title="Agents" chip={agents ? `lock: ${agents.input_lock_holder || "free"}` : ""}>
          {(agents?.agents || []).map((a) => (
            <div className="agent" key={a.agent_id}>
              <b><span className={"dot " + a.status} /> {a.agent_id}</b>
              <span>{a.role === "watchdog" ? "🛡 watchdog" : a.status}</span>
            </div>
          ))}
          <Approvals list={agents?.pending_approvals || []} onChange={refetchAgents} />
        </Panel>

        <Panel title="Hardware Requirements" chip={modes ? sysLine(modes.detected_system) : ""} className="col2">
          <div className="hwrow">
            {(modes?.modes || []).map((m) => (
              <div key={m.mode} className={"hw " + (current?.inference_mode === m.mode ? "active" : "")}>
                <h4>{m.mode.replace("_", "-")}</h4>
                <div>CPU {m.min_cpu_cores} · RAM {m.min_ram_gb}GB · GPU {m.gpu}</div>
                <div>Disk {m.disk_space_gb}GB · Net {m.network_dependency}</div>
                <small className={String(m.recommendation).startsWith("Warning") ? "warn" : ""}>{m.recommendation}</small>
              </div>
            ))}
          </div>
        </Panel>

        <Panel title="Live Activity" className="col3">
          <div className="feed">
            {events.map((e, i) => (
              <div className="row" key={e.event_id || i}>
                <span className="ty">{e.event_type}</span>
                <span>{e.message || e.detail || e.action || ""}{e.verified === false ? " ⚠" : e.verified ? " ✓" : ""}</span>
              </div>
            ))}
          </div>
        </Panel>
      </main>
    </div>
  );
}

function TaskCard({ t, onChange }) {
  const act = async (verb) => { await api(`/tasks/${t.task_id}/${verb}`, { method: "POST" }); onChange(); };
  const running = !["completed", "cancelled", "failed"].includes(t.status);
  return (
    <div className="card">
      <div className="cardhead"><b>{t.title}</b><span className={"st " + t.status}>{t.status}</span></div>
      <div className="mono">{t.task_id}</div>
      <div className="prog"><i style={{ width: `${Math.round((t.progress || 0) * 100)}%` }} /></div>
      <div className="meta">{t.coordination_mode} · {t.input_behavior_mode} · step {t.current_step ?? "–"}</div>
      {running && (
        <div className="btns">
          <button onClick={() => act(t.status === "paused" ? "resume" : "pause")}>{t.status === "paused" ? "Resume" : "Pause"}</button>
          <button className="danger" onClick={() => act("cancel")}>Cancel</button>
        </div>
      )}
    </div>
  );
}

function Approvals({ list, onChange }) {
  if (!list.length) return null;
  const a = list[0];
  const resolve = async (verb) => { await api(`/approvals/${a.request_id}/${verb}`, { method: "POST" }); onChange(); };
  return (
    <div className="approval">
      <b className="warn">⚠ {a.risk}</b>
      <div>{a.message}</div>
      <div className="btns">
        <button onClick={() => resolve("grant")}>Approve</button>
        <button className="danger" onClick={() => resolve("deny")}>Deny</button>
      </div>
      {list.length > 1 && <small>{list.length - 1} more queued (shown one at a time)</small>}
    </div>
  );
}

function Panel({ title, chip, className = "", children }) {
  return (
    <section className={"panel " + className}>
      <div className="phead"><h2>{title}</h2>{chip && <span className="chip">{chip}</span>}</div>
      {children}
    </section>
  );
}
function Empty({ children }) { return <div className="empty">{children}</div>; }
function AccentPicker() {
  const set = (a) => { document.documentElement.setAttribute("data-accent", a); localStorage.setItem("accent", a); };
  return (
    <span className="swatches">
      {["cyan", "magenta", "lime"].map((a) => <button key={a} className={"sw " + a} onClick={() => set(a)} />)}
    </span>
  );
}
function sysLine(s) { return s?.ram_gb ? `${s.cpu_cores} cores · ${s.ram_gb} GB` : "specs unknown"; }
