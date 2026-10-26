// Credit Recovery Copilot front end. Formats numbers only: every figure comes from the API (engine or extraction).
const $ = (s) => document.querySelector(s);
const state = { cases: [], slug: null, view: null, pending: {}, sliders: {}, scenario: 0, timer: null };
const params = new URLSearchParams(location.search);

const where = (url) => (/sec\.gov/.test(url || "") ? "SEC EDGAR" : /epiq/.test(url || "") ? "the claims agent (Epiq)" : "source");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function fmt(v, dec = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return Number(v).toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
}
const pct = (v, dec = 1) => (v === null || v === undefined ? "—" : `${fmt(v, dec)}%`);
const money = (v, a) => fmt(v, a.rounding_step < 1 ? 1 : 0);
const unitLabel = (a) => (a.units === "USD millions" ? "$ millions" : "$ thousands");

async function api(path, opts = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ? (typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)) : `HTTP ${res.status}`);
  return body;
}
function showError(msg) { const e = $("#error"); e.textContent = msg; e.classList.toggle("hidden", !msg); }

// ---------- step 1: cases ----------

async function loadCases(select) {
  state.cases = await api("/api/cases");
  $("#cases").innerHTML = state.cases.map((c) => `
    <button class="case" data-slug="${c.slug}">
      <div class="co">${esc(c.company)}</div>
      <div class="meta">${esc(c.exhibit.split("(")[0])} · filed ${esc(c.filed_date)}</div>
      <div class="meta">${esc(c.filing.split(":")[0])}</div>
      <div class="runs">${c.saved_runs.length} saved run(s) · <a href="${esc(c.url)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">open on ${where(c.url)}</a></div>
    </button>`).join("");
  document.querySelectorAll(".case").forEach((b) => b.addEventListener("click", () => selectCase(b.dataset.slug)));
  if (select) selectCase(select);
}

function selectCase(slug) {
  state.slug = slug;
  document.querySelectorAll(".case").forEach((b) => b.classList.toggle("selected", b.dataset.slug === slug));
  const c = state.cases.find((x) => x.slug === slug);
  $("#run").disabled = false;
  const sel = $("#saved");
  sel.disabled = !c.saved_runs.length;
  sel.innerHTML = `<option value="">${c.saved_runs.length ? "choose a saved run…" : "no saved runs"}</option>` + c.saved_runs.map((r) => {
    const when = new Date(r.timestamp_utc).toLocaleString();
    const tag = r.injection_test ? " · safety test (planted instruction)" : r.reviewed ? ` · reviewed (${r.corrections} correction set)` : "";
    return `<option value="${r.name}">${when} · ${r.status === "reconciled" ? "RECONCILED" : "NEEDS REVIEW"}${tag}</option>`;
  }).join("");
  showError("");
}

// ---------- running a live extraction ----------

const STEPS = [
  ["locate", "Find and sanitize the liquidation-analysis exhibit (code)"],
  ["extract", "Extractor agent copies the table with gpt-6-luna"],
  ["validate", "Check every number against its cited row and the table totals (code)"],
  ["engine", "Recompute the waterfall and compare with the filed recoveries (engine)"],
];
function setStep(key, status, detail) {
  const li = document.querySelector(`#progress-steps li[data-k="${key}"]`);
  li.className = status;
  if (detail) li.querySelector(".det").textContent = ` — ${detail}`;
}
async function runLive() {
  if (!state.slug) return;
  showError("");
  $("#run").disabled = true;
  $("#progress").classList.remove("hidden");
  $("#progress-steps").innerHTML = STEPS.map(([k, t]) => `<li data-k="${k}"><span class="dot"></span><span>${t}<span class="det muted"></span></span></li>`).join("");
  const t0 = Date.now();
  state.timer = setInterval(() => { $("#elapsed").textContent = `${((Date.now() - t0) / 1000).toFixed(0)} s`; }, 250);
  try {
    setStep("locate", "active");
    const ex = await api(`/api/cases/${state.slug}/exhibit`);
    setStep("locate", "done", `pages ${ex.first_page}–${ex.last_page} of ${ex.pages_in_filing}, ${fmt(ex.chars)} characters, ${ex.quarantined} hidden item(s) withheld`);
    setStep("extract", "active");
    const v = await api(`/api/cases/${state.slug}/extract`, { method: "POST" });
    setStep("extract", "done", v.error ? "failed" : `${v.attempts} attempt(s), ${v.seconds} s`);
    if (!v.error) {
      const a = v.result.assessment;
      setStep("validate", "done", a.grounded && a.crossfoot_ok ? "passed" : "problems found (see below)");
      setStep("engine", "done", a.reconciles_with_filed ? "matches the filed recoveries" : "does NOT match the filed recoveries");
    }
    render(v);
    await loadCases(state.slug);
  } catch (e) {
    showError(`Run failed: ${e.message}`);
    document.querySelectorAll("#progress-steps li.active").forEach((li) => (li.className = ""));
  } finally {
    clearInterval(state.timer);
    $("#run").disabled = false;
  }
}

async function openRun(name) {
  showError("");
  try { render(await api(`/api/runs/${name}`)); } catch (e) { showError(e.message); }
}

// ---------- rendering a run ----------

function render(v) {
  state.view = v;
  state.pending = {};
  $("#result").classList.remove("hidden");
  renderStatus(v);
  renderUsage(v);
  $("#activity").innerHTML = v.activity.map((s) => {
    const cls = s.by === "gpt-6-luna" ? "model" : s.by.startsWith("person") ? "person" : s.by;
    return `<li class="by-${esc(cls)}"><span class="by ${cls}">${esc(s.by)}</span><span class="t">${esc(s.title)}</span><div class="d">${esc(s.detail)}</div></li>`;
  }).join("");
  renderSafety(v);
  if (v.result) {
    renderRecon(v);
    setupStress(v);
    renderTables(v);
    renderReference(v);
  }
  updateReviewBar();
}

// Slim "analysis header": which company, which filing and exhibit, where it came from (all from the API).
function renderSubject(v) {
  const c = state.cases.find((x) => x.slug === v.case), s = v.source || {};
  const pages = Array.isArray(s.exhibit_pages) && s.exhibit_pages.length === 2
    ? `pages ${s.exhibit_pages[0]}–${s.exhibit_pages[1]}${s.pages_in_filing ? ` of ${s.pages_in_filing}` : ""}` : "";
  const exhibit = c ? c.exhibit : s.exhibit_heading;
  const chips = [
    exhibit ? `<span class="ah-chip ex">${esc(exhibit)}</span>` : "",
    pages ? `<span class="ah-chip">${esc(pages)}</span>` : "",
    c ? `<span class="ah-chip">filed ${esc(c.filed_date)}</span>` : "",
    s.sha256 ? `<span class="ah-chip mono" title="SHA-256 of the filing copy analysed: ${esc(s.sha256)}">sha256 ${esc(s.sha256.slice(0, 12))}…</span>` : "",
    c && c.url ? `<a class="ah-link" href="${esc(c.url)}" target="_blank" rel="noopener">Open source on ${where(c.url)} ↗</a>` : "",
  ].join("");
  $("#analysis-head").innerHTML = `<div class="ah-kicker">Analysed filing</div>
    <div class="ah-co">${esc(c ? c.company : v.case)}</div>
    ${c ? `<div class="ah-filing">${esc(c.filing)}</div>` : ""}
    <div class="ah-meta">${chips}</div>`;
}

function renderStatus(v) {
  const badge = $("#status-badge");
  renderSubject(v);
  let title, detail;
  if (v.error) {
    $("#status-card").className = "card status-card is-review";
    badge.className = "badge review fail"; badge.textContent = "⚠ EXTRACTION FAILED";
    title = "The model call did not return a usable table."; detail = v.error;
  } else {
    const a = v.result.assessment;
    const ok = a.status === "reconciled";
    $("#status-card").className = `card status-card ${ok ? "is-ok" : "is-review"}`;
    badge.className = `badge ${ok ? "ok" : "review"}`;
    badge.textContent = ok ? "✓ RECONCILED" : "⚠ NEEDS REVIEW";
    const corrected = (v.corrections || []).length;
    if (ok) {
      title = corrected ? "Reconciled after human correction." : "AI extraction checked by code and reconciled.";
      detail = `Every extracted number appears in the row the agent cited, the table's totals add up, and the engine reproduces the debtor's filed class recoveries (largest gap ${fmt(a.max_pct_gap, 2)} percentage points; filings round).`;
    } else {
      const counts = {};
      a.warnings.filter((w) => w.severity === "error").forEach((w) => (counts[w.kind] = (counts[w.kind] || 0) + 1));
      title = `Not verified: ${Object.entries(counts).map(([k, n]) => `${n} ${k} problem${n > 1 ? "s" : ""}`).join(", ")}.`;
      detail = "Nothing has been changed automatically. ";
      if (a.grounded && a.crossfoot_ok && !a.reconciles_with_filed) {
        detail += "The extracted numbers match the filing and its totals add up, but one consolidated priority waterfall does not reproduce the filed class recoveries. The filing may use separate legal-entity or collateral-pool waterfalls, so a person should review before relying on any recomputed figure.";
      } else {
        detail += "Review the flagged rows in section 4 and correct them with your name, or treat the filed figures as unverified.";
      }
    }
  }
  $("#status-title").textContent = title;
  $("#status-detail").textContent = detail;
  const when = v.timestamp_utc ? new Date(v.timestamp_utc).toLocaleString() : "";
  $("#run-meta").innerHTML = `<div class="rm-k">Run</div><div class="rm-id">${esc(v.run_id)}</div><div>${esc(when)}</div>`
    + ((v.corrections || []).length ? `<div>${v.corrections.length} correction set(s) by ${esc(v.corrections.map((c) => c.by).join(", "))}</div>` : "")
    + (v.injection_test ? `<div class="rm-flag">⚠ <strong>Safety test run: an instruction was planted in this copy of the filing</strong></div>` : "");
}

function renderUsage(v) {
  const t = v.tokens || {}, c = v.cost_usd || {};
  const tiles = [
    ["Input tokens", fmt(t.input_tokens)], ["Cached input", fmt(t.cached_tokens)],
    ["Output tokens", `${fmt(t.output_tokens)}`], ["Reasoning (in output)", fmt(t.reasoning_tokens)],
    ["Cost of this run", c.total !== undefined ? `$${c.total.toFixed(5)}` : "—"], ["Runtime", `${v.seconds} s`],
  ];
  $("#usage").innerHTML = tiles.map(([k, val], i) => `<div class="tile${i >= 4 ? " accent" : ""}"><div class="k">${k}</div><div class="v">${val}</div></div>`).join("")
    + `<div class="usage-foot">Model reported by the API: <strong>${esc((v.model_reported || []).join(", ") || "—")}</strong> (requested gpt-6-luna) · ${v.attempts} attempt(s)</div>`;
}

function renderSafety(v) {
  const s = v.safety || {};
  const warns = v.result ? v.result.assessment.warnings : [];
  const errors = warns.filter((w) => w.severity === "error");
  let html = "";
  (s.injection_indicators || []).forEach((f) => (html += `<div class="warn"><div class="kind">instruction-like text in the filing (flagged for review)</div>${esc(f)}</div>`));
  (s.quarantined || []).slice(0, 6).forEach((q) => (html += `<div class="warn info"><div class="kind">hidden content withheld from the model</div>${esc(q.technique)}: “${esc(q.excerpt.slice(0, 140))}”</div>`));
  (s.layout_warnings || []).forEach((w) => (html += `<div class="warn layout"><div class="kind">page layout not fully verified (plain text sent, review)</div>${esc(w)}</div>`));
  if ((s.quarantined || []).length > 6) html += `<div class="calm">… and ${s.quarantined.length - 6} more hidden item(s) withheld (listed in the audit trail).</div>`;
  if (!html) html = `<div class="calm clean">No hidden text and no instruction-like phrases found in this exhibit.</div>`;
  if (errors.length) {
    html += `<div class="calm" style="margin-top:10px"><strong>${errors.length} check(s) failed</strong> (first ${Math.min(errors.length, 6)} shown):</div>`;
    errors.slice(0, 6).forEach((w) => (html += `<div class="warn err"><div class="kind">${esc(w.kind)}</div>${esc(w.message)}</div>`));
  }
  html += `<div class="calm small guard">Spending guard: at most ${4} model requests and 80,000 tokens per extraction; live runs are rate-limited on the server.</div>`;
  $("#safety").innerHTML = html;
}

function renderRecon(v) {
  const a = v.result.analysis, comp = v.result.assessment.computed_by_engine;
  const head = `<tr><th>Creditor class</th>${a.scenarios.map((s) => `<th colspan="3">${esc(s)}: filed · engine · match</th>`).join("")}</tr>`;
  let rows = "", lastP = null;
  a.claims.map((c, k) => ({ c, k })).sort((x, y) => x.c.priority - y.c.priority || x.k - y.k).forEach(({ c, k }) => {
    if (c.priority !== lastP) { rows += `<tr class="group"><td colspan="${1 + 3 * a.scenarios.length}">Priority ${c.priority}</td></tr>`; lastP = c.priority; }
    rows += `<tr><td>${esc(c.label)}</td>` + a.scenarios.map((_, i) => {
      const e = comp[i].classes[k].pct, f = c.filed_recovery_pct[i];
      const ok = f === null || Math.abs(e - f) <= 0.5;
      return `<td>${pct(f)}</td><td>${pct(e)}</td><td class="${ok ? "" : "miss"}">${ok ? '<span class="ok-mark">✓</span>' : '<span class="bad-mark">✗</span>'}</td>`;
    }).join("") + "</tr>";
  });
  rows += `<tr><td><strong>Net distributable value</strong> (${unitLabel(a)})</td>` + a.scenarios.map((_, i) =>
    `<td>${money(a.net_distributable_value_stated[i], a)}</td><td>${money(comp[i].net_distributable_value, a)}</td><td></td>`).join("") + "</tr>";
  const fulcrum = a.scenarios.map((s, i) => `<strong>${esc(s)}:</strong> ${esc(comp[i].fulcrum.join(", ") || "every class paid in full")}`).join(" · ");
  let note = "";
  if (!v.result.assessment.reconciles_with_filed) note = `<div class="note"><strong>Does not reconcile.</strong> Cells marked ✗ differ by more than 0.5 percentage points. The engine's figures are shown for transparency only; the filing's own figures remain the reference until a person reviews the structure.</div>`;
  $("#recon").innerHTML = `<div class="table-wrap"><table>${head}${rows}</table></div>
    <div class="fulcrum"><span class="fl-k">Fulcrum class (engine, as filed):</span> ${fulcrum}</div>${note}`;
}

// ---------- stress test ----------

function setupStress(v) {
  const a = v.result.analysis;
  const want = params.get("scenario"); params.delete("scenario");
  state.scenario = want !== null && +want < a.scenarios.length ? +want : Math.min(state.scenario, a.scenarios.length - 1);
  $("#scenario").innerHTML = a.scenarios.map((s, i) => `<option value="${i}" ${i === state.scenario ? "selected" : ""}>${esc(s)}</option>`).join("");
  buildSliders();
  stress();
}

// Cosmetic only: paints the filled part of a range track (CSS var --fill).
function paintRange(inp) {
  const min = +inp.min || 0, max = +inp.max || 100;
  inp.style.setProperty("--fill", `${Math.max(0, Math.min(100, ((+inp.value - min) / (max - min)) * 100))}%`);
}

function filedPct(asset) { return asset.recovery_pct[state.scenario] ?? (asset.book_value ? (100 * asset.recovery_value[state.scenario]) / asset.book_value : 0); }

function buildSliders() {
  const a = state.view.result.analysis;
  state.sliders = {};
  // The four most material non-cash assets are shown; the rest sit behind a toggle (cash recovers at 100% by definition).
  const assets = a.assets.filter((x) => x.book_value)
    .map((x) => ({ x, weight: /cash/i.test(x.label) ? -1 : Math.max(...x.recovery_value), b: x.book_value }))
    .sort((p, q) => q.weight - p.weight || q.b - p.b).map((o) => o.x);
  const main = Math.min(4, assets.length);
  $("#sliders").innerHTML = assets.map((x, j) => {
    const f = filedPct(x);
    const max = Math.max(100, Math.ceil((Math.max(...x.recovery_pct.map((p) => p || 0)) * 1.2) / 10) * 10);
    return `<label class="ctl" data-label="${esc(x.label)}">${esc(x.label)} <span class="val" id="sv-${j}">${pct(f)}</span>
      <input type="range" min="0" max="${max}" step="0.1" value="${f}" data-j="${j}">
      <span class="hint">Filed: ${pct(f)} of book (${money(x.recovery_value[state.scenario], a)} on ${money(x.book_value, a)})</span></label>`
      + (j === main - 1 && assets.length > main ? `<details class="more"><summary class="small">${assets.length - main} more asset line(s)</summary>` : "");
  }).join("") + (assets.length > main ? "</details>" : "");
  document.querySelectorAll("#sliders input").forEach((inp) => inp.addEventListener("input", () => {
    const x = assets[+inp.dataset.j];
    const val = +inp.value, f = filedPct(x);
    if (Math.abs(val - f) < 1e-9) delete state.sliders[x.label]; else state.sliders[x.label] = val;
    $(`#sv-${inp.dataset.j}`).textContent = pct(val);
    paintRange(inp);
    inp.closest(".ctl").classList.toggle("changed", x.label in state.sliders);
    debounceStress();
  }));
  // deep-link assumptions, e.g. ?o=Property, Plant %26 Equipment|13.7
  if (state.linkedO) params.delete("o"); state.linkedO = true;
  params.getAll("o").forEach((o) => {
    const [label, val] = o.split("|");
    const j = assets.findIndex((x) => x.label === label);
    if (j >= 0) { const inp = document.querySelector(`#sliders input[data-j="${j}"]`); inp.value = val; inp.dispatchEvent(new Event("input")); }
  });
  if (params.get("cost")) { $("#cost").value = params.get("cost"); params.delete("cost"); }
  $("#cost-val").textContent = `×${(+$("#cost").value).toFixed(2)}`;
  document.querySelectorAll("#sliders input, #cost").forEach(paintRange);
}

let stressTimer = null;
function debounceStress() { clearTimeout(stressTimer); stressTimer = setTimeout(stress, 150); }

async function stress() {
  const v = state.view; if (!v || !v.result) return;
  const body = { scenario: state.scenario, asset_pct: state.sliders, cost_multiplier: +$("#cost").value };
  try { renderStress(await api(`/api/runs/${v.name}/scenario`, { method: "POST", body: JSON.stringify(body) }), body); }
  catch (e) { $("#stress-out").innerHTML = `<div class="error">${esc(e.message)}</div>`; }
}

function renderStress(r, body) {
  const a = state.view.result.analysis, b = r.base, s = r.stressed;
  const kpi = (k, x, y) => `<div class="tile"><div class="k">${k} (${unitLabel(a)})</div><div class="v">${money(y, a)}</div><div class="small muted">engine on filed assumptions: ${money(x, a)}</div></div>`;
  const changed = Object.keys(body.asset_pct).length || body.cost_multiplier !== 1;
  let rows = "";
  s.classes.forEach((c, k) => {
    const d = c.pct - b.classes[k].pct;
    rows += `<tr><td>${esc(c.label)} <span class="muted small">P${c.priority}</span></td><td>${money(c.claim, a)}</td><td>${pct(b.classes[k].pct)}</td><td><strong>${pct(c.pct)}</strong></td>
      <td class="${Math.abs(d) < 0.05 ? "" : d > 0 ? "up" : "down"}">${Math.abs(d) < 0.05 ? "—" : (d > 0 ? "+" : "") + fmt(d, 1) + " pts"}</td>
      <td><div class="bar"><span style="width:${Math.min(100, c.pct)}%"></span><i style="left:${Math.min(100, b.classes[k].pct)}%"></i></div></td></tr>`;
  });
  const bf = b.fulcrum.join(", ") || "none (all paid in full)", sf = s.fulcrum.join(", ") || "none (all paid in full)";
  const moved = bf !== sf;
  const assumptions = Object.entries(body.asset_pct).map(([k, val]) => `${esc(k)} at ${pct(val)} of book`)
    .concat(body.cost_multiplier !== 1 ? [`liquidation costs ×${body.cost_multiplier.toFixed(2)}`] : []);
  $("#stress-out").innerHTML = `
    <div class="kpis">${kpi("Gross proceeds", b.gross_proceeds, s.gross_proceeds)}${kpi("Liquidation adjustments", b.adjustments, s.adjustments)}${kpi("Net distributable value", b.net_distributable_value, s.net_distributable_value)}</div>
    <div class="assume"><strong>Analyst assumptions (${esc(r.scenario)} case):</strong> ${assumptions.length ? assumptions.join("; ") : "none — filed assumptions"}</div>
    <div class="table-wrap"><table><tr><th>Creditor class (payment priority)</th><th>Claim</th><th>Filed assumptions</th><th>Your scenario</th><th>Change</th><th>Recovery (bar = scenario, tick = filed)</th></tr>${rows}</table></div>
    <div class="fulcrum-box ${moved ? "moved" : ""}">
      <strong>${moved ? "Fulcrum moved" : "Fulcrum unchanged"}:</strong> ${moved ? `${esc(bf)} → <strong>${esc(sf)}</strong>` : esc(sf)}<br>
      <span class="small">The fulcrum is the most senior class that is not paid in full under these assumptions: classes above it are covered in full, classes below it receive nothing. It is typically the class whose claims convert into ownership of the reorganized company.${changed ? "" : " Move a slider to see how it shifts."}</span>
    </div>`;
}

// ---------- extracted tables + human review ----------

function provOf(field) { return state.view.result.provenance[field] || "extracted"; }
function shown(v) {
  if (v === null || v === undefined || v === "") return "";
  const n = Number(v); if (Number.isNaN(n)) return String(v);
  return n.toLocaleString("en-US", { maximumFractionDigits: 4 });
}
function cell(field, raw, cls = "") {
  const value = shown(raw);
  const p = provOf(field);
  const pill = p.startsWith("corrected") ? `<span class="prov corrected" title="${esc(p)}">edited</span>` : "";
  return `<input class="cell-input ${cls}" data-field="${field}" data-orig="${value ?? ""}" value="${value ?? ""}" title="${esc(p)}">${pill}`;
}
function rowProv(prefix) {
  const fields = Object.entries(state.view.result.provenance).filter(([k]) => k.startsWith(prefix));
  const corr = fields.filter(([, p]) => p.startsWith("corrected"));
  return corr.length ? `<span class="prov corrected">${esc(corr[0][1])}</span>` : `<span class="prov">AI-extracted</span>`;
}
function flagged(label) { return (state.view.review_rows || []).some((r) => r.row_label === label && r.warnings.length); }

function renderTables(v) {
  const a = v.result.analysis, S = a.scenarios;
  const src = (t) => (t ? `<div class="src">cited: ${esc(t)}</div>` : `<div class="src">no source row cited</div>`);
  let h = `<div class="small muted units">Units: ${unitLabel(a)} · scenarios: ${S.map(esc).join(", ")} · rounding step ${a.rounding_step} (set by code)</div>`;
  h += `<div class="table-wrap"><table><tr><th>Asset</th><th>Book value</th>${S.map((s) => `<th>${esc(s)} %</th>`).join("")}${S.map((s) => `<th>${esc(s)} $</th>`).join("")}</tr>`;
  a.assets.forEach((x, i) => {
    h += `<tr class="${flagged(x.label) ? "flagged" : ""}"><td><strong>${esc(x.label)}</strong> ${rowProv(`assets[${i}]`)}${src(x.source_text)}</td><td>${cell(`assets[${i}].book_value`, x.book_value)}</td>`
      + S.map((_, j) => `<td>${cell(`assets[${i}].recovery_pct[${j}]`, x.recovery_pct[j])}</td>`).join("")
      + S.map((_, j) => `<td>${cell(`assets[${i}].recovery_value[${j}]`, x.recovery_value[j])}</td>`).join("") + "</tr>";
  });
  h += `<tr><td><strong>Stated gross proceeds</strong>${src((a.totals_source_text || [])[0])}</td><td></td>${S.map(() => "<td></td>").join("")}${S.map((_, j) => `<td>${cell(`gross_proceeds_stated[${j}]`, a.gross_proceeds_stated[j])}</td>`).join("")}</tr>`;
  a.adjustments.forEach((x, i) => {
    h += `<tr class="${flagged(x.label) ? "flagged" : ""}"><td>${esc(x.label)} ${rowProv(`adjustments[${i}]`)}${src(x.source_text)}</td><td></td>${S.map(() => "<td></td>").join("")}${S.map((_, j) => `<td>${cell(`adjustments[${i}].amounts[${j}]`, x.amounts[j])}</td>`).join("")}</tr>`;
  });
  h += `<tr><td><strong>Stated net distributable value</strong>${src((a.totals_source_text || [])[1])}</td><td></td>${S.map(() => "<td></td>").join("")}${S.map((_, j) => `<td>${cell(`net_distributable_value_stated[${j}]`, a.net_distributable_value_stated[j])}</td>`).join("")}</tr></table></div>`;
  h += `<div class="table-wrap" style="margin-top:14px"><table><tr><th>Claim class</th><th>Priority</th><th>Claim</th>${S.map((s) => `<th>${esc(s)} filed %</th>`).join("")}${S.map((s) => `<th>${esc(s)} filed $</th>`).join("")}</tr>`;
  a.claims.forEach((c, i) => {
    h += `<tr class="${flagged(c.label) ? "flagged" : ""}"><td><strong>${esc(c.label)}</strong> ${rowProv(`claims[${i}]`)}${src(c.source_text)}</td><td>${cell(`claims[${i}].priority`, c.priority, "prio")}</td><td>${cell(`claims[${i}].amount`, c.amount)}</td>`
      + S.map((_, j) => `<td>${cell(`claims[${i}].filed_recovery_pct[${j}]`, c.filed_recovery_pct[j])}</td>`).join("")
      + S.map((_, j) => `<td>${cell(`claims[${i}].filed_recovery_value[${j}]`, (c.filed_recovery_value || [])[j])}</td>`).join("") + "</tr>";
  });
  h += "</table></div>";
  $("#tables").innerHTML = h;
  document.querySelectorAll(".cell-input").forEach((inp) => inp.addEventListener("input", () => {
    const f = inp.dataset.field;
    if (inp.value.trim() === inp.dataset.orig) delete state.pending[f];
    else state.pending[f] = inp.value.trim();
    inp.classList.toggle("pending", f in state.pending);
    updateReviewBar();
  }));
  if (state.linkedEdit) params.delete("edit"); state.linkedEdit = true;
  params.getAll("edit").forEach((e) => { // deep link, e.g. ?edit=claims[1].priority:2
    const k = e.lastIndexOf(":"); const inp = document.querySelector(`.cell-input[data-field="${CSS.escape(e.slice(0, k))}"]`);
    if (inp) { inp.value = e.slice(k + 1); inp.dispatchEvent(new Event("input")); }
  });
  if (params.get("by")) $("#reviewer").value = params.get("by");
}

function updateReviewBar() {
  const n = Object.keys(state.pending).length;
  $("#review-bar").classList.toggle("hidden", !n);
  $("#pending-count").textContent = `${n} pending correction${n === 1 ? "" : "s"} (not applied yet)`;
}

async function applyCorrections() {
  const by = $("#reviewer").value.trim();
  if (!by) { $("#reviewer").focus(); $("#reviewer").placeholder = "Your name is required"; return; }
  const corrections = [];
  for (const [field, raw] of Object.entries(state.pending)) {
    const value = raw === "" ? null : Number(raw.replace(/,/g, ""));
    if (raw !== "" && Number.isNaN(value)) { showError(`Not a number: ${field} = ${raw}`); return; }
    corrections.push({ field, value: field.endsWith("priority") ? Math.round(value) : value });
  }
  try {
    const v = await api(`/api/runs/${state.view.name}/corrections`, { method: "POST", body: JSON.stringify({ by, corrections }) });
    render(v);
    await loadCases(state.slug);
    $("#status-card").scrollIntoView({ behavior: "smooth" });
  } catch (e) { showError(e.message); $("#step-case").scrollIntoView(); }
}

function renderReference(v) {
  const r = v.reference_check;
  if (!r || r.error) { $("#reference").innerHTML = `<p class="muted">${esc(r?.error || "not available")}</p>`; return; }
  const issues = r.wrong.map((w) => `<li>${esc(w.field)}: expected ${esc(w.expected)}, extracted ${esc(w.extracted)}</li>`).concat(r.missing.slice(0, 20).map((m) => `<li>missing: ${esc(m)}</li>`));
  $("#reference").innerHTML = `<p><strong>${r.correct} of ${r.fields_scored} fields</strong> match the hand-keyed answer key (${fmt(r.accuracy * 100, 1)}%).
    The answer key (data/cases/&lt;case&gt;/case.json) was typed by hand from the same filed table and is used only to score runs; it is never sent to the model and never replaces an extracted value.
    Differences can be judgment calls (e.g. subtotal vs line items), not only errors.</p>${issues.length ? `<ul class="small">${issues.join("")}</ul>` : ""}`;
}

// ---------- wiring ----------

$("#run").addEventListener("click", runLive);
$("#saved").addEventListener("change", (e) => e.target.value && openRun(e.target.value));
$("#scenario").addEventListener("change", (e) => { state.scenario = +e.target.value; buildSliders(); stress(); });
$("#cost").addEventListener("input", () => { $("#cost-val").textContent = `×${(+$("#cost").value).toFixed(2)}`; paintRange($("#cost")); debounceStress(); });
$("#reset").addEventListener("click", () => { $("#cost").value = 1; buildSliders(); stress(); });
$("#apply").addEventListener("click", applyCorrections);
$("#discard").addEventListener("click", () => render(state.view));

(async () => {
  try {
    await loadCases(params.get("case"));
    if (params.get("run")) await openRun(params.get("run"));
    const only = (params.get("only") || "").split(",").filter(Boolean);
    if (only.length) document.querySelectorAll("main > section, #result > section, #result > .grid2 > section").forEach((el) => {
      if (!only.includes(el.id) && el.id !== "status-card") el.classList.add("hidden");
    });
    const focus = params.get("focus");
    if (focus) setTimeout(() => document.getElementById(focus)?.scrollIntoView(), 400);
  } catch (e) { showError(`Could not reach the server: ${e.message}`); }
})();
