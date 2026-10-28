"use strict";

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/";
let api = null;
let scenarios = [];
let current = null;
let edited = false;

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const TONE = { CREATE_CASE: "ok", UPDATE_CASE: "ok", REVIEW: "warn", IGNORE: "idle", HOLD: "bad" };
const WORD = { CREATE_CASE: "CREATE", UPDATE_CASE: "UPDATE", REVIEW: "REVIEW", IGNORE: "IGNORE", HOLD: "HOLD" };
const MEANING = {
  CREATE_CASE: "New case written with an exact customer + order key",
  UPDATE_CASE: "Existing case found deterministically; update appended to its history",
  REVIEW: "Not safe to automate. Goes to a person in the daily review list",
  IGNORE: "Not a case. Nothing written",
  HOLD: "Transient failure. Nothing written; the event is retried",
};

function loadScript(src) {
  return new Promise((ok, fail) => {
    const s = document.createElement("script");
    s.src = src; s.onload = ok; s.onerror = () => fail(new Error("could not load " + src));
    document.head.appendChild(s);
  });
}

async function boot() {
  try {
    await loadScript(PYODIDE + "pyodide.js");
    const py = await loadPyodide({ indexURL: PYODIDE });
    const manifest = await (await fetch("manifest.json")).json();
    for (const f of manifest.files) {
      const text = await (await fetch("../" + f)).text();
      py.FS.mkdirTree("/home/pyodide/" + f.split("/").slice(0, -1).join("/"));
      py.FS.writeFile("/home/pyodide/" + f, text);
    }
    py.runPython("import sys; sys.path.insert(0, '/home/pyodide/src')");
    api = py.pyimport("case_intake.demo_api");
    scenarios = JSON.parse(api.scenarios());
    $("#scenario").innerHTML = scenarios.map((s, i) => `<option value="${s.id}">${i + 1}. ${esc(s.title)}</option>`).join("");
    $("#mode").textContent = "engine loaded · no API key";
    $("#mode").classList.add("ok");
    $("#run").disabled = false;
    pick(scenarios[0].id);
    run();
    renderBatch();
  } catch (e) {
    $("#mode").textContent = "engine failed to load";
    $("#mode").classList.add("bad");
    $("#outcome").innerHTML = `<p class="bad-text">${esc(e.message)}</p><p class="muted">The demo loads Pyodide from a CDN. Run locally with <code>make demo</code>.</p>`;
  }
}

function pick(id) {
  current = scenarios.find((s) => s.id === id);
  $("#scenario").value = id;
  $("#blurb").textContent = current.blurb + "  Expected: " + current.expected + ".";
  $("#f-from").value = current.email.sender;
  $("#f-subject").value = current.email.subject;
  $("#f-thread").value = current.email.thread_id;
  $("#f-body").value = current.email.body;
  $("#dry").checked = current.dry_run;
  setEdited(false);
}

function setEdited(v) { edited = v; $("#edited").hidden = !v; }

function run() {
  if (!api) return;
  const email = { ...current.email, sender: $("#f-from").value, subject: $("#f-subject").value,
                  thread_id: $("#f-thread").value, body: $("#f-body").value };
  const payload = { email, recorded_output: edited ? null : current.recorded_output, dry_run: $("#dry").checked };
  const r = JSON.parse(api.run_one(JSON.stringify(payload)));
  renderStages(r);
  renderOutcome(r);
}

function renderStages(r) {
  const names = { idempotency: "Idempotency", "pre-filter": "Pre-filter", classification: "Classification",
                  normalization: "Normalization", matching: "Matching", decision: "Decision", write: "Write" };
  const all = ["idempotency", "pre-filter", "classification", "normalization", "matching", "decision", "write"];
  const seen = Object.fromEntries(r.stages.map((s) => [s.stage, s]));
  const cls = r.stages.find((s) => s.stage === "classification");
  $("#stages").innerHTML = all.map((st) => {
    const s = seen[st];
    if (!s) return `<li class="stage notrun"><div class="st-h"><span class="dot"></span><b>${names[st]}</b><span class="tag idle">not reached</span></div></li>`;
    let extra = "";
    if (st === "classification" && Object.keys(s.data || {}).length) {
      extra = `<pre class="json" aria-label="Classifier output">${esc(JSON.stringify(s.data, null, 1))}</pre>
               <p class="muted small">Classifier: ${esc(r.classifier_used)}${r.classifier_used === "recorded" ? " (a stored model output for this email)" : ""}</p>`;
    }
    if (st === "pre-filter" && s.data && s.data.suspected_injection) {
      extra = `<p class="small warn-text">Text addressed to the model: “${esc(s.data.suspected_injection)}”. Treated as content, never as instructions.</p>`;
    }
    return `<li class="stage ${s.status}"><div class="st-h"><span class="dot"></span><b>${names[st]}</b>
            <span class="tag ${({ pass: "ok", stop: "idle", skip: "idle", fail: "bad" })[s.status]}">${s.status}</span></div>
            <p class="small">${esc(s.detail)}</p>${extra}</li>`;
  }).join("");
  if (!cls && r.audit.prefilter_rule) {
    // make the cost point visible
    $("#stages").insertAdjacentHTML("beforeend", `<li class="note small">No model call was made for this email.</li>`);
  }
}

function caseCard(c, title) {
  if (!c) return "";
  return `<div class="case"><div class="case-h">${esc(title)} <code>${esc(c.case_key)}</code></div>
    <table class="kv">
      <tr><td>Customer</td><td>${esc(c.customer_name || "")} (${esc(c.customer_id)})</td></tr>
      <tr><td>Order / invoice</td><td>${esc(c.order_id)}</td></tr>
      <tr><td>Type · status</td><td>${esc(c.case_type || "")} · ${esc(c.status)}</td></tr>
      <tr><td>Owner</td><td>${esc(c.owner)}</td></tr>
    </table>
    <ol class="hist">${c.history.map((h) => `<li><span class="mono">${esc(h.at.slice(0, 16).replace("T", " "))}</span> ${esc(h.event_id)}: ${esc(h.summary)}</li>`).join("")}</ol></div>`;
}

function renderOutcome(r) {
  const a = r.audit;
  const before = (r.tracker_before || []).find((c) => c.case_key === a.case_key);
  const after = (r.tracker_after || []).find((c) => c.case_key === a.case_key);
  let state = "";
  if (r.decision === "CREATE_CASE" || r.decision === "UPDATE_CASE") {
    state = a.wrote
      ? caseCard(after, r.decision === "CREATE_CASE" ? "Created" : "Updated")
      : caseCard(r.case_after, "Proposed (dry run, not written)") + `<p class="small muted">Tracker unchanged: ${before ? `${esc(a.case_key)} still has ${before.history.length} history entr${before.history.length === 1 ? "y" : "ies"}` : `${esc(a.case_key)} does not exist`}.</p>`;
  } else if (before) {
    state = caseCard(before, "Existing case (unchanged)");
  }
  $("#outcome").className = "";
  $("#outcome").innerHTML = `
    <div class="decision ${TONE[r.decision]}">
      <div class="d-label">Decision${a.dry_run ? " · dry run" : ""}</div>
      <div class="d-value">${WORD[r.decision]}</div>
      <div class="d-text">${esc(MEANING[r.decision])}</div>
    </div>
    <table class="kv">
      <tr><td>CaseKey</td><td><code>${esc(a.case_key || "none")}</code></td></tr>
      <tr><td>Match</td><td>${esc(a.match_method || "n/a")}</td></tr>
      <tr><td>Reason</td><td>${esc(r.reason)}</td></tr>
      <tr><td>Model called</td><td>${a.model_called ? "yes" : "no"}</td></tr>
      <tr><td>Written</td><td>${a.wrote ? "yes" : "no"}</td></tr>
    </table>
    <h3>Tracker state</h3>
    ${state || `<p class="muted small">No case touched.</p>`}
    <h3>Audit log entry</h3>
    <pre class="json">${esc(JSON.stringify(a, null, 1))}</pre>`;
}

function renderBatch() {
  const r = JSON.parse(api.batch($("#batch-dry").checked));
  const s = r.summary, d = s.decisions;
  const rows = r.rows.map((x) => `<tr class="${x.decision === x.expected ? "" : "diff"}">
      <td class="mono">${esc(x.event_id)}</td><td>${esc(x.subject)}</td>
      <td><span class="tag ${TONE[x.decision]}">${WORD[x.decision]}</span></td>
      <td>${x.decision === x.expected ? "" : `<span class="small">labelled ${WORD[x.expected]}</span>`}</td>
      <td class="small">${esc(x.reason)}</td><td>${x.model_called ? "yes" : "no"}</td><td>${x.wrote ? "yes" : "no"}</td></tr>`).join("");
  $("#batch-out").innerHTML = `
    <div class="stats">
      <div><div class="k">New cases</div><div class="big">${d.CREATE_CASE}</div></div>
      <div><div class="k">Updated</div><div class="big">${d.UPDATE_CASE}</div></div>
      <div><div class="k">Review</div><div class="big">${d.REVIEW}</div></div>
      <div><div class="k">Ignored</div><div class="big">${d.IGNORE}</div></div>
      <div><div class="k">Held (retry)</div><div class="big">${d.HOLD}</div></div>
      <div><div class="k">Model calls</div><div class="big">${s.model_calls}</div><div class="muted small">${s.ignored_before_model} discarded before the model</div></div>
    </div>
    <h3>The summary message (one per day, not one alert per email)</h3>
    <pre class="digest">${esc(r.text)}</pre>
    <h3>Every event</h3>
    <div class="table-wrap"><table class="grid"><thead><tr><th>Event</th><th>Subject</th><th>Decision</th><th>vs label</th><th>Reason</th><th>Model</th><th>Written</th></tr></thead><tbody>${rows}</tbody></table></div>
    <p class="muted small">Rows marked “labelled …” are where the result differs from the human label. In this set both come from deliberate model mistakes: one false positive (contained as REVIEW, not written) and one false negative (a missed case). Synthetic replay validation, not production metrics.</p>`;
}

$("#scenario").addEventListener("change", (e) => { pick(e.target.value); run(); });
$("#run").addEventListener("click", run);
for (const id of ["#f-from", "#f-subject", "#f-thread", "#f-body"]) $(id).addEventListener("input", () => setEdited(true));
$("#dry").addEventListener("change", run);
$("#batch-dry").addEventListener("change", renderBatch);
document.querySelectorAll(".tab[data-view]").forEach((t) => t.addEventListener("click", () => {
  document.querySelectorAll(".tab[data-view]").forEach((x) => { x.classList.toggle("active", x === t); x.setAttribute("aria-pressed", x === t); });
  $("#view-walk").hidden = t.dataset.view !== "walk";
  $("#view-batch").hidden = t.dataset.view !== "batch";
}));

boot();
