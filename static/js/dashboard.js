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
  bookingSearch: "",
  bookingDateFrom: "",
  bookingDateTo: "",
  bookingTimeFrom: "",
  bookingTimeTo: "",
  analytics: null,
  analyticsLoading: false,
  analyticsPeriod: "30d",
  analyticsFrom: "",
  analyticsTo: "",
  //message dashboard view ajoute
  chatClientId: null,        // ID du client en cours de chat
  chatMessages: [],          // Messages chargés
  chatLoading: false,        // Loading initial
  chatLastTimestamp: null,   // Dernier timestamp reçu (pour polling)
  chatPollingInterval: null, // Référence au setInterval
  chatHumanTakeover: false,  // Human takeover actif ?
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
  if (page === "analytics") fetchAnalytics();
}

//_______________________________________autres fetcher

// ─── Chat en temps réel ───────────────────────────────────────────────────────

async function openChat(pk, name, phone) {
  // Arrêter tout polling existant
  stopChatPolling();

  set({
    modal: { type: "chat", pk, name, phone },
    chatClientId: pk,
    chatMessages: [],
    chatLoading: true,
    chatLastTimestamp: null,
    chatHumanTakeover: false,
  });

  // Charger tous les messages initiaux
  await loadChatMessages(pk, null);

  // Démarrer le polling toutes les 10 secondes
  S.chatPollingInterval = setInterval(() => {
    if (S.chatClientId === pk && S.modal?.type === "chat") {
      pollChatMessages(pk);
    } else {
      stopChatPolling();
    }
  }, 10000);
}

async function loadChatMessages(pk, since) {
  try {
    let path = `/clients/${pk}/messages/`;
    if (since) path += `?since=${encodeURIComponent(since)}`;
 
    const data = await req("GET", path);
    if (!data) return;
 
    if (since) {
      if (data.messages && data.messages.length > 0) {
        // ← DÉDUPLICATION : éviter les doublons par id ou wa_message_id
        const existingIds = new Set(S.chatMessages.map(m => m.id));
        const newMsgs = data.messages.filter(m => !existingIds.has(m.id));
        
        if (newMsgs.length > 0) {
          S.chatMessages = [...S.chatMessages, ...newMsgs];
          S.chatLastTimestamp = newMsgs[newMsgs.length - 1].timestamp;
          S.chatHumanTakeover = data.human_takeover;
          render();
          setTimeout(() => {
            const list = document.getElementById("chat-msg-list");
            if (list) list.scrollTop = list.scrollHeight;
          }, 50);
        } else {
          // Mettre à jour takeover même sans nouveaux messages
          if (S.chatHumanTakeover !== data.human_takeover) {
            S.chatHumanTakeover = data.human_takeover;
            render();
          }
        }
      }
    } else {
      S.chatMessages = data.messages || [];
      S.chatHumanTakeover = data.human_takeover;
      S.chatLoading = false;
      if (data.messages && data.messages.length > 0) {
        S.chatLastTimestamp = data.messages[data.messages.length - 1].timestamp;
      }
      render();
      setTimeout(() => {
        const list = document.getElementById("chat-msg-list");
        if (list) list.scrollTop = list.scrollHeight;
      }, 100);
    }
  } catch (e) {
    S.chatLoading = false;
    render();
  }
}

async function pollChatMessages(pk) {
  // Polling silencieux — pas de spinner
  await loadChatMessages(pk, S.chatLastTimestamp);
}

function stopChatPolling() {
  if (S.chatPollingInterval) {
    clearInterval(S.chatPollingInterval);
    S.chatPollingInterval = null;
  }
}

async function sendChatMessage(pk) {
  const input = document.getElementById("chat-input");
  const message = input?.value?.trim();
  if (!message) return;  // ← ne rien faire si vide
 
  const btn = document.getElementById("chat-send-btn");
  if (btn) { btn.disabled = true; }
 
  try {
    await req("POST", `/clients/${pk}/message/`, { to: String(pk), message });
    input.value = "";
    input.style.height = "auto";  // reset hauteur textarea
 
    const now = new Date().toISOString();
    // ← ID unique pour éviter doublons au polling
    const localId = `local_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    S.chatMessages.push({
      id: localId,
      direction: "outbound",
      content: message,
      msg_type: "text",
      timestamp: now,
      generated_by_ai: false,
      approved_by_human: true,
    });
    S.chatLastTimestamp = now;
    render();
 
    setTimeout(() => {
      const list = document.getElementById("chat-msg-list");
      if (list) list.scrollTop = list.scrollHeight;
    }, 50);
 
  } catch (e) {
    toast(e.message, "err");
  } finally {
    if (btn) { btn.disabled = false; }
  }
}

// État enregistrement vocal
let S_recorder = { stream: null, recorder: null, chunks: [], recording: false };

async function sendMediaFromDashboard(pk) {
  const input = document.getElementById("chat-file-input");
  if (!input || !input.files.length) return;
  const file = input.files[0];
 
  // Reset input immédiatement pour éviter double déclenchement
  const fileRef = file;
  input.value = "";
 
  toast("Sending…", "");
 
  try {
    const formData = new FormData();
    formData.append("file", fileRef);
 
    const r = await fetch(API_BASE + `/clients/${pk}/media/`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": getCsrf() },
      body: formData,
    });
 
    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${r.status}`);
    }
 
    const data = await r.json();
    toast("✓ Sent", "ok");
 
    const now = new Date().toISOString();
    const localId = `local_media_${Date.now()}`;
    const mime = fileRef.type || "";
 
    // Pour les images: créer un URL objet pour prévisualisation immédiate
    const localUrl = mime.startsWith("image/") || mime.startsWith("audio/")
      ? URL.createObjectURL(fileRef)
      : "";
 
    S.chatMessages.push({
      id: localId,
      direction: "outbound",
      content: fileRef.name || `[${data.type}]`,
      msg_type: data.type,
      media_url: data.url || localUrl,   // URL serveur en priorité
      media_mime_type: mime,
      media_filename: fileRef.name,
      timestamp: now,
      generated_by_ai: false,
      approved_by_human: true,
    });
    S.chatLastTimestamp = now;
    render();
    setTimeout(() => {
      const list = document.getElementById("chat-msg-list");
      if (list) list.scrollTop = list.scrollHeight;
    }, 50);
 
  } catch (e) {
    toast(e.message, "err");
  }
}

async function startVoiceRecording(pk) {
  if (S_recorder.recording) {
    stopVoiceRecording();
    return;
  }
 
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
 
    // Ordre de préférence : webm (universel) → ogg → mp4
    let mimeType = "audio/webm;codecs=opus";
    if (!MediaRecorder.isTypeSupported(mimeType)) {
      mimeType = "audio/webm";
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        mimeType = "audio/ogg;codecs=opus";
        if (!MediaRecorder.isTypeSupported(mimeType)) {
          mimeType = "audio/mp4";
        }
      }
    }
 
    const recorder = new MediaRecorder(stream, { mimeType });
    S_recorder = { stream, recorder, chunks: [], recording: true, pk, mimeType };
 
    recorder.ondataavailable = (e) => {
      if (e.data && e.data.size > 0) {
        S_recorder.chunks.push(e.data);
      }
    };
 
    recorder.onstop = async () => {
      // ← CRITIQUE : sauvegarder AVANT le reset (évite la race condition)
      const savedPk   = S_recorder.pk;
      const savedMime = S_recorder.mimeType || "audio/webm";
      const chunks    = [...(S_recorder.chunks || [])];
 
      // Nettoyage immédiat du stream
      if (S_recorder.stream) {
        S_recorder.stream.getTracks().forEach(t => t.stop());
      }
      S_recorder = { stream: null, recorder: null, chunks: [], recording: false };
      updateSendBtn(); // remettre le bouton en vert
      render();
 
      // Vérifier qu'on a des données
      const totalSize = chunks.reduce((acc, c) => acc + c.size, 0);
      if (totalSize === 0) {
        toast("No audio recorded — try again", "err");
        return;
      }
 
      const actualMime = savedMime.split(";")[0]; // "audio/webm" ou "audio/ogg"
      const ext = actualMime.includes("ogg") ? ".ogg" : ".webm";
      const blob = new Blob(chunks, { type: actualMime });
 
      if (blob.size === 0) {
        toast("Empty recording — try again", "err");
        return;
      }
 
      toast("Sending voice note…", "");
 
      const fileName = `voice_${Date.now()}${ext}`;
      const file = new File([blob], fileName, { type: actualMime });
      const formData = new FormData();
      formData.append("file", file);
 
      try {
        const r = await fetch(API_BASE + `/clients/${savedPk}/media/`, {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRFToken": getCsrf() },
          body: formData,
        });
 
        let data = {};
        try { data = await r.json(); } catch {}
 
        if (r.ok) {
          toast("✓ Voice note sent", "ok");
          const objUrl = URL.createObjectURL(blob);
          const now = new Date().toISOString();
 
          S.chatMessages.push({
            id: `local_voice_${Date.now()}`,
            direction: "outbound",
            content: "[Voice note]",
            msg_type: "audio",
            media_url: data.url || objUrl,
            media_mime_type: actualMime,
            timestamp: now,
            generated_by_ai: false,
            approved_by_human: true,
          });
          S.chatLastTimestamp = now;
          render();
          setTimeout(() => {
            const list = document.getElementById("chat-msg-list");
            if (list) list.scrollTop = list.scrollHeight;
          }, 50);
        } else {
          toast((data.error || `Send failed HTTP ${r.status}`), "err");
          console.error("Voice note send error:", r.status, data);
        }
      } catch (e) {
        toast("Network error: " + e.message, "err");
        console.error("Voice note exception:", e);
      }
    };
 
    recorder.start(250); // chunk toutes les 250ms
    updateSendBtn();     // bouton rouge ⏹
    render();
    toast("🔴 Recording… tap again to stop", "");
 
  } catch (e) {
    toast("Microphone: " + e.message, "err");
    S_recorder = { stream: null, recorder: null, chunks: [], recording: false };
    updateSendBtn();
  }
}

function stopVoiceRecording() {
  if (S_recorder.recording && S_recorder.recorder) {
    S_recorder.recorder.stop(); // déclenche onstop async
    S_recorder.recording = false;
    updateSendBtn();
    render();
  }
}

function renderMediaMessage(msg, isIn) {
  const mime = msg.media_mime_type || "";
  const url  = msg.media_url || "";
  const filename = msg.media_filename || "file";

  const fullUrl = url.startsWith("http") || url.startsWith("blob:")
    ? url
    : (window.location.origin + url);

  if (!fullUrl || fullUrl === window.location.origin) {
    return `<div style="font-size:12px;opacity:0.7;font-style:italic">[${msg.msg_type || "media"}]</div>`;
  }

  if (mime.startsWith("image/") || msg.msg_type === "image") {
    return `
      <div style="max-width:220px;cursor:pointer" onclick="window.open('${fullUrl}','_blank')">
        <img src="${fullUrl}"
          style="width:100%;border-radius:8px;display:block;max-height:200px;object-fit:cover"
          alt=""
          onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"
        >
        <div style="display:none;padding:10px;font-size:13px;color:#666;align-items:center;gap:6px">
          📷 <span>Image</span>
        </div>
      </div>`;
  }

  if (mime.startsWith("audio/") || msg.msg_type === "audio" || msg.msg_type === "voice") {
    return `
      <div style="min-width:220px;max-width:280px">
        <div style="font-size:11px;opacity:0.75;margin-bottom:5px">
          🎙️ ${msg.msg_type === "voice" ? "Voice note" : "Audio"}
        </div>
        <audio controls style="width:100%;height:36px;outline:none" preload="metadata">
          <source src="${fullUrl}" type="${mime || 'audio/ogg'}">
          <source src="${fullUrl}">
        </audio>
      </div>`;
  }

  return `
    <a href="${fullUrl}" target="_blank" style="
      display:flex;align-items:center;gap:10px;
      color:inherit;text-decoration:none;
      background:rgba(255,255,255,0.12);
      border-radius:10px;padding:10px 14px;
      min-width:180px;max-width:250px;
    ">
      <span style="font-size:28px">${_docIcon(mime)}</span>
      <div style="overflow:hidden">
        <div style="font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
          ${esc(filename)}
        </div>
        <div style="font-size:11px;opacity:0.65">Tap to open</div>
      </div>
    </a>`;
}

function _docIcon(mime) {
  if (mime.includes("pdf")) return "📄";
  if (mime.includes("word") || mime.includes("doc")) return "📝";
  if (mime.includes("sheet") || mime.includes("excel")) return "📊";
  return "📎";
}

async function toggleTakeoverFromChat(pk, enable) {
  try {
    await req("POST", `/clients/${pk}/takeover/`, { enable });
    S.chatHumanTakeover = enable;
    toast(enable ? "Human takeover active — AI silenced" : "Released back to AI", "ok");
    render();
  } catch (e) { toast(e.message, "err"); }
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

// function closeModal() { set({ modal: null }); }
function closeModal() {
  stopChatPolling();
  S.chatClientId = null;
  set({ modal: null });
} //dashboard direct message

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
            <button class="btn btn-ghost btn-xs" onclick="openChat(${c.id},'${esc(c.name || "Client")}','${esc(c.wa_number || "")}')">💬 Chat</button>
            
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
  let list = S.bookings;

  // Recherche
  if (S.bookingSearch) {
    const q = S.bookingSearch.toLowerCase();
    list = list.filter((b) =>
      (b.parent_name || "").toLowerCase().includes(q) ||
      (b.phone || "").includes(q) ||
      (b.child_name || "").toLowerCase().includes(q)
    );
  }

  // Filtre date
  if (S.bookingDateFrom) list = list.filter((b) => b.booking_day >= S.bookingDateFrom);
  if (S.bookingDateTo)   list = list.filter((b) => b.booking_day <= S.bookingDateTo);

  // Filtre heure
  if (S.bookingTimeFrom) list = list.filter((b) => b.booking_time >= S.bookingTimeFrom);
  if (S.bookingTimeTo)   list = list.filter((b) => b.booking_time <= S.bookingTimeTo);

  const today = new Date().toISOString().split("T")[0];

  return `
<div class="panel">
  <div class="panel-head">
    <span style="font-size:15px">📸</span>
    <h2>Bookings</h2>
    <span class="count">${list.length}</span>
    <div class="panel-actions">
      <div class="flex aic gap1" style="flex-wrap:wrap">
        <select class="f-input" style="width:120px;padding:4px 8px;font-size:12px"
          onchange="set({bookingFilter:this.value});fetchBookings()">
          <option value="upcoming" ${S.bookingFilter==="upcoming"?"selected":""}>Upcoming</option>
          <option value="past"     ${S.bookingFilter==="past"?"selected":""}>Past</option>
          <option value="all"      ${S.bookingFilter==="all"?"selected":""}>All</option>
        </select>
        <input class="f-input" type="text" placeholder="Search name / phone…" style="width:180px;padding:4px 8px;font-size:12px"
          value="${esc(S.bookingSearch||"")}" oninput="set({bookingSearch:this.value})">
        <input class="f-input" type="date" title="From date" style="width:130px;padding:4px 8px;font-size:12px"
          value="${esc(S.bookingDateFrom||"")}" onchange="set({bookingDateFrom:this.value})">
        <input class="f-input" type="date" title="To date" style="width:130px;padding:4px 8px;font-size:12px"
          value="${esc(S.bookingDateTo||"")}" onchange="set({bookingDateTo:this.value})">
        <input class="f-input" type="time" title="From time" style="width:100px;padding:4px 8px;font-size:12px"
          value="${esc(S.bookingTimeFrom||"")}" onchange="set({bookingTimeFrom:this.value})">
        <input class="f-input" type="time" title="To time" style="width:100px;padding:4px 8px;font-size:12px"
          value="${esc(S.bookingTimeTo||"")}" onchange="set({bookingTimeTo:this.value})">
        <button class="btn btn-ghost btn-sm" onclick="set({bookingSearch:'',bookingDateFrom:'',bookingDateTo:'',bookingTimeFrom:'',bookingTimeTo:''})">✕ Clear</button>
        <button class="refresh" onclick="fetchBookings()">↻</button>
        <button class="btn btn-accent btn-sm" onclick="openBookingForm(null)">+ Add</button>
      </div>
    </div>
  </div>
  ${S.bookingsLoading
    ? '<div class="loading"><span class="spin"></span>Loading…</div>'
    : list.length === 0
      ? `<div class="empty"><div class="empty-icon">📅</div><h3>No bookings</h3></div>`
      : `<div class="table-wrap"><table>
        <thead><tr>
          <th>Client</th><th>Date & Time</th><th>Package</th>
          <th>Occasion</th><th>Child</th><th>Actions</th>
        </tr></thead>
        <tbody>${list.map((b) => {
          const days = daysUntil(b.booking_day);
          const isToday = b.booking_day === today;
          const isSoon = days !== null && days >= 0 && days <= 3;
          const isChild = b.occasion === "child_celebration";
          return `<tr ${isToday?"style='background:rgba(255,200,0,0.08)'":(isSoon?"style='background:rgba(255,150,0,0.05)'":'')}>
            <td>
              <div class="name">${esc(b.parent_name)}</div>
              <div class="phone muted" style="font-size:11px">${esc(b.phone)}</div>
            </td>
            <td>
              <div class="mono" style="font-size:13px">${fmtDate(b.booking_day)}</div>
              <div class="mono muted" style="font-size:11px">${esc(b.booking_time)}</div>
              ${isToday?`<span class="badge ba" style="font-size:10px">TODAY</span>`:(isSoon?`<span class="badge bd" style="font-size:10px">in ${days}d</span>`:"")}
            </td>
            <td>
              ${packageBadge(b.package)}
              ${b.extras?`<div class="muted" style="font-size:11px;margin-top:2px">${esc(b.extras)}</div>`:""}
            </td>
            <td>
              <span class="badge bn">${isChild?"👶 Child":"📋 Other"}</span>
              ${isChild&&b.photo_type?`<div class="muted" style="font-size:11px;margin-top:2px">${b.photo_type==="family"?"👨‍👩‍👧 Family":"👶 Child"}</div>`:""}
            </td>
            <td>
              ${isChild
                ? `<div class="name">${b.child_gender?genderIcon(b.child_gender):""} ${esc(b.child_name||"—")}</div>
                   ${b.child_birthday?`<div class="muted" style="font-size:11px">🎂 ${fmtDate(b.child_birthday)}</div>`:"<div class='muted' style='font-size:11px'>—</div>"}`
                : `<span class="muted">—</span>`
              }
            </td>
            <td><div class="flex aic gap1">
              <button class="btn btn-ghost btn-xs" onclick="openBookingDetail(${b.id})">🔍 Details</button>
              <button class="btn btn-ghost btn-xs" onclick="openBookingFormById(${b.id})">✏ Edit</button>
              <button class="btn btn-red btn-xs" onclick="deleteBooking(${b.id},'${esc(b.parent_name)}')">🗑</button>
            </div></td>
          </tr>`;
        }).join("")}</tbody>
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

function openBookingFormById(id) {
  const booking = S.bookings.find((b) => b.id === id);
  if (!booking) { toast("Booking not found", "err"); return; }
  set({ modal: { type: "booking", booking } });
}

function renderBookingForm(booking) {
  const b = booking || {};
  const isEdit = !!b.id;
  const isChild = !b.occasion || b.occasion === "child_celebration";

  return `
<div class="modal modal-lg">
  <div class="modal-head">
    <h3>${isEdit ? `Edit — ${esc(b.parent_name||"")}` : "Add New Booking"}</h3>
    <button class="btn btn-ghost btn-icon btn-sm" onclick="closeModal()">✕</button>
  </div>
  <div class="modal-body">

    <div class="section-hd" style="margin-bottom:12px">👤 Client</div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Client Name *</label>
        <input class="f-input" id="bk-parent" type="text" value="${esc(b.parent_name||"")}" placeholder="Full name">
      </div>
      <div class="f-group">
        <label class="f-label">Phone *</label>
        <input class="f-input" id="bk-phone" type="text" value="${esc(b.phone||"")}" placeholder="250...">
      </div>
    </div>

    <div class="section-hd" style="margin:16px 0 12px">📅 Session</div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Booking Day *</label>
        <input class="f-input" id="bk-day" type="date" value="${esc(b.booking_day||"")}">
      </div>
      <div class="f-group">
        <label class="f-label">Booking Time *</label>
        <input class="f-input" id="bk-time" type="time" value="${esc(b.booking_time||"")}">
      </div>
    </div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Package *</label>
        <select class="f-input" id="bk-package">
          <option value="starter" ${(b.package||"starter")==="starter"?"selected":""}>🥉 Starter</option>
          <option value="silver"  ${b.package==="silver"?"selected":""}>🥈 Silver</option>
          <option value="gold"    ${b.package==="gold"?"selected":""}>🥇 Gold</option>
          <option value="premium" ${b.package==="premium"?"selected":""}>🏆 Premium (Home)</option>
        </select>
      </div>
      <div class="f-group">
        <label class="f-label">Extras</label>
        <input class="f-input" id="bk-extras" type="text" value="${esc(b.extras||"")}"
          placeholder="Cake, Frames, Video…">
      </div>
    </div>

    <div class="section-hd" style="margin:16px 0 12px">🎉 Occasion</div>
    <div class="f-row">
      <div class="f-group">
        <label class="f-label">Type *</label>
        <select class="f-input" id="bk-occasion" onchange="updateBookingOccasion()">
          <option value="child_celebration" ${isChild?"selected":""}>👶 Children's Celebration</option>
          <option value="other" ${b.occasion==="other"?"selected":""}>📋 Other</option>
        </select>
      </div>
    </div>

    <div id="bk-child-section" style="display:${isChild?"block":"none"}">
      <div class="section-hd" style="margin:16px 0 12px">👶 Child Info</div>
      <div class="f-row">
        <div class="f-group">
          <label class="f-label">Session Type</label>
          <select class="f-input" id="bk-photo-type">
            <option value="child"  ${(!b.photo_type||b.photo_type==="child")?"selected":""}>👶 Child Photoshoot</option>
            <option value="family" ${b.photo_type==="family"?"selected":""}>👨‍👩‍👧 Family Photoshoot</option>
          </select>
        </div>
        <div class="f-group">
          <label class="f-label">Child Name</label>
          <input class="f-input" id="bk-child" type="text" value="${esc(b.child_name||"")}" placeholder="First name">
        </div>
      </div>
      <div class="f-row">
        <div class="f-group">
          <label class="f-label">Birthday <span class="muted" style="font-weight:400">(auto-schedules wishes 🎂)</span></label>
          <input class="f-input" id="bk-birthday" type="date" value="${esc(b.child_birthday||"")}">
        </div>
        <div class="f-group">
          <label class="f-label">Gender</label>
          <select class="f-input" id="bk-gender">
            <option value="girl"  ${b.child_gender==="girl"?"selected":""}>👧 Girl</option>
            <option value="boy"   ${b.child_gender==="boy"?"selected":""}>👦 Boy</option>
            <option value="other" ${b.child_gender==="other"?"selected":""}>🧒 Other</option>
          </select>
        </div>
      </div>
      <div class="f-group">
        <label class="f-label">Preferred Outfit</label>
        <input class="f-input" id="bk-outfit" type="text" value="${esc(b.preferred_outfit||"")}"
          placeholder="e.g. Pink dress, casual">
      </div>
    </div>

    <div class="f-group" style="margin-top:12px">
      <label class="f-label">Notes</label>
      <textarea class="f-input" id="bk-notes" rows="2"
        placeholder="Any additional notes…">${esc(b.notes||"")}</textarea>
    </div>

    <div id="bk-birthday-hint" style="display:${isChild&&b.child_birthday?"block":"none"};
      background:rgba(99,199,99,0.08);border:1px solid rgba(99,199,99,0.2);
      border-radius:8px;padding:12px;margin-top:8px;font-size:13px;color:#aaa">
      🎂 Birthday messages will auto-schedule: 1 week before, day before, day-of, and next year.
    </div>

  </div>
  <div class="modal-foot">
    <button class="btn btn-ghost" onclick="closeModal()">Cancel</button>
    <button class="btn btn-accent" onclick="submitBookingForm(${b.id||"null"})">
      ${isEdit?"💾 Save Changes":"✓ Create Booking"}
    </button>
  </div>
</div>`;
}

function updateBookingOccasion() {
  const val = document.getElementById("bk-occasion")?.value;
  const section = document.getElementById("bk-child-section");
  if (section) section.style.display = val === "child_celebration" ? "block" : "none";
}

function submitBookingForm(editId) {
  const get = (id) => document.getElementById(id)?.value?.trim() || "";

  const required = { "bk-parent": "Client name", "bk-phone": "Phone",
                     "bk-day": "Booking day", "bk-time": "Booking time" };
  for (const [id, label] of Object.entries(required)) {
    if (!get(id)) { toast(`${label} is required`, "err"); return; }
  }

  const occasion = get("bk-occasion");
  const isChild = occasion === "child_celebration";

  const data = {
    parent_name:      get("bk-parent"),
    phone:            get("bk-phone"),
    booking_day:      get("bk-day"),
    booking_time:     get("bk-time"),
    package:          get("bk-package"),
    extras:           get("bk-extras"),
    occasion,
    notes:            get("bk-notes"),
    // Child fields — envoyés seulement si occasion = child_celebration
    photo_type:       isChild ? get("bk-photo-type") : "",
    child_name:       isChild ? get("bk-child")      : "",
    child_birthday:   isChild ? (get("bk-birthday") || null) : null,
    child_gender:     isChild ? get("bk-gender")     : "",
    preferred_outfit: isChild ? get("bk-outfit")     : "",
  };

  saveBooking(data, editId);
}

function openBookingDetail(id) {
  const b = S.bookings.find((x) => x.id === id);
  if (!b) return;
  set({ modal: { type: "bookingDetail", data: b } });
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
  // AJOUTE 
  if (m.type === "chat") {
  const msgs = S.chatMessages;
  const loading = S.chatLoading;
  const takeover = S.chatHumanTakeover;
  const isRecording = S_recorder.recording;

  // Helper: formater timestamp
  function fmtTime(ts) {
    if (!ts) return "";
    return new Date(ts).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
  }

  // Helper: rendre un message individuel
  function renderMsg(msg) {
    const isIn = msg.direction === "inbound";
    const time = fmtTime(msg.timestamp);
    const isInteractive = msg.msg_type === "interactive";
    const hasMedia = msg.media_url && msg.media_url.length > 0;
    const isCall = msg.msg_type === "call";
    const isVoice = msg.msg_type === "voice" || msg.msg_type === "audio";
    const isImage = msg.msg_type === "image";
    const isDoc = msg.msg_type === "document";

    // ── Message système (appel) ────────────────────────────────
    if (isCall) {
      return `<div style="display:flex;justify-content:center;margin:8px 0">
        <div style="background:#f0f0f0;border-radius:20px;padding:4px 14px;font-size:12px;color:#666">
          📞 Missed call attempt
        </div>
      </div>`;
    }

    // ── Contenu du message ─────────────────────────────────────
    let contentHtml = "";

    if (hasMedia) {
      contentHtml = renderMediaMessage(msg, isIn);
    } else if (isInteractive) {
      // Boutons envoyés par le bot
      const lines = msg.content.split("\\n");
      const bodyText = lines[0] || "";
      const btnLine = lines.slice(1).join(" ").trim();
      const btns = btnLine
        ? btnLine.split("|").map(b => b.replace(/[\\[\\]]/g, "").trim()).filter(Boolean)
        : [];
      contentHtml = `
        <div style="font-size:13px;margin-bottom:${btns.length ? "8px" : "0"}">${esc(bodyText)}</div>
        ${btns.length ? `<div style="display:flex;flex-wrap:wrap;gap:4px">
          ${btns.map(b => `<span style="
            background:rgba(0,168,132,0.15);
            border:1px solid rgba(0,168,132,0.4);
            color:#00a884;
            border-radius:16px;padding:3px 10px;font-size:11px;font-weight:600;
          ">${esc(b)}</span>`).join("")}
        </div>` : ""}
      `;
    } else {
      contentHtml = `<div style="white-space:pre-wrap;word-break:break-word;font-size:14px">${esc(msg.content)}</div>`;
    }

    // ── Bulle INBOUND (client → nous) ─────────────────────────
    if (isIn) {
      const isClientBtn = isInteractive || (msg.content && msg.content.startsWith("[button:"));
      return `
      <div style="display:flex;align-items:flex-end;gap:6px;max-width:72%;margin-bottom:2px">
        <div style="width:28px;height:28px;border-radius:50%;background:#25D366;
          display:flex;align-items:center;justify-content:center;
          font-size:12px;font-weight:bold;color:#fff;flex-shrink:0;margin-bottom:18px">
          ${esc((m.name || "?")[0].toUpperCase())}
        </div>
        <div>
          <div style="
            background:#fff;
            border-radius:0 12px 12px 12px;
            padding:8px 12px;
            box-shadow:0 1px 2px rgba(0,0,0,0.08);
            ${isClientBtn ? "border-left:3px solid #25D366;" : ""}
          ">
            ${isClientBtn ? `<div style="font-size:10px;color:#25D366;font-weight:600;margin-bottom:3px">👆 Button tap</div>` : ""}
            ${contentHtml}
          </div>
          <div style="font-size:10px;color:#999;margin-top:2px;padding-left:2px">${time}</div>
        </div>
      </div>`;
    }

    // ── Bulle OUTBOUND (nous → client) ────────────────────────
    const bubbleBg = isInteractive
      ? "linear-gradient(135deg,#128C7E,#075E54)"
      : msg.generated_by_ai
        ? "linear-gradient(135deg,#25D366,#128C7E)"
        : "#fff";
    const textColor = (isInteractive || msg.generated_by_ai) ? "#fff" : "#333";
    const border = (!isInteractive && !msg.generated_by_ai) ? "border:1px solid #e0e0e0;" : "";
    const senderLabel = msg.generated_by_ai
      ? "🤖 Julie · AI"
      : "👤 You · Staff";
    const senderColor = msg.generated_by_ai ? "#25D366" : "#128C7E";

    return `
    <div style="display:flex;justify-content:flex-end;margin-bottom:2px">
      <div style="max-width:72%">
        <div style="
          background:${bubbleBg};
          color:${textColor};
          border-radius:12px 0 12px 12px;
          padding:8px 12px;
          box-shadow:0 1px 2px rgba(0,0,0,0.12);
          ${border}
        ">
          ${contentHtml}
        </div>
        <div style="font-size:10px;color:${senderColor};margin-top:2px;text-align:right;padding-right:2px;font-weight:600">
          ${senderLabel} · ${time}
          ${msg.approved_by_human === null ? " · ⏳" : ""}
        </div>
      </div>
    </div>`;
  }

  // ── Zone de saisie (takeover requis) ──────────────────────────────────────
  const inputArea = takeover ? `
    <div style="display:flex;align-items:flex-end;gap:8px">
      
      <!-- Upload media -->
      <label title="Send image or document" style="
        width:40px;height:40px;border-radius:50%;
        background:#f0f0f0;cursor:pointer;
        display:flex;align-items:center;justify-content:center;
        font-size:18px;flex-shrink:0;
      ">
        📎
        <input type="file" id="chat-file-input" accept="image/*,.pdf,.doc,.docx"
          style="display:none"
          onchange="sendMediaFromDashboard(${m.pk})"
        >
      </label>

      <!-- Textarea -->
      <textarea
        id="chat-input"
        placeholder="Type a message…"
        rows="1"
        style="flex:1;resize:none;padding:10px 14px;border:1px solid #ddd;
          border-radius:20px;font-size:14px;font-family:inherit;
          background:#fff;outline:none;max-height:120px;overflow-y:auto;line-height:1.4;"
        oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,120)+'px';updateSendBtn()"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();sendChatMessage(${m.pk})}"
      ></textarea>

      <!-- Bouton adaptatif: Send si texte, Record si vide -->
      

      ${isRecording
        ? `<button onclick="stopVoiceRecording()" 
            style="
            width:44px;height:44px;border-radius:50%;border:none;cursor:pointer;
            background:#ef4444;color:#fff;font-size:18px;flex-shrink:0;
            animation:pulse 1s infinite;
          " title="Stop recording">⏹</button>`
        : `<button
        id="chat-send-btn"
        style="width:44px;height:44px;border-radius:50%;border:none;cursor:pointer;
          background:#25D366;color:#fff;font-size:20px;flex-shrink:0;transition:background 0.2s;"
        onclick="handleSendOrRecord(${m.pk})"
        title="Send or record voice"
      >🎙️</button>`
      }
    </div>
    <div style="font-size:10px;color:#999;margin-top:4px;text-align:center">
      Enter to send · Shift+Enter for newline · 📎 for files
    </div>
  ` : `
    <div style="
      background:#fff8e1;border:1px solid #ffc107;border-radius:12px;
      padding:12px 16px;font-size:13px;color:#795548;text-align:center;
    ">
      ⚠️ AI is active — click <strong>Take Over</strong> to reply or send media
    </div>
  `;

  inner = `
  <div class="modal modal-lg" style="
    height:88vh;display:flex;flex-direction:column;
    border-radius:12px;overflow:hidden;
  ">

    <!-- Header style WhatsApp -->
    <div style="
      background:linear-gradient(135deg,#075E54,#128C7E);
      padding:12px 16px;display:flex;align-items:center;gap:12px;
      flex-shrink:0;
    ">
      <!-- Avatar -->
      <div style="
        width:40px;height:40px;border-radius:50%;
        background:#25D366;display:flex;align-items:center;
        justify-content:center;font-size:16px;font-weight:bold;color:#fff;
        flex-shrink:0;
      ">${esc((m.name || "?")[0].toUpperCase())}</div>
      
      <!-- Infos -->
      <div style="flex:1">
        <div style="font-size:15px;font-weight:700;color:#fff">${esc(m.name || "Client")}</div>
        <div style="font-size:12px;color:rgba(255,255,255,0.75)">
          ${esc(m.phone || "")}
          · ${takeover
            ? '<span style="color:#ffd700">👤 You are in control</span>'
            : '<span style="color:#a0f0c0">🤖 AI responding</span>'}
        </div>
      </div>

      <!-- Actions -->
      <div style="display:flex;gap:8px;align-items:center">
        ${takeover
          ? `<button onclick="toggleTakeoverFromChat(${m.pk},false)" style="
              padding:6px 12px;border-radius:20px;border:none;cursor:pointer;
              background:rgba(255,255,255,0.2);color:#fff;font-size:12px;font-weight:600;
            ">Release to AI</button>`
          : `<button onclick="toggleTakeoverFromChat(${m.pk},true)" style="
              padding:6px 12px;border-radius:20px;border:none;cursor:pointer;
              background:#ef4444;color:#fff;font-size:12px;font-weight:600;
            ">Take Over</button>`
        }
        <div style="font-size:10px;color:rgba(255,255,255,0.6);display:flex;align-items:center;gap:4px">
          <span style="width:6px;height:6px;border-radius:50%;background:#25D366;display:inline-block"></span>
          Live · 10s
        </div>
        <button onclick="closeModal()" style="
          background:none;border:none;cursor:pointer;color:#fff;font-size:20px;
          width:32px;height:32px;border-radius:50%;
          display:flex;align-items:center;justify-content:center;
        ">✕</button>
      </div>
    </div>

    <!-- Zone messages style WhatsApp -->
    <div id="chat-msg-list" style="
      flex:1;overflow-y:auto;
      padding:12px 16px;
      display:flex;flex-direction:column;gap:4px;
      background: #e5ddd5 url('data:image/png;base64,iVBORw0KGgo=') center/400px;
    ">
      ${loading
        ? `<div style="display:flex;justify-content:center;align-items:center;height:100%;color:#666">
            <span class="spin"></span>&nbsp;Loading messages…
          </div>`
        : msgs.length === 0
          ? `<div style="display:flex;justify-content:center;align-items:center;height:100%">
              <div style="background:#fff;border-radius:12px;padding:12px 20px;font-size:13px;color:#999">
                💬 No messages yet
              </div>
            </div>`
          : msgs.map(renderMsg).join("")
      }
    </div>

    <!-- Zone de saisie -->
    <div style="
      flex-shrink:0;padding:10px 12px;
      background:#f0f0f0;border-top:1px solid #ddd;
    ">
      ${inputArea}
    </div>

  </div>
  `;
  // ── FIN CHAT MODAL ─────────────────────────────────────────────────────
}
//------

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
            : [...c.recent_messages].reverse().map((msg) => {
                msg.direction === "inbound"
                  ? `<div class="msg-row-in"><div>
                      <div class="msg-bubble msg-bubble-in">${esc(msg.content)}</div>
                      <div class="msg-meta">${ago(msg.timestamp)}</div>
                    </div></div>`
                  // Dans le rendu des messages, j'a remplace le bloc outbound par :
                  : `<div class="msg-row-out"><div>
                      <div class="msg-bubble msg-bubble-out">
                        ${msg.msg_type === "interactive" 
                          ? `<div style="font-style:italic;color:#aaa;font-size:12px">
                              [Interactive: ${esc(msg.content)}]
                            </div>`
                          : esc(msg.content)
                        }
                      </div>
                      <div class="msg-meta msg-meta-out">
                        ${msg.generated_by_ai ? "🤖 AI" : "👤 Staff"} · ${ago(msg.timestamp)}
                      </div>
                    </div></div>`
          }).join("")
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
  
  if (m.type === "bookingDetail") {
  const b = m.data;
  const isChild = b.occasion === "child_celebration";
  inner = `
  <div class="modal modal-lg">
    <div class="modal-head">
      <h3>Booking Details</h3>
      <button class="btn btn-ghost btn-icon btn-sm" onclick="closeModal()">✕</button>
    </div>
    <div class="modal-body">
      <div class="section-hd">👤 Client</div>
      <div class="d-grid mb4">
        <div class="d-item"><div class="d-label">Name</div><div class="d-val">${esc(b.parent_name)}</div></div>
        <div class="d-item"><div class="d-label">Phone</div><div class="d-val phone">${esc(b.phone)}</div></div>
      </div>
      <div class="section-hd">📅 Session</div>
      <div class="d-grid mb4">
        <div class="d-item"><div class="d-label">Date</div><div class="d-val mono">${fmtDate(b.booking_day)}</div></div>
        <div class="d-item"><div class="d-label">Time</div><div class="d-val mono">${esc(b.booking_time)}</div></div>
        <div class="d-item"><div class="d-label">Package</div><div class="d-val">${packageBadge(b.package)}</div></div>
        <div class="d-item"><div class="d-label">Extras</div><div class="d-val">${esc(b.extras||"—")}</div></div>
        <div class="d-item"><div class="d-label">Occasion</div><div class="d-val">${isChild?"👶 Children's Celebration":"📋 Other"}</div></div>
        ${isChild?`<div class="d-item"><div class="d-label">Type</div><div class="d-val">${b.photo_type==="family"?"👨‍👩‍👧 Family":"👶 Child"} Photoshoot</div></div>`:""}
      </div>
      ${isChild?`
      <div class="section-hd">👶 Child</div>
      <div class="d-grid mb4">
        <div class="d-item"><div class="d-label">Name</div><div class="d-val">${b.child_gender?genderIcon(b.child_gender):""} ${esc(b.child_name||"—")}</div></div>
        <div class="d-item"><div class="d-label">Birthday</div><div class="d-val mono">${b.child_birthday?`🎂 ${fmtDate(b.child_birthday)}`:"—"}</div></div>
        <div class="d-item"><div class="d-label">Outfit</div><div class="d-val">${esc(b.preferred_outfit||"—")}</div></div>
      </div>`:``}
      ${b.notes?`
      <div class="section-hd">📝 Notes</div>
      <div style="background:#f9f6f2;border-radius:8px;padding:12px;font-size:14px;color:#555">${esc(b.notes)}</div>`:``}
    </div>
    <div class="modal-foot">
      <button class="btn btn-ghost" onclick="closeModal()">Close</button>
      <button class="btn btn-accent" onclick="openBookingFormById(${b.id});closeModal()">✏ Edit</button>
    </div>
  </div>`;
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

function updateSendBtn() {
  const btn = document.getElementById("chat-send-btn");
  if (!btn) return;
  const val = document.getElementById("chat-input")?.value?.trim();
  if (S_recorder.recording) {
    btn.textContent = "⏹";
    btn.style.background = "#ef4444";
  } else {
    btn.textContent = val ? "➤" : "🎙️";
    btn.style.background = "#25D366";
  }
}
 
function handleSendOrRecord(pk) {
  if (S_recorder.recording) {
    stopVoiceRecording();
    return;
  }
  const val = document.getElementById("chat-input")?.value?.trim();
  if (val) {
    sendChatMessage(pk);
  } else {
    startVoiceRecording(pk);
  }
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
    { id: "analytics", icon: "📊", label: "Analytics" },
  ];

  const pageContent = {
    overview: pageOverview,
    approvals: pageApprovals,
    clients: pageClients,
    bookings: pageBookings,
    analytics: pageAnalytics, 
  }[page]?.() || "";

  const titles = {
    overview: "Overview",
    approvals: "Approval Queue",
    clients: "Clients",
    bookings: "Bookings",
    analytics: "Analytics",
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

//____________________________________________________________________________________STATS

async function fetchAnalytics() {
  set({ analyticsLoading: true });
  try {
    let path = `/analytics/?period=${S.analyticsPeriod}`;
    if (S.analyticsPeriod === "custom" && S.analyticsFrom && S.analyticsTo) {
      path = `/analytics/?from=${S.analyticsFrom}&to=${S.analyticsTo}`;
    }
    set({ analytics: await req("GET", path), analyticsLoading: false });
  } catch (e) {
    set({ analyticsLoading: false });
    toast(e.message, "err");
  }
}

function pageAnalytics() {
  const d = S.analytics;
  const L = S.analyticsLoading;

  function pct(a, b) {
    if (!b) return "0%";
    return Math.round((a / b) * 100) + "%";
  }
  function bar(val, max, color) {
    const w = max ? Math.round((val / max) * 100) : 0;
    return `<div style="background:#eee;border-radius:4px;height:8px;flex:1">
      <div style="background:${color};width:${w}%;height:8px;border-radius:4px;transition:width .4s"></div>
    </div>`;
  }

  return `
<div class="flex aic gap2 mb4" style="flex-wrap:wrap">
  <select class="f-input" style="width:140px;padding:5px 10px"
    onchange="set({analyticsPeriod:this.value});if(this.value!=='custom')fetchAnalytics()">
    <option value="7d"    ${S.analyticsPeriod==="7d"?"selected":""}>Last 7 days</option>
    <option value="30d"   ${S.analyticsPeriod==="30d"?"selected":""}>Last 30 days</option>
    <option value="90d"   ${S.analyticsPeriod==="90d"?"selected":""}>Last 90 days</option>
    <option value="custom"${S.analyticsPeriod==="custom"?"selected":""}>Custom range</option>
  </select>
  ${S.analyticsPeriod === "custom" ? `
    <input class="f-input" type="date" style="width:140px;padding:5px 10px"
      value="${esc(S.analyticsFrom)}" onchange="set({analyticsFrom:this.value})">
    <span class="muted">→</span>
    <input class="f-input" type="date" style="width:140px;padding:5px 10px"
      value="${esc(S.analyticsTo)}" onchange="set({analyticsTo:this.value})">
    <button class="btn btn-accent btn-sm" onclick="fetchAnalytics()">Apply</button>
  ` : ""}
  <button class="refresh" onclick="fetchAnalytics()">↻ Refresh</button>
  ${d ? `<span class="muted" style="font-size:12px">
    ${esc(d.period?.from)} → ${esc(d.period?.to)}
  </span>` : ""}
</div>

${L ? '<div class="loading"><span class="spin"></span>Loading analytics…</div>' :
  !d ? '<div class="empty"><div class="empty-icon">📊</div><h3>Select a period above</h3></div>' : `

<!-- FUNNEL -->
<div class="panel mb4">
  <div class="panel-head"><h2>🔽 Conversion Funnel</h2></div>
  <div style="padding:20px">
    ${[
      ["👥 New Clients",         d.funnel.total_clients,        d.funnel.total_clients, "#6366f1"],
      ["💬 Started Conversation",d.funnel.started_conversation, d.funnel.total_clients, "#8b5cf6"],
      ["✅ Completed Discovery", d.funnel.completed_discovery,  d.funnel.total_clients, "#06b6d4"],
      ["📦 Saw Packages",        d.funnel.saw_packages,         d.funnel.total_clients, "#10b981"],
      ["🎯 Chose a Package",     d.funnel.chose_package,        d.funnel.total_clients, "#f59e0b"],
      ["💳 Confirmed Payment",   d.funnel.confirmed_payment,    d.funnel.total_clients, "#ef4444"],
    ].map(([label, val, total, color]) => `
      <div style="display:flex;align-items:center;gap:12px;margin-bottom:14px">
        <div style="width:200px;font-size:13px">${label}</div>
        <div style="font-weight:700;width:40px;text-align:right;font-size:15px">${val}</div>
        ${bar(val, total, color)}
        <div style="width:45px;font-size:12px;color:#999;text-align:right">${pct(val, total)}</div>
      </div>`).join("")}
  </div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">

<!-- DISCOVERY PREFERENCES -->
<div class="panel">
  <div class="panel-head"><h2>🎛️ Discovery Preferences</h2></div>
  <div style="padding:20px">
    ${[
      ["📍 Session", "studio", "home", d.discovery.session.studio, d.discovery.session.home, "#6366f1", "#8b5cf6"],
      ["🖼️ Frames",  "Yes",    "No",   d.discovery.frames.yes,    d.discovery.frames.no,    "#10b981", "#ef4444"],
      ["🎂 Cake",    "Yes",    "No",   d.discovery.cake.yes,      d.discovery.cake.no,      "#f59e0b", "#ef4444"],
      ["🎬 Video",   "Yes",    "No",   d.discovery.video.yes,     d.discovery.video.no,     "#06b6d4", "#ef4444"],
    ].map(([label, l1, l2, v1, v2, c1, c2]) => {
      const total = v1 + v2;
      const p1 = total ? Math.round(v1/total*100) : 0;
      const p2 = 100 - p1;
      return `
      <div style="margin-bottom:18px">
        <div style="display:flex;justify-content:space-between;margin-bottom:6px">
          <span style="font-size:13px;font-weight:600">${label}</span>
          <span style="font-size:11px;color:#999">${total} responses</span>
        </div>
        <div style="display:flex;border-radius:6px;overflow:hidden;height:24px">
          <div style="background:${c1};width:${p1}%;display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff;font-weight:700;transition:width .4s">
            ${p1>10?`${l1} ${p1}%`:""}
          </div>
          <div style="background:${c2};width:${p2}%;display:flex;align-items:center;justify-content:center;font-size:11px;color:#fff;font-weight:700;transition:width .4s">
            ${p2>10?`${l2} ${p2}%`:""}
          </div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:11px;color:#999">
          <span>${l1}: ${v1}</span><span>${l2}: ${v2}</span>
        </div>
      </div>`;
    }).join("")}
  </div>
</div>

<!-- COMBOS POPULAIRES -->
<div class="panel">
  <div class="panel-head"><h2>🔥 Popular Combos</h2></div>
  <div style="padding:20px">
    ${d.discovery.top_combos.length === 0
      ? '<div class="empty"><p>No data yet</p></div>'
      : d.discovery.top_combos.map((c, i) => {
          const colors = ["#6366f1","#8b5cf6","#06b6d4","#10b981","#f59e0b","#ef4444"];
          const maxVal = d.discovery.top_combos[0]?.count || 1;
          return `
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
            <span style="font-size:16px">${["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣"][i]||"•"}</span>
            <div style="flex:1">
              <div style="font-size:13px;margin-bottom:4px">${esc(c.combo)}</div>
              <div style="background:#eee;border-radius:4px;height:6px">
                <div style="background:${colors[i%colors.length]};width:${Math.round(c.count/maxVal*100)}%;height:6px;border-radius:4px"></div>
              </div>
            </div>
            <span style="font-weight:700;font-size:14px">${c.count}</span>
          </div>`;
        }).join("")
    }
  </div>
</div>
</div>

<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:16px">

<!-- COMPORTEMENT -->
<div class="panel">
  <div class="panel-head"><h2>🧠 Behavior</h2></div>
  <div style="padding:20px">
    ${[
      ["👤 Talk to Agent",    d.behavior.talk_to_agent,   "#f59e0b"],
      ["🔒 Human Takeovers",  d.behavior.human_takeovers, "#ef4444"],
    ].map(([label, val, color]) => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #f0f0f0">
        <span style="font-size:13px">${label}</span>
        <span style="font-weight:700;font-size:18px;color:${color}">${val}</span>
      </div>`).join("")}
    <div style="margin-top:16px">
      <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#999;margin-bottom:10px">Languages</div>
      ${Object.entries(d.behavior.languages).map(([lang, count]) => {
        const flags = {en:"🇬🇧", rw:"🇷🇼", fr:"🇫🇷"};
        const total = Object.values(d.behavior.languages).reduce((a,b)=>a+b,0);
        return `
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
          <span style="font-size:16px">${flags[lang]||"🌐"}</span>
          <span style="font-size:13px;width:30px">${lang.toUpperCase()}</span>
          ${bar(count, total, {en:"#6366f1",rw:"#10b981",fr:"#f59e0b"}[lang]||"#999")}
          <span style="font-size:12px;font-weight:600;width:30px">${count}</span>
        </div>`;
      }).join("")}
    </div>
  </div>
</div>

<!-- PHASE DISTRIBUTION -->
<div class="panel">
  <div class="panel-head"><h2>📍 Where They Stopped</h2></div>
  <div style="padding:20px">
    ${Object.entries(d.behavior.phase_distribution)
      .sort((a,b) => b[1]-a[1])
      .map(([phase, count]) => {
        const total = Object.values(d.behavior.phase_distribution).reduce((a,b)=>a+b,0);
        const icons = {entry:"🚪",booking:"📦",sales_resistance:"⚔️",preparation:"📸",delivery:"📤",feedback:"⭐"};
        return `
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
          <span style="font-size:14px">${icons[phase]||"•"}</span>
          <div style="flex:1">
            <div style="display:flex;justify-content:space-between;margin-bottom:3px">
              <span style="font-size:12px">${phase}</span>
              <span style="font-size:12px;font-weight:600">${count}</span>
            </div>
            ${bar(count, total, "#6366f1")}
          </div>
          <span style="font-size:11px;color:#999;width:35px;text-align:right">${pct(count,total)}</span>
        </div>`;
      }).join("")}
  </div>
</div>

<!-- AI PERFORMANCE -->
<div class="panel">
  <div class="panel-head"><h2>⚡ AI Performance</h2></div>
  <div style="padding:20px">
    ${[
      ["💬 Conversations",      d.ai_performance.total_conversations, "#6366f1", ""],
      ["🔤 Total Tokens",       (d.ai_performance.total_tokens||0).toLocaleString(), "#8b5cf6", ""],
      ["📊 Avg Tokens/Conv",    d.ai_performance.avg_tokens_per_conv, "#06b6d4", ""],
      ["💰 Estimated Cost",     `$${d.ai_performance.estimated_cost_usd}`, "#10b981", "USD"],
    ].map(([label, val, color]) => `
      <div style="display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid #f0f0f0">
        <span style="font-size:13px;color:#555">${label}</span>
        <span style="font-weight:700;font-size:16px;color:${color}">${val}</span>
      </div>`).join("")}
    <div style="margin-top:16px;background:#f9f6f2;border-radius:8px;padding:12px;font-size:12px;color:#999">
      💡 Cost estimate based on GPT-4o-mini pricing (60% input / 40% output)
    </div>
  </div>
</div>
</div>
`}`;
}