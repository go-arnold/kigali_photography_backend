/* static/js/dashboard.js
   Kigali Photography — Dashboard JS
   All rendering, state management, API calls, and actions live here.
   ─────────────────────────────────────────────────────────────────── */
"use strict";

const API_BASE = "/api/dashboard";

// ─── Utilities ───────────────────────────────────────────────────────────────
function getCsrf() {
  return (
    document.cookie.split(";").map((c) => c.trim())
      .find((c) => c.startsWith("csrftoken="))?.split("=")[1] || ""
  );
}

async function req(method, path, body) {
  const opts = {
    method, credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRFToken": getCsrf() },
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(API_BASE + path, opts);
  if (r.status === 401 || r.status === 403) { doLogout(); return null; }
  if (r.status === 204) return {};
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || data.error || Object.values(data).flat().join(", ") || `HTTP ${r.status}`);
  return data;
}

function toast(msg, type = "") {
  const c = document.getElementById("toasts");
  const el = document.createElement("div");
  el.className = `toast ${type === "ok" ? "ok" : type === "err" ? "err" : ""}`;
  el.innerHTML = `<span>${type === "ok" ? "✓" : type === "err" ? "✕" : "i"}</span>${msg}`;
  c.appendChild(el);
  setTimeout(() => el.remove(), 3400);
}

function ago(dt) {
  if (!dt) return "—";
  const s = Math.floor((Date.now() - new Date(dt)) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

function fmtDate(dt) {
  if (!dt) return "—";
  return new Date(dt).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

function fmtDateTime(dt) {
  if (!dt) return "—";
  const d = new Date(dt);
  return d.toLocaleDateString("en-GB", { day: "2-digit", month: "short" }) + " " +
    d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

function esc(s) {
  return String(s || "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function openSidebar() {
  document.getElementById("sidebar")?.classList.add("open");
  document.getElementById("sb-overlay")?.classList.add("open");
}
function closeSidebar() {
  document.getElementById("sidebar")?.classList.remove("open");
  document.getElementById("sb-overlay")?.classList.remove("open");
}

// ─── State ───────────────────────────────────────────────────────────────────
let S = {
  page: "overview", user: "",
  stats: null, statsLoading: true,
  approvals: [], approvalsLoading: true,
  clients: [], clientsLoading: true,
  bookings: [], bookingsLoading: true,
  bookingFilter: "upcoming",
  clientSearch: "", clientFilter: "all",
  modal: null, detail: null, detailLoading: false, detailTab: "info",
};

function set(patch) { Object.assign(S, patch); render(); }

// ─── Fetchers ────────────────────────────────────────────────────────────────
async function fetchStats() {
  set({ statsLoading: true });
  try { set({ stats: await req("GET", "/stats/"), statsLoading: false }); }
  catch { set({ statsLoading: false }); }
}

async function fetchApprovals() {
  set({ approvalsLoading: true });
  try { set({ approvals: (await req("GET", "/approvals/")) || [], approvalsLoading: false }); }
  catch { set({ approvalsLoading: false }); }
}

async function fetchClients() {
  set({ clientsLoading: true });
  try { set({ clients: (await req("GET", "/clients/")) || [], clientsLoading: false }); }
  catch { set({ clientsLoading: false }); }
}

async function fetchBookings() {
  set({ bookingsLoading: true });
  try {
    set({
      bookings: (await req("GET", `/bookings/?filter=${S.bookingFilter}`)) || [],
      bookingsLoading: false,
    });
  } catch { set({ bookingsLoading: false }); }
}

async function fetchDetail(pk) {
  set({ detailLoading: true, detail: null });
  try { set({ detail: await req("GET", `/clients/${pk}/`), detailLoading: false }); }
  catch (e) { set({ detailLoading: false }); toast(e.message, "err"); }
}

function nav(page) {
  closeSidebar(); set({ page });
  if (page === "overview") { fetchStats(); fetchApprovals(); }
  if (page === "approvals") fetchApprovals();
  if (page === "clients") fetchClients();
  if (page === "bookings") fetchBookings();
}

// ─── Actions ─────────────────────────────────────────────────────────────────
async function approveItem(id, sendNow) {
  try {
    await req("POST", `/approvals/${id}/approve/`, { send_immediately: sendNow });
    toast(sendNow ? "Approved & sent via WhatsApp" : "Approved", "ok");
    fetchApprovals(); fetchStats(); closeModal();
  } catch (e) { toast(e.message, "err"); }
}

async function rejectItem(id, notes) {
  try {
    await req("POST", `/approvals/${id}/reject/`, { notes: notes || "" });
    toast("Rejected", "ok");
    fetchApprovals(); fetchStats(); closeModal();
  } catch (e) { toast(e.message, "err"); }
}

async function sendManual(pk, message) {
  if (!message?.trim()) { toast("Message cannot be empty", "err"); return; }
  try {
    await req("POST", `/clients/${pk}/message/`, { to: String(pk), message: message.trim() });
    toast("Message sent", "ok"); closeModal();
  } catch (e) { toast(e.message, "err"); }
}

async function takeover(pk, enable) {
  try {
    await req("POST", `/clients/${pk}/takeover/`, { enable });
    toast(enable ? "Human takeover active — AI silenced" : "Released back to AI", "ok");
    fetchClients(); fetchStats();
    if (S.detail && S.detail.id === pk) fetchDetail(pk);
    closeModal();
  } catch (e) { toast(e.message, "err"); }
}

async function overrideJourney(pk, data) {
  try {
    await req("POST", `/clients/${pk}/journey/`, data);
    toast("Journey updated", "ok");
    fetchClients();
    if (S.detail && S.detail.id === pk) fetchDetail(pk);
    closeModal();
  } catch (e) { toast(e.message, "err"); }
}

// Booking actions
async function saveBooking(data, editId) {
  try {
    if (editId) {
      await req("PATCH", `/bookings/${editId}/`, data);
      toast("Booking updated", "ok");
    } else {
      await req("POST", "/bookings/", data);
      toast("Booking created", "ok");
    }
    fetchBookings(); closeModal();
  } catch (e) { toast(e.message, "err"); }
}

async function deleteBooking(id, name) {
  if (!confirm(`Delete booking for ${name}? This cannot be undone.`)) return;
  try {
    await req("DELETE", `/bookings/${id}/`);
    toast("Booking deleted", "ok");
    fetchBookings();
  } catch (e) { toast(e.message, "err"); }
}

function closeModal() { set({ modal: null }); }

// ─── Component helpers ───────────────────────────────────────────────────────
function heatBadge(label) {
  const map = { HIGH: "ba", MEDIUM: "bd", LOW: "bg" };
  return `<span class="badge ${map[label] || "bn"}">${label || "—"}</span>`;
}

function heatBar(score, label) {
  const cls = { HIGH: "hf-high", MEDIUM: "hf-medium", LOW: "hf-low" }[label] || "hf-low";
  return `<div class="heat-wrap">
    <div class="heat-track"><div class="heat-fill ${cls}" style="width:${score || 0}%"></div></div>
    <span class="heat-num">${score || 0}</span>
  </div>`;
}

function statusBadge(s) {
  const map = { booked: "bb", new: "bn", contacted: "bn", quoted: "bd" };
  return s ? `<span class="badge ${map[s] || "bn"}">${s}</span>` : "—";
}

function genderIcon(g) {
  return g === "boy" ? "👦" : g === "girl" ? "👧" : "🧒";
}

function packageBadge(pkg) {
  const map = { starter: "bn", silver: "bd", gold: "ba" };
  const labels = { starter: "🥉 Starter", silver: "🥈 Silver", gold: "🥇 Gold" };
  return `<span class="badge ${map[pkg] || "bn"}">${labels[pkg] || pkg}</span>`;
}

function daysUntil(dateStr) {
  if (!dateStr) return null;
  const diff = Math.ceil((new Date(dateStr) - new Date()) / 86400000);
  return diff;
}

// ─── Pages ───────────────────────────────────────────────────────────────────
function pageOverview() {
  const s = S.stats || {};
  const L = S.statsLoading;
  const v = (x) => (L ? '<span class="spin"></span>' : x);
  const pending = S.approvals.filter((a) => a.status === "pending");

  return `
<div class="stats-row">
  <div class="stat ${(s.pending_approvals || 0) > 0 ? "stat-alert" : ""}">
    <div class="stat-label">Pending</div>
    <div class="stat-val">${v(s.pending_approvals ?? 0)}</div>
    <div class="stat-sub">approvals</div>
  </div>
  <div class="stat ${(s.active_human_takeovers || 0) > 0 ? "stat-alert" : ""}">
    <div class="stat-label">Takeovers</div>
    <div class="stat-val">${v(s.active_human_takeovers ?? 0)}</div>
    <div class="stat-sub">AI silenced</div>
  </div>
  <div class="stat g">
    <div class="stat-label">Conversations</div>
    <div class="stat-val">${v(s.total_conversations ?? 0)}</div>
    <div class="stat-sub">all time</div>
  </div>
  <div class="stat">
    <div class="stat-label">Over Budget</div>
    <div class="stat-val">${v(s.conversations_over_budget ?? 0)}</div>
    <div class="stat-sub">conversations</div>
  </div>
  <div class="stat b">
    <div class="stat-label">API Cost</div>
    <div class="stat-val" style="font-size:20px">$${v((s.estimated_cost_usd || 0).toFixed(4))}</div>
    <div class="stat-sub">${(s.total_tokens_used || 0).toLocaleString()} tokens</div>
  </div>
  <div class="stat g">
    <div class="stat-label">Cost / Conv</div>
    <div class="stat-val" style="font-size:20px">$${v(s.total_conversations ? ((s.estimated_cost_usd || 0) / s.total_conversations).toFixed(4) : "0.0000")}</div>
    <div class="stat-sub">average</div>
  </div>
</div>
<div class="panel">
  <div class="panel-head">
    <span style="font-size:15px">🔔</span>
    <h2>Pending Approvals</h2>
    <span class="count">${pending.length}</span>
    <div class="panel-actions">
      <button class="refresh" onclick="fetchApprovals();fetchStats()">↻ Refresh</button>
    </div>
  </div>
  ${S.approvalsLoading
    ? '<div class="loading"><span class="spin"></span>Loading…</div>'
    : pending.length === 0
      ? `<div class="empty"><div class="empty-icon">✓</div><h3>Queue is clear</h3><p>No messages waiting for review</p></div>`
      : `<div class="table-wrap"><table>
        <thead><tr><th>Client</th><th>Action</th><th>AI Suggestion</th><th>Heat</th><th>Age</th><th>Actions</th></tr></thead>
        <tbody>${pending.map((a) => `<tr>
          <td><div class="name">${esc(a.client_name || "Unknown")}</div><div class="phone">${esc(a.client_phone || "")}</div></td>
          <td><span class="badge ba">${esc(a.action)}</span></td>
          <td><div class="trunc muted">${esc(a.ai_suggestion || "—")}</div></td>
          <td>${heatBadge(a.heat_label)}</td>
          <td class="mono muted" style="font-size:11px">${ago(a.created_at)}</td>
          <td><div class="flex aic gap1">
            <button class="btn btn-green btn-sm" onclick="openApproval(${a.id})">Review</button>
            <button class="btn btn-red btn-sm" onclick="quickReject(${a.id})">✕</button>
          </div></td>
        </tr>`).join("")}</tbody>
      </table></div>`
  }
</div>`;
}

function pageApprovals() {
  const all = S.approvals;
  return `
<div class="panel">
  <div class="panel-head">
    <h2>Approval Queue</h2>
    <span class="count">${all.length}</span>
    <div class="panel-actions">
      <button class="refresh" onclick="fetchApprovals()">↻ Refresh</button>
    </div>
  </div>
  ${S.approvalsLoading
    ? '<div class="loading"><span class="spin"></span>Loading…</div>'
    : all.length === 0
      ? `<div class="empty"><div class="empty-icon">📭</div><h3>Nothing here yet</h3><p>Messages flagged for review will appear here</p></div>`
      : `<div class="table-wrap"><table>
        <thead><tr><th>Client</th><th>Action</th><th>Status</th><th>AI Suggestion</th><th>Heat</th><th>Created</th><th>Actions</th></tr></thead>
        <tbody>${all.map((a) => `<tr>
          <td><div class="name">${esc(a.client_name || "Unknown")}</div><div class="phone">${esc(a.client_phone || "")}</div></td>
          <td><span class="badge bn">${esc(a.action)}</span></td>
          <td><span class="badge ${a.status === "pending" ? "ba" : a.status === "approved" ? "bg" : "br"}">${a.status}</span></td>
          <td><div class="trunc muted">${esc(a.ai_suggestion || "—")}</div></td>
          <td>${heatBadge(a.heat_label)}</td>
          <td class="mono muted" style="font-size:11px">${fmtDate(a.created_at)}</td>
          <td>${a.status === "pending"
            ? `<div class="flex aic gap1">
                <button class="btn btn-green btn-sm" onclick="openApproval(${a.id})">Review</button>
                <button class="btn btn-red btn-sm" onclick="quickReject(${a.id})">✕</button>
              </div>`
            : `<span class="muted" style="font-size:11px">${a.reviewed_at ? ago(a.reviewed_at) : "—"}</span>`
          }</td>
        </tr>`).join("")}</tbody>
      </table></div>`
  }
</div>`;
}

function pageClients() {
  let list = S.clients;
  if (S.clientSearch) {
    const q = S.clientSearch.toLowerCase();
    list = list.filter((c) => (c.name || "").toLowerCase().includes(q) || (c.wa_number || "").includes(q));
  }
  if (S.clientFilter === "takeover") list = list.filter((c) => c.human_takeover);
  if (S.clientFilter === "pending") list = list.filter((c) => c.pending_approvals > 0);
  if (S.clientFilter === "booked") list = list.filter((c) => c.status === "booked");
  if (S.clientFilter === "high") list = list.filter((c) => c.heat_label === "HIGH");
  if (S.clientFilter === "optout") list = list.filter((c) => c.is_opted_out);

  return `
<div class="flex aic gap2 mb4 clients-toolbar">
  <div class="flex aic gap2" style="margin-left:auto;flex-wrap:wrap">
    <input class="f-input" style="width:210px;padding:5px 10px" type="text" placeholder="Search name or phone…"
      value="${esc(S.clientSearch)}" oninput="set({clientSearch:this.value})">
    <select class="f-input" style="width:150px;padding:5px 10px" onchange="set({clientFilter:this.value})">
      <option value="all" ${S.clientFilter === "all" ? "selected" : ""}>All clients</option>
      <option value="high" ${S.clientFilter === "high" ? "selected" : ""}>High heat</option>
      <option value="takeover" ${S.clientFilter === "takeover" ? "selected" : ""}>Human takeover</option>
      <option value="pending" ${S.clientFilter === "pending" ? "selected" : ""}>Pending approval</option>
      <option value="booked" ${S.clientFilter === "booked" ? "selected" : ""}>Booked</option>
      <option value="optout" ${S.clientFilter === "optout" ? "selected" : ""}>Opted out</option>
    </select>
    <button class="refresh" onclick="fetchClients()">↻</button>
  </div>
</div>
<div class="panel">
  <div class="panel-head">
    <h2>Clients</h2>
    <span class="count">${list.length} of ${S.clients.length}</span>
  </div>
  ${S.clientsLoading
    ? '<div class="loading"><span class="spin"></span>Loading…</div>'
    : list.length === 0
      ? `<div class="empty"><div class="empty-icon">👥</div><h3>No clients found</h3><p>They appear once they message the bot</p></div>`
      : `<div class="table-wrap"><table>
        <thead><tr><th>Name</th><th>Phone</th><th>Status</th><th>Heat</th><th>Phase</th><th>Lang</th><th>Last Seen</th><th>Actions</th></tr></thead>
        <tbody>${list.map((c) => `<tr>
          <td><div class="flex aic gap1">
            ${c.human_takeover ? '<span title="Takeover active" style="font-size:12px">👤</span>' : ""}
            ${c.pending_approvals > 0 ? `<span title="${c.pending_approvals} pending" style="font-size:12px">🔔</span>` : ""}
            ${c.is_opted_out ? '<span title="Opted out" style="font-size:12px">🔕</span>' : ""}
            <span class="name">${esc(c.name || "Unknown")}</span>
          </div></td>
          <td class="phone">${esc(c.wa_number || "—")}</td>
          <td>${statusBadge(c.status)}</td>
          <td>${heatBar(c.heat_score, c.heat_label)}</td>
          <td class="muted" style="font-size:12px">${esc(c.phase || "—")}/${esc(c.step || "—")}</td>
          <td class="mono" style="font-size:11px">${(c.language || "en").toUpperCase()}</td>
          <td class="mono muted" style="font-size:11px">${ago(c.last_contact)}</td>
          <td><div class="flex aic gap1">
            <button class="btn btn-ghost btn-xs" onclick="openDetail(${c.id})">View</button>
            <button class="btn btn-ghost btn-xs" onclick="openMessage(${c.id},'${esc(c.name || "Client")}','${esc(c.wa_number || "")}')">✉</button>
            <button class="btn ${c.human_takeover ? "btn-green" : "btn-red"} btn-xs"
              onclick="takeover(${c.id},${!c.human_takeover})">
              ${c.human_takeover ? "Release" : "Takeover"}
            </button>
          </div></td>
        </tr>`).join("")}</tbody>
      </table></div>`
  }
</div>`;
}

function pageBookings() {
  const list = S.bookings;
  const today = new Date().toISOString().split("T")[0];

  return `
<div class="panel">
  <div class="panel-head">
    <span style="font-size:15px">📸</span>
    <h2>Bookings</h2>
    <span class="count">${list.length}</span>
    <div class="panel-actions">
      <div class="flex aic gap1">
        <select class="f-input" style="width:130px;padding:4px 8px;font-size:12px"
          onchange="set({bookingFilter:this.value});fetchBookings()">
          <option value="upcoming" ${S.bookingFilter === "upcoming" ? "selected" : ""}>Upcoming</option>
          <option value="past" ${S.bookingFilter === "past" ? "selected" : ""}>Past</option>
          <option value="all" ${S.bookingFilter === "all" ? "selected" : ""}>All</option>
        </select>
        <button class="refresh" onclick="fetchBookings()">↻ Refresh</button>
        <button class="btn btn-accent btn-sm" onclick="openBookingForm(null)">+ Add Booking</button>
      </div>
    </div>
  </div>

  ${S.bookingsLoading
    ? '<div class="loading"><span class="spin"></span>Loading…</div>'
    : list.length === 0
      ? `<div class="empty">
          <div class="empty-icon">📅</div>
          <h3>No bookings yet</h3>
          <p>Click <strong>+ Add Booking</strong> to register a confirmed session</p>
        </div>`
      : `<div class="table-wrap"><table>
        <thead>
          <tr>
            <th>Child</th>
            <th>Parent</th>
            <th>Phone</th>
            <th>Package</th>
            <th>Occasion</th>
            <th>Booking Date</th>
            <th>Time</th>
            <th>Birthday</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          ${list.map((b) => {
            const days = daysUntil(b.booking_day);
            const isToday = b.booking_day === today;
            const isSoon = days !== null && days >= 0 && days <= 3;
            const rowClass = isToday ? "style='background:rgba(255,200,0,0.08)'" : isSoon ? "style='background:rgba(255,150,0,0.05)'" : "";
            return `<tr ${rowClass}>
              <td>
                <div class="flex aic gap1">
                  <span>${genderIcon(b.child_gender)}</span>
                  <div>
                    <div class="name">${esc(b.child_name)}</div>
                    <div class="muted" style="font-size:11px">${esc(b.child_age)}</div>
                  </div>
                </div>
              </td>
              <td><div class="name">${esc(b.parent_name)}</div></td>
              <td class="phone">${esc(b.phone)}</td>
              <td>
                ${packageBadge(b.package)}
                ${b.extras ? `<div class="muted" style="font-size:11px;margin-top:3px">${esc(b.extras)}</div>` : ""}
              </td>
              <td><span class="badge bn">${esc(b.occasion)}</span></td>
              <td>
                <div class="mono" style="font-size:13px">${fmtDate(b.booking_day)}</div>
                ${isToday
                  ? `<span class="badge ba" style="font-size:10px;margin-top:3px">TODAY</span>`
                  : isSoon
                    ? `<span class="badge bd" style="font-size:10px;margin-top:3px">in ${days}d</span>`
                    : ""
                }
              </td>
              <td class="mono">${esc(b.booking_time)}</td>
              <td class="mono muted" style="font-size:11px">
                ${b.child_birthday
                  ? `🎂 ${fmtDate(b.child_birthday)}`
                  : '<span class="muted">—</span>'
                }
              </td>
              <td>
                <div class="flex aic gap1">
                  <button class="btn btn-ghost btn-xs" onclick="openBookingForm(${JSON.stringify(b).replace(/</g,"\\u003c").replace(/>/g,"\\u003e").replace(/&/g,"\\u0026")})">
                    ✏ Edit
                  </button>
                  <button class="btn btn-red btn-xs" onclick="deleteBooking(${b.id},'${esc(b.child_name)}')">
                    🗑 Delete
                  </button>
                </div>
              </td>
            </tr>`;
          }).join("")}
        </tbody>
      </table></div>`
  }
</div>`;
}

// ─── Modals ───────────────────────────────────────────────────────────────────
function openApproval(id) {
  const a = S.approvals.find((x) => x.id === id);
  if (!a) return;
  set({ modal: { type: "approval", data: a } });
}

function quickReject(id) {
  if (confirm("Reject this approval?")) rejectItem(id, "");
}

function openMessage(pk, name, phone) {
  set({ modal: { type: "message", pk, name, phone } });
}

function openDetail(pk) {
  set({ modal: { type: "detail", pk }, detailTab: "info" });
  fetchDetail(pk);
}

function openJourneyEdit(c) {
  set({ modal: { type: "journey", client: c } });
}

function openBookingForm(booking) {
  set({ modal: { type: "booking", booking } });
}

function renderBookingForm(booking) {
  const b = booking || {};
  const isEdit = !!b.id;
  const title = isEdit ? `Edit Booking — ${esc(b.child_name)}` : "Add New Booking";

  return `
<div class="modal modal-lg">
  <div class="modal-head">
    <h3>${title}</h3>
    <button class="btn btn-ghost btn-icon btn-sm" onclick="closeModal()">✕</button>
  </div>
  <div class="modal-body">

    <div class="section-hd" style="margin-bottom:12px">👤 Parent / Contact</div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Parent Name *</label>
        <input class="f-input" id="bk-parent" type="text" value="${esc(b.parent_name || "")}" placeholder="Full name">
      </div>
      <div class="f-group">
        <label class="f-label">Phone *</label>
        <input class="f-input" id="bk-phone" type="text" value="${esc(b.phone || "")}" placeholder="250...">
      </div>
    </div>

    <div class="section-hd" style="margin:16px 0 12px">👶 Child Info</div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Child Name *</label>
        <input class="f-input" id="bk-child" type="text" value="${esc(b.child_name || "")}" placeholder="First name">
      </div>
      <div class="f-group">
        <label class="f-label">Gender</label>
        <select class="f-input" id="bk-gender">
          <option value="girl" ${b.child_gender === "girl" ? "selected" : ""}>👧 Girl</option>
          <option value="boy" ${b.child_gender === "boy" ? "selected" : ""}>👦 Boy</option>
          <option value="other" ${b.child_gender === "other" ? "selected" : ""}>🧒 Other</option>
        </select>
      </div>
    </div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Age</label>
        <input class="f-input" id="bk-age" type="text" value="${esc(b.child_age || "")}" placeholder="e.g. 2 years, 6 months">
      </div>
      <div class="f-group">
        <label class="f-label">Birthday <span class="muted" style="font-weight:400">(auto-schedules wishes)</span></label>
        <input class="f-input" id="bk-birthday" type="date" value="${esc(b.child_birthday || "")}">
      </div>
    </div>

    <div class="section-hd" style="margin:16px 0 12px">📸 Session Details</div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Occasion</label>
        <select class="f-input" id="bk-occasion">
          <option value="birthday" ${(b.occasion || "birthday") === "birthday" ? "selected" : ""}>🎂 Birthday</option>
          <option value="milestone" ${b.occasion === "milestone" ? "selected" : ""}>🏆 Milestone</option>
          <option value="family" ${b.occasion === "family" ? "selected" : ""}>👨‍👩‍👧 Family Portrait</option>
          <option value="graduation" ${b.occasion === "graduation" ? "selected" : ""}>🎓 Graduation</option>
          <option value="other" ${b.occasion === "other" ? "selected" : ""}>Other</option>
        </select>
      </div>
      <div class="f-group">
        <label class="f-label">Package *</label>
        <select class="f-input" id="bk-package">
          <option value="starter" ${(b.package || "starter") === "starter" ? "selected" : ""}>🥉 Starter</option>
          <option value="silver" ${b.package === "silver" ? "selected" : ""}>🥈 Silver</option>
          <option value="gold" ${b.package === "gold" ? "selected" : ""}>🥇 Gold</option>
        </select>
      </div>
    </div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Extras</label>
        <input class="f-input" id="bk-extras" type="text" value="${esc(b.extras || "")}" placeholder="e.g. Birthday Cake, 2 A5 Frames, Highlight Video">
      </div>
      <div class="f-group">
        <label class="f-label">Preferred Outfit</label>
        <input class="f-input" id="bk-outfit" type="text" value="${esc(b.preferred_outfit || "")}" placeholder="e.g. Pink dress, casual">
      </div>
    </div>

    <div class="section-hd" style="margin:16px 0 12px">📅 Booking Date & Time</div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Booking Day *</label>
        <input class="f-input" id="bk-day" type="date" value="${esc(b.booking_day || "")}">
      </div>
      <div class="f-group">
        <label class="f-label">Booking Time *</label>
        <input class="f-input" id="bk-time" type="time" value="${esc(b.booking_time || "")}">
      </div>
    </div>

    <div class="f-group">
      <label class="f-label">Notes</label>
      <textarea class="f-input" id="bk-notes" rows="2" placeholder="Any additional notes…">${esc(b.notes || "")}</textarea>
    </div>

    ${b.child_birthday ? `
    <div style="background:rgba(99,199,99,0.08);border:1px solid rgba(99,199,99,0.2);border-radius:8px;padding:12px;margin-top:8px;font-size:13px;color:#aaa">
      🎂 Birthday messages will be auto-scheduled: 1 week before, 1 day before, day-of, and next year.
    </div>` : `
    <div style="background:rgba(255,200,0,0.06);border:1px solid rgba(255,200,0,0.15);border-radius:8px;padding:12px;margin-top:8px;font-size:13px;color:#aaa">
      💡 Add a birthday date to automatically schedule birthday wishes for this child.
    </div>`}

  </div>
  <div class="modal-foot">
    <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
    <button class="btn btn-accent" onclick="submitBookingForm(${b.id || "null"})">
      ${isEdit ? "💾 Save Changes" : "✓ Create Booking"}
    </button>
  </div>
</div>`;
}

function submitBookingForm(editId) {
  const get = (id) => document.getElementById(id)?.value?.trim() || "";

  // Validation
  const required = {
    "bk-parent": "Parent name",
    "bk-phone": "Phone",
    "bk-child": "Child name",
    "bk-day": "Booking day",
    "bk-time": "Booking time",
  };
  for (const [id, label] of Object.entries(required)) {
    if (!get(id)) { toast(`${label} is required`, "err"); return; }
  }

  const data = {
    parent_name: get("bk-parent"),
    phone: get("bk-phone"),
    child_name: get("bk-child"),
    child_gender: get("bk-gender"),
    child_age: get("bk-age"),
    child_birthday: get("bk-birthday") || null,
    occasion: get("bk-occasion"),
    package: get("bk-package"),
    extras: get("bk-extras"),
    preferred_outfit: get("bk-outfit"),
    notes: get("bk-notes"),
    booking_day: get("bk-day"),
    booking_time: get("bk-time"),
  };

  saveBooking(data, editId);
}

function renderModal() {
  const m = S.modal;
  if (!m) return "";
  let inner = "";

  if (m.type === "approval") {
    const a = m.data;
    inner = `
    <div class="modal">
      <div class="modal-head">
        <h3>Review Approval</h3>
        <button class="btn btn-ghost btn-icon btn-sm" onclick="closeModal()">✕</button>
      </div>
      <div class="modal-body">
        <div class="d-grid mb4">
          <div class="d-item"><div class="d-label">Client</div><div class="d-val">${esc(a.client_name)}</div></div>
          <div class="d-item"><div class="d-label">Phone</div><div class="d-val phone">${esc(a.client_phone)}</div></div>
          <div class="d-item"><div class="d-label">Action</div><div class="d-val"><span class="badge ba">${esc(a.action)}</span></div></div>
          <div class="d-item"><div class="d-label">Heat</div><div class="d-val">${heatBadge(a.heat_label)} ${a.heat_score_at_suggestion}</div></div>
          <div class="d-item"><div class="d-label">Created</div><div class="d-val mono" style="font-size:12px">${fmtDateTime(a.created_at)}</div></div>
          <div class="d-item"><div class="d-label">Expires</div><div class="d-val mono" style="font-size:12px">${fmtDateTime(a.expires_at)}</div></div>
        </div>
        <div class="ai-box">
          <div class="ai-box-label">AI Suggestion</div>
          <div class="ai-box-text">${esc(a.ai_suggestion || "No suggestion")}</div>
          ${a.ai_reasoning ? `<div class="ai-box-reason">${esc(a.ai_reasoning)}</div>` : ""}
        </div>
        <div class="f-group">
          <label class="f-label">Notes (optional)</label>
          <textarea class="f-input" id="ap-notes" rows="2" placeholder="Add context for the team…"></textarea>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn btn-red" onclick="rejectItem(${a.id}, document.getElementById('ap-notes').value)">✕ Reject</button>
        <button class="btn btn-green" onclick="approveItem(${a.id}, false)">✓ Approve</button>
        <button class="btn btn-accent" onclick="approveItem(${a.id}, true)">⚡ Approve & Send</button>
      </div>
    </div>`;
  }

  if (m.type === "message") {
    inner = `
    <div class="modal">
      <div class="modal-head">
        <h3>Message ${esc(m.name)}</h3>
        <button class="btn btn-ghost btn-icon btn-sm" onclick="closeModal()">✕</button>
      </div>
      <div class="modal-body">
        <p class="muted mb3" style="font-size:13px">Sends directly from the studio WhatsApp number, bypassing AI.</p>
        <div class="d-grid mb4">
          <div class="d-item"><div class="d-label">To</div><div class="d-val phone">${esc(m.phone)}</div></div>
        </div>
        <div class="f-group">
          <label class="f-label">Message</label>
          <textarea class="f-input" id="msg-body" rows="5" placeholder="Type your message here…"></textarea>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn btn-accent" onclick="sendManual(${m.pk}, document.getElementById('msg-body').value)">Send via WhatsApp</button>
      </div>
    </div>`;
  }

  if (m.type === "detail") {
    const c = S.detail;
    const loading = S.detailLoading;
    const tab = S.detailTab;
    inner = `
    <div class="modal modal-lg">
      <div class="modal-head">
        <h3>${c ? esc(c.name || "Client") : "Loading…"}</h3>
        <button class="btn btn-ghost btn-icon btn-sm" onclick="closeModal()">✕</button>
      </div>
      <div class="modal-body">
        ${loading ? '<div class="loading"><span class="spin"></span></div>'
          : !c ? '<div class="loading muted">Not found</div>'
          : `
        <div class="tabs">
          <div class="tab ${tab === "info" ? "active" : ""}" onclick="set({detailTab:'info'})">Info</div>
          <div class="tab ${tab === "messages" ? "active" : ""}" onclick="set({detailTab:'messages'})">Messages</div>
        </div>
        ${tab === "info" ? `
        <div class="section-hd">Contact & Journey</div>
        <div class="d-grid mb4">
          <div class="d-item"><div class="d-label">Phone</div><div class="d-val phone">${esc(c.wa_number)}</div></div>
          <div class="d-item"><div class="d-label">Language</div><div class="d-val">${(c.language || "en").toUpperCase()}</div></div>
          <div class="d-item"><div class="d-label">Status</div><div class="d-val">${statusBadge(c.status)}</div></div>
          <div class="d-item"><div class="d-label">Phase / Step</div><div class="d-val">${esc(c.phase || "—")} / ${esc(c.step || "—")}</div></div>
          <div class="d-item"><div class="d-label">Heat</div><div class="d-val">${heatBadge(c.heat_label)} ${c.heat_score}</div></div>
          <div class="d-item"><div class="d-label">Token Budget</div><div class="d-val mono">${c.token_budget_pct || 0}% used</div></div>
          <div class="d-item"><div class="d-label">Human Takeover</div><div class="d-val">${c.human_takeover ? '<span class="badge ba">ACTIVE</span>' : '<span class="muted">Off</span>'}</div></div>
          <div class="d-item"><div class="d-label">Opted Out</div><div class="d-val">${c.is_opted_out ? '<span class="badge br">YES</span>' : '<span class="muted">No</span>'}</div></div>
        </div>
        <hr class="div">
        <div class="flex aic gap2" style="flex-wrap:wrap">
          <button class="btn btn-ghost btn-sm" onclick="openMessage(${c.id},'${esc(c.name || "Client")}','${esc(c.wa_number || "")}');closeModal()">✉ Send Message</button>
          <button class="btn ${c.human_takeover ? "btn-green" : "btn-red"} btn-sm" onclick="takeover(${c.id},${!c.human_takeover})">
            ${c.human_takeover ? "Release to AI" : "Enable Takeover"}
          </button>
          <button class="btn btn-ghost btn-sm" onclick="openJourneyEdit(${JSON.stringify(c).replace(/</g,"\\u003c").replace(/>/g,"\\u003e").replace(/&/g,"\\u0026")})">Edit Journey</button>
        </div>
        ` : `
        <div class="msg-list">
          ${!(c.recent_messages && c.recent_messages.length)
            ? `<div class="empty"><p>No messages yet</p></div>`
            : [...c.recent_messages].reverse().map((msg) =>
                msg.direction === "inbound"
                  ? `<div class="msg-row-in"><div>
                      <div class="msg-bubble msg-bubble-in">${esc(msg.content)}</div>
                      <div class="msg-meta">${ago(msg.timestamp)}</div>
                    </div></div>`
                  : `<div class="msg-row-out"><div>
                      <div class="msg-bubble msg-bubble-out">${esc(msg.content)}</div>
                      <div class="msg-meta msg-meta-out">${msg.generated_by_ai ? "🤖 AI" : "👤 Staff"} · ${ago(msg.timestamp)}</div>
                    </div></div>`
              ).join("")
          }
        </div>`
        }`}
      </div>
    </div>`;
  }

  if (m.type === "journey") {
    const c = m.client;
    inner = `
    <div class="modal">
      <div class="modal-head">
        <h3>Edit Journey</h3>
        <button class="btn btn-ghost btn-icon btn-sm" onclick="closeModal()">✕</button>
      </div>
      <div class="modal-body">
        <div class="f-row">
          <div class="f-group">
            <label class="f-label">Phase</label>
            <select class="f-input" id="j-phase">
              ${["entry","package","booking","prep","delivery","feedback"].map((p) =>
                `<option value="${p}" ${c.phase === p ? "selected" : ""}>${p}</option>`
              ).join("")}
            </select>
          </div>
          <div class="f-group">
            <label class="f-label">Heat Score (0–100)</label>
            <input class="f-input" type="number" id="j-heat" min="0" max="100" value="${c.heat_score || 50}">
          </div>
        </div>
        <div class="f-group">
          <label class="f-label">
            <input type="checkbox" id="j-release" ${c.human_takeover ? "" : "disabled"}>
            Release human takeover
          </label>
        </div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
        <button class="btn btn-accent" onclick="overrideJourney(${c.id},{
          phase: document.getElementById('j-phase').value,
          heat_score: parseInt(document.getElementById('j-heat').value),
          release_takeover: document.getElementById('j-release').checked
        })">Save Changes</button>
      </div>
    </div>`;
  }

  if (m.type === "booking") {
    inner = renderBookingForm(m.booking);
  }

  return `<div class="overlay" onclick="if(event.target===this)closeModal()">${inner}</div>`;
}

// ─── Login ────────────────────────────────────────────────────────────────────
function renderLogin() {
  return `
  <div class="login-page">
    <div class="login-card">
      <div class="login-logo">Kigali Photography</div>
      <div class="login-sub">Studio dashboard — staff access only</div>
      <div class="login-err" id="lerr"></div>
      <div class="f-group">
        <label class="f-label">Username</label>
        <input class="f-input" id="lu" type="text" autocomplete="username" placeholder="username">
      </div>
      <div class="f-group">
        <label class="f-label">Password</label>
        <input class="f-input" id="lp" type="password" autocomplete="current-password" placeholder="••••••••"
          onkeydown="if(event.key==='Enter')doLogin()">
      </div>
      <button class="btn btn-dark w100" style="width:100%;justify-content:center;padding:10px;font-size:14px" id="lbtn" onclick="doLogin()">
        Sign in →
      </button>
    </div>
  </div>`;
}

async function doLogin() {
  const u = document.getElementById("lu")?.value?.trim();
  const p = document.getElementById("lp")?.value;
  if (!u || !p) return;
  const btn = document.getElementById("lbtn");
  btn.disabled = true;
  btn.textContent = "Signing in…";
  try {
    await fetch("/admin/login/", { credentials: "include" }).catch(() => {});
    await fetch("/admin/login/", {
      method: "POST", credentials: "include",
      headers: { "Content-Type": "application/x-www-form-urlencoded", "X-CSRFToken": getCsrf() },
      body: `username=${encodeURIComponent(u)}&password=${encodeURIComponent(p)}&next=/`,
      redirect: "manual",
    });
    const check = await fetch(API_BASE + "/stats/", { credentials: "include" });
    if (check.ok || check.status !== 403) {
      S.user = u;
      startDashboard();
    } else {
      throw new Error("Invalid username or password");
    }
  } catch (e) {
    const err = document.getElementById("lerr");
    if (err) { err.style.display = "block"; err.textContent = e.message; }
    btn.disabled = false;
    btn.textContent = "Sign in →";
  }
}

function doLogout() {
  fetch("/admin/logout/", { method: "POST", credentials: "include", headers: { "X-CSRFToken": getCsrf() } });
  S.user = "";
  document.getElementById("root").innerHTML = renderLogin();
}

// ─── Main render ──────────────────────────────────────────────────────────────
function render() {
  const root = document.getElementById("root");
  const { page, stats } = S;
  const pendingCount = S.approvals.filter((a) => a.status === "pending").length;

  const navItems = [
    { id: "overview", icon: "◈", label: "Overview" },
    { id: "approvals", icon: "🔔", label: "Approvals", badge: pendingCount || "" },
    { id: "clients", icon: "👥", label: "Clients" },
    { id: "bookings", icon: "📸", label: "Bookings" },
  ];

  const pageContent = {
    overview: pageOverview,
    approvals: pageApprovals,
    clients: pageClients,
    bookings: pageBookings,
  }[page]?.() || "";

  const titles = {
    overview: "Overview",
    approvals: "Approval Queue",
    clients: "Clients",
    bookings: "Bookings",
  };

  root.innerHTML = `
  <div id="app">
    <div class="sb-overlay" id="sb-overlay" onclick="closeSidebar()"></div>
    <nav class="sidebar" id="sidebar">
      <div class="sb-brand">
        <div class="sb-brand-name">Kigali<br>Photography</div>
        <div class="sb-brand-tag">Studio Dashboard</div>
      </div>
      <div class="sb-nav">
        <div class="sb-section">Navigation</div>
        ${navItems.map((n) => `
          <div class="sb-item ${page === n.id ? "active" : ""}" onclick="nav('${n.id}')">
            <span class="sb-item-icon">${n.icon}</span>
            <span>${n.label}</span>
            ${n.badge ? `<span class="sb-badge">${n.badge}</span>` : ""}
          </div>`).join("")}
      </div>
      <div class="sb-footer">
        <div class="sb-user">@${esc(S.user)}</div>
        <button class="sb-signout" onclick="doLogout()">Sign out</button>
      </div>
    </nav>
    <div class="main">
      <div class="topbar">
        <button class="sb-toggle" onclick="openSidebar()" aria-label="Open menu">&#9776;</button>
        <span class="topbar-title">${titles[page] || ""}</span>
        <div class="topbar-meta">
          <span class="topbar-dot"></span>
          <span>Live</span>
          ${stats ? `· $${(stats.estimated_cost_usd || 0).toFixed(4)} spent` : ""}
          ${stats ? `· ${(stats.total_tokens_used || 0).toLocaleString()} tokens` : ""}
        </div>
      </div>
      <div class="content">${pageContent}</div>
    </div>
  </div>
  ${renderModal()}`;
}

// ─── Boot ─────────────────────────────────────────────────────────────────────
function startDashboard() {
  nav("overview");
  setInterval(() => {
    if (S.page === "overview") { fetchStats(); fetchApprovals(); }
  }, 30000);
}

(async () => {
  await fetch("/admin/login/", { credentials: "include" }).catch(() => {});
  const r = await fetch(API_BASE + "/stats/", { credentials: "include" });
  if (r.ok) {
    try {
      const info = await fetch("/admin/", { credentials: "include" });
      const html = await info.text();
      const match = html.match(/class="user-name">([^<]+)</);
      if (match) S.user = match[1].trim();
    } catch {}
    startDashboard();
  } else {
    document.getElementById("root").innerHTML = renderLogin();
  }
})();
