/* LitPilot frontend — no build step, no framework, one file.
   Everything the UI shows comes from the SSE stream or from the run's JSONL trace,
   so a page refresh can rebuild the exact same screen. */

const $ = (id) => document.getElementById(id);
const state = { runId: null, es: null, events: 0, health: null, conclusion: "" };

/* ---------- boot ---------- */
async function boot() {
  try {
    const r = await fetch("/api/health");
    const h = await r.json();
    state.health = h;
    const pill = $("healthPill");
    if (h.llm_ready) {
      pill.textContent = `模型就绪 · ${h.model}`;
      pill.className = "pill ok";
      $("mockToggle").checked = h.default_mock;
    } else {
      pill.textContent = "未配置 API key · 仅离线语料";
      pill.className = "pill warn";
      $("mockToggle").checked = true;
    }
  } catch (e) {
    $("healthPill").textContent = "服务未连接";
    $("healthPill").className = "pill warn";
  }
  loadHistory();
  $("runBtn").onclick = startRun;
  $("evClose").onclick = () => ($("evidencePanel").hidden = true);
  $("history").onchange = (e) => e.target.value && replayRun(e.target.value);
  $("topic").addEventListener("keydown", (e) => {
    if (e.key === "Enter") startRun();
  });

  // ?replay=<run_id> reopens a finished run — used for links in the report and
  // for demoing without waiting.
  const replay = new URLSearchParams(location.search).get("replay");
  if (replay) replayRun(replay);
}

/* ---------- run ---------- */
async function startRun() {
  const topic = $("topic").value.trim();
  if (!topic) return;
  const btn = $("runBtn");
  btn.disabled = true;
  btn.textContent = "运行中…";
  resetUI();

  const body = {
    topic,
    mock: $("mockToggle").checked,
    inject_fault: $("faultToggle").checked,
  };
  let res;
  try {
    res = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (e) {
    pushEvent({ node: "done", status: "error", title: "无法连接后端：" + e.message });
    finish();
    return;
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    pushEvent({ node: "done", status: "error", title: "启动失败：" + (err.detail || res.status) });
    finish();
    return;
  }
  const data = await res.json();
  state.runId = data.run_id;
  listen(data.run_id);
}

function listen(runId) {
  if (state.es) state.es.close();
  const es = new EventSource(`/api/runs/${runId}/stream`);
  state.es = es;
  es.onmessage = (m) => {
    let ev;
    try { ev = JSON.parse(m.data); } catch { return; }
    pushEvent(ev);
    if (ev.node === "table") {
      renderTableFromEvents(ev);
    }
    if (ev.node === "done") {
      state.conclusion = ev.decision || "";
      es.close();
      loadResult(runId);
    }
  };
  es.addEventListener("end", () => es.close());
  es.onerror = () => { /* keep-alive blips are normal; the browser retries */ };
}

async function loadResult(runId) {
  try {
    const r = await fetch(`/api/runs/${runId}/result`);
    if (!r.ok) throw new Error("结果尚未落盘");
    const data = await r.json();
    if (data.status === "running") {
      setTimeout(() => loadResult(runId), 600);
      return;
    }
    renderResult(data);
  } catch (e) {
    pushEvent({ node: "done", status: "warn", title: "读取结果失败：" + e.message });
  } finally {
    finish();
    loadHistory();
  }
}

function finish() {
  const btn = $("runBtn");
  btn.disabled = false;
  btn.textContent = "运行";
}

function resetUI() {
  $("trace").innerHTML = "";
  $("traceEmpty").hidden = true;
  $("tableEmpty").hidden = true;
  $("tbody").innerHTML = "";
  $("conclusion").hidden = true;
  $("evidencePanel").hidden = true;
  state.events = 0;
  $("stepCounter").textContent = "0 步";
  $("rowCounter").textContent = "0 篇";
}

/* ---------- trace ---------- */
const NODE_LABEL = {
  planner: "PLAN", search: "SEARCH", fetch: "FETCH", parse: "PARSE",
  extract: "EXTRACT", verify: "VERIFY", table: "TABLE", critic: "CRITIC",
  metrics: "METRIC", done: "DONE",
};

function pushEvent(ev) {
  const list = $("trace");
  const li = document.createElement("li");
  const status = ev.status || "info";
  li.className = `ev ${status}`;
  const seq = ev.seq ? String(ev.seq).padStart(2, "0") : "··";
  const node = NODE_LABEL[ev.node] || (ev.node || "STEP").toUpperCase();
  const tool = ev.tool ? `<span class="muted">${ev.tool}()</span>` : "";
  const decision = ev.decision ? `<div class="decision">${esc(ev.decision)}</div>` : "";
  li.innerHTML = `
    <span class="seq">${seq}</span>
    <div>
      <div><span class="node">${node}</span><span class="title">${esc(ev.title || "")}</span>${tool}</div>
      ${decision}
    </div>`;
  if (ev.detail && ev.detail.claims) {
    li.style.cursor = "pointer";
    li.title = "点击查看该篇证据明细";
    li.onclick = () => showClaims(ev.title, ev.detail.claims);
  }
  list.appendChild(li);
  list.scrollTop = list.scrollHeight;
  state.events += 1;
  $("stepCounter").textContent = `${state.events} 步`;
}

/* ---------- table ---------- */
function renderTableFromEvents(ev) {
  const rows = (ev.detail && ev.detail.rows) || [];
  if (!rows.length) return;
  $("tableEmpty").hidden = true;
  $("tbody").innerHTML = rows.map((r) => `
    <tr class="${r.used_in_conclusion ? "" : "excluded"}" data-paper="${esc(r.paper_id)}">
      <td><div class="ptitle">${esc(r.title)}</div>
          <div class="pmeta">${r.metrics && r.metrics.length ? "" : "指标缺失"}</div></td>
      <td>${esc(r.method || "—")}</td>
      <td>${esc(r.dataset || "—")}</td>
      <td>${esc((r.metrics || []).join(" · ") || "—")}</td>
      <td><span class="badge ${r.worst_level}">${r.worst_level}</span></td>
      <td>${r.used_in_conclusion ? '<span class="yes">进入结论</span>' : '<span class="no">已排除</span>'}</td>
    </tr>`).join("");
  $("rowCounter").textContent = `${rows.length} 篇`;
}

function renderResult(data) {
  const m = data.metrics || {};
  $("mCcr").textContent = Math.round((m.ccr || 0) * 100) + "%";
  $("mCcrSub").textContent = `${m.claims_verified || 0}/${m.claims_total || 0} 条结论可核对`;
  $("mField").textContent = Math.round((m.field_completeness || 0) * 100) + "%";
  $("mFieldSub").textContent = "method + dataset + metric 齐全";
  const dist = m.level_dist || {};
  $("mLevels").innerHTML = ["A", "B", "C", "D"]
    .map((k) => `<span class="lv lv-${k}">${k} ${dist[k] || 0}</span>`).join("");
  $("mFail").textContent = `${m.failures || 0} 失败 / ${m.extract_retries || 0} 重试`;
  $("mFailSub").textContent = `${m.duration_s || 0}s · ${m.papers_total || 0} 篇`;

  const rows = data.table || [];
  $("tableEmpty").hidden = rows.length > 0;
  $("tbody").innerHTML = rows.map((r) => {
    const metrics = (r.metrics || []).map((x) => `${x.name}=${x.value}`).join(" · ");
    const cache = r.from_cache ? '<span class="tag">缓存</span>' : "";
    const src = r.source === "abstract" ? '<span class="tag">仅摘要</span>' : "";
    return `<tr class="${r.used_in_conclusion ? "" : "excluded"}" data-paper="${esc(r.paper_id)}">
      <td><div class="ptitle">${esc(r.title)}</div>
          <div class="pmeta">${r.year || ""} ${r.venue ? "· " + esc(r.venue) : ""}${cache}${src}</div></td>
      <td>${esc(r.method || "—")}</td>
      <td>${esc(r.dataset || "—")}</td>
      <td>${esc(metrics || "—")}</td>
      <td><span class="badge ${r.worst_level}">${r.worst_level}</span></td>
      <td>${r.used_in_conclusion ? '<span class="yes">进入结论</span>' : '<span class="no">已排除</span>'}</td>
    </tr>`;
  }).join("");
  $("rowCounter").textContent = `${rows.length} 篇`;

  [...document.querySelectorAll("#tbody tr")].forEach((tr) => {
    tr.onclick = () => {
      const pid = tr.dataset.paper;
      const claims = (data.claims || []).filter((c) => c.paper_id === pid);
      const paper = (data.papers || []).find((p) => p.paper_id === pid);
      showClaims(paper ? paper.title : pid, claims.map(toClaimView));
    };
  });

  if (state.conclusion) {
    $("conclusion").hidden = false;
    $("conclusion").textContent = state.conclusion;
  } else {
    const usable = rows.filter((r) => r.used_in_conclusion);
    if (usable.length) {
      $("conclusion").hidden = false;
      $("conclusion").textContent =
        `${usable.length} 篇结论可回查原文；` +
        `${rows.length - usable.length} 篇因证据等级不足被排除（表内保留，标记为已排除）。`;
    }
  }
}

function toClaimView(c) {
  const e = c.evidence || {};
  return {
    text: c.text,
    quote: e.quote || "",
    level: (e.level || "D"),
    page: e.page,
    ratio: e.match_ratio,
    note: e.note || "",
    section: c.section || "",
  };
}

/* ---------- evidence ---------- */
function showClaims(title, claims) {
  $("evidencePanel").hidden = false;
  $("evTitle").textContent = "证据明细 · " + (title || "");
  if (!claims || !claims.length) {
    $("evBody").innerHTML = '<div class="trace-empty">这篇没有产出可核对的结论。</div>';
    return;
  }
  $("evBody").innerHTML = claims.map((c) => {
    const level = c.level || "D";
    const meta = [
      `<span class="badge ${level}">${level} 级</span>`,
      c.section ? `<span>章节 ${esc(c.section)}</span>` : "",
      c.page ? `<span>第 ${c.page} 页</span>` : "",
      c.ratio ? `<span>覆盖度 ${Number(c.ratio).toFixed(3)}</span>` : "",
    ].filter(Boolean).join("");
    return `<div class="claim level-${level}">
      <div class="ct">${esc(c.text || "")}</div>
      ${c.quote ? `<blockquote>${esc(c.quote)}</blockquote>` : '<div class="muted">（无引用句）</div>'}
      <div class="meta">${meta}${c.note ? `<span>${esc(c.note)}</span>` : ""}</div>
    </div>`;
  }).join("");
}

/* ---------- history ---------- */
async function loadHistory() {
  try {
    const r = await fetch("/api/runs");
    const data = await r.json();
    const sel = $("history");
    const keep = sel.value;
    sel.innerHTML = '<option value="">历史运行…</option>' +
      (data.runs || []).map((x) =>
        `<option value="${x.run_id}">${x.run_id} · ${x.events} 步</option>`).join("");
    if (keep) sel.value = keep;
  } catch { /* history is optional */ }
}

async function replayRun(runId) {
  resetUI();
  $("runBtn").disabled = true;
  $("runBtn").textContent = "回放中…";
  state.conclusion = "";
  try {
    const tr = await (await fetch(`/api/runs/${runId}/trace`)).json();
    (tr.events || []).forEach((ev) => {
      pushEvent(ev);
      if (ev.node === "table") renderTableFromEvents(ev);
      if (ev.node === "done") state.conclusion = ev.decision || "";
    });
    await loadResult(runId);
  } catch (e) {
    pushEvent({ node: "done", status: "error", title: "回放失败：" + e.message });
    finish();
  }
}

/* ---------- utils ---------- */
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

boot();
