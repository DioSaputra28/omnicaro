/* omnicaro — operations console */
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const STATE = {
  accounts: [],
  counts: {},
  categories: {},
  jobs: [],
  listings: [],
  userAgents: [],
  proxies: [],
  proxyTest: null,
  schedules: [],
  schedQuotaSig: "",
  uploadQuotaSig: "",
  editingSchedule: null,
  settings: null,
  currentJob: "",
  filter: "all",
  search: "",
  uaSearch: "",
  view: "dashboard",
};

let stream = null;

/* ---------- helpers ---------- */

async function api(path, options = {}) {
  let res;
  try {
    res = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
  } catch (err) {
    throw new Error("Server tidak merespons. Pastikan omnicaro masih jalan "
      + "(python run.py), lalu muat ulang halaman.");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
  return data;
}

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v === true) node.setAttribute(k, "");
    else if (v !== false && v != null) node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    if (c == null || c === false) continue;
    node.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return node;
}

function badge(text, kind) {
  return el("span", { class: `badge badge-${kind || "neutral"}` }, text);
}

function initials(text) {
  return (text || "?").replace(/[^a-zA-Z0-9 ]/g, " ")
    .trim().split(/\s+/).slice(0, 2)
    .map((w) => w[0] || "").join("").toUpperCase() || "?";
}

function timeShort(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("id-ID", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

function msg(node, text, kind) {
  if (!node) return;
  node.textContent = text || "";
  node.className = "form-msg" + (kind ? ` is-${kind}` : "");
}

function toast(text, kind) {
  const box = el("div", { class: `toast ${kind || ""}` }, text);
  $("#toasts").append(box);
  setTimeout(() => box.remove(), 4200);
}

function accountBadge(status) {
  if (status === "login") return badge("aktif", "ok");
  if (status === "logout") return badge("logout", "bad");
  if (status === "blocked") return badge("gugur (CF)", "bad");
  return badge("belum dicek", "neutral");
}

function listingBadge(status) {
  if (status === "posted") return badge("posted", "ok");
  if (status === "error") return badge("gagal", "bad");
  return badge("belum", "neutral");
}

function jobBadge(status) {
  if (status === "done") return badge("selesai", "ok");
  if (status === "error") return badge("gagal", "bad");
  if (status === "cancelled") return badge("dibatalkan", "warn");
  if (status === "running") return badge("berjalan", "run");
  return badge(status || "queued", "neutral");
}

/* ---------- views ---------- */

const VIEWS = ["dashboard", "accounts", "catalog", "agents", "proxies",
               "schedules", "settings", "queue"];

function viewFromHash() {
  const name = (location.hash || "").replace(/^#\/?/, "");
  return VIEWS.includes(name) ? name : "";
}

function setView(name, syncHash = true) {
  if (!VIEWS.includes(name)) name = "dashboard";
  STATE.view = name;
  $$(".nav-item").forEach((b) => b.classList.toggle(
    "is-active", b.dataset.view === name));
  $$(".view").forEach((v) => v.classList.toggle(
    "is-active", v.id === `view-${name}`));
  try {
    localStorage.setItem("omnicaro.view", name);
  } catch (err) { /* storage bisa diblokir */ }
  if (syncHash && viewFromHash() !== name) {
    location.hash = name;
  }
  if (name === "settings") loadSettings().catch(() => {});
}

$$(".nav-item").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

window.addEventListener("hashchange", () => {
  setView(viewFromHash() || "dashboard", false);
});

$$("[data-goto]").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.goto));
});

/* ---------- render: dashboard ---------- */

function renderDashboard() {
  const a = STATE.accounts;
  const c = STATE.counts || {};
  const active = a.filter((x) => x.status === "login").length;
  const total = c.listings || 0;
  const posted = c.posted || 0;
  const failed = c.failed || 0;

  $("#m-accounts").textContent = a.length;
  $("#m-active").textContent = `${active} aktif`;
  $("#active-count").textContent = `${active} aktif`;
  $("#m-listings").textContent = total;
  $("#m-pending").textContent = `${c.pending || 0} belum diposting`;
  $("#m-posted").textContent = posted;
  $("#m-rate").textContent = total
    ? `${Math.round((posted / total) * 100)}% dari katalog` : "0% dari katalog";
  $("#m-failed").textContent = failed;

  $("#engine-status").textContent = STATE.currentJob ? "berjalan" : "idle";
  $("#engine-job").textContent = STATE.currentJob || "—";
  const curJob = STATE.jobs.find((j) => j.id === STATE.currentJob);
  $("#engine-badge").textContent = curJob ? "running" : "idle";
  $("#engine-badge").className =
    "badge " + (curJob ? "badge-run" : "badge-neutral");
  $("#engine-queue").textContent = c.pending || 0;
  $("#engine-browser").textContent =
    STATE.browser && STATE.browser.headless ? "headless" : "tampil";

  $("#a-total").textContent = a.length;
  $("#a-login").textContent = a.filter((x) => x.status === "login").length;
  $("#a-logout").textContent = a.filter((x) => x.status === "logout").length;
  $("#a-unknown").textContent = a.filter((x) => x.status === "unknown").length;

  const activeBox = $("#dashboard-accounts");
  activeBox.innerHTML = "";
  const shown = a.filter((x) => x.status === "login").slice(0, 5);
  $("#dashboard-accounts-empty").hidden = shown.length > 0;
  for (const acc of shown) {
    activeBox.append(el("li", {}, [
      el("div", { class: "mini-main" }, [
        el("strong", {}, acc.label),
        el("span", {}, acc.nickname ? `@${acc.nickname}` : "login aktif"),
      ]),
      badge("aktif", "ok"),
    ]));
  }

  const jobsBox = $("#dashboard-jobs");
  jobsBox.innerHTML = "";
  const recent = STATE.jobs.slice(0, 5);
  $("#dashboard-jobs-empty").hidden = recent.length > 0;
  for (const job of recent) {
    jobsBox.append(el("li", {}, [
      el("div", { class: "mini-main" }, [
        el("strong", {}, jobLabel(job.kind)),
        el("span", {}, timeShort(job.started_at || job.created_at)),
      ]),
      jobBadge(job.status),
    ]));
  }

  const dashList = $("#dashboard-listings");
  dashList.innerHTML = "";
  for (const it of STATE.listings.slice(0, 6)) {
    dashList.append(listingRow(it, false));
  }
}

/* ---------- render: accounts ---------- */

function accountNicheSelect(a) {
  const sel = el("select", { class: "select-mini" },
    [el("option", { value: "" }, "—")]);
  for (const [key, info] of Object.entries(STATE.categories || {})) {
    sel.append(el("option", { value: key }, info.label || key));
  }
  sel.value = a.niche || "";
  sel.addEventListener("change", async () => {
    try {
      await api(`/api/accounts/${a.id}`, {
        method: "PATCH",
        body: JSON.stringify({ niche: sel.value }),
      });
      toast(`Kategori ${a.label} disimpan.`, "ok");
      await refresh();
    } catch (err) {
      toast(err.message, "err");
    }
  });
  return sel;
}

function renderAccounts() {
  const body = $("#accounts-body");
  body.innerHTML = "";
  const q = STATE.search.toLowerCase();
  const rows = STATE.accounts.filter((a) => {
    const matchStatus = STATE.filter === "all"
      || (STATE.filter === "login" && a.status === "login")
      || (STATE.filter === "logout" && a.status === "logout")
      || (STATE.filter === "blocked" && a.status === "blocked")
      || (STATE.filter === "unknown" && a.status === "unknown");
    const blob = `${a.label} ${a.nickname || ""} ${a.id}`.toLowerCase();
    return matchStatus && (!q || blob.includes(q));
  });
  $("#accounts-empty").hidden = rows.length > 0;

  for (const a of rows) {
    const stats = a.stats || {};
    body.append(el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-id" }, [
          el("span", { class: "avatar" }, initials(a.label)),
          el("div", { class: "id-main" }, [
            el("strong", {}, a.label),
            el("span", {}, `ID ${a.id}`),
          ]),
        ]),
      ]),
      el("td", {}, [accountNicheSelect(a)]),
      el("td", {}, [accountBadge(a.status)]),
      el("td", {}, a.status === "login" && a.nickname
        ? `@${a.nickname}` : "—"),
      el("td", { class: "num" }, timeShort(a.last_check)),
      el("td", { class: "num" }, stats.open ? `${stats.open}` : "—"),
      el("td", {}, [
        el("div", { class: "row-actions" }, [
          el("button", {
            class: "btn btn-mini", type: "button",
            onclick: () => checkAccount(a.id),
          }, "Cek login"),
          el("button", {
            class: "btn btn-mini btn-danger", type: "button",
            onclick: () => removeAccount(a),
          }, "Hapus"),
        ]),
      ]),
    ]));
  }
}

/* ---------- render: catalog ---------- */

function renderCategories() {
  const wrap = $("#category-list");
  wrap.innerHTML = "";
  const cat = STATE.categories || {};
  const uploadSel = $("#upload-category");
  const prevUpload = uploadSel.value;
  uploadSel.innerHTML = "";
  uploadSel.append(el("option", { value: "" }, "Semua kategori"));
  uploadSel.append(el("option", { value: "__account__" },
    "Ikut kategori akun"));
  for (const [key, info] of Object.entries(cat)) {
    wrap.append(el("label", {}, [
      el("input", { type: "checkbox", value: key }),
      info.label || key,
    ]));
    uploadSel.append(el("option", { value: key }, info.label || key));
  }
  uploadSel.value = prevUpload;
  if (!prevUpload && (STATE.accounts || []).some((a) => a.niche)) {
    uploadSel.value = "__account__";
  }

  const nicheSel = $("#acct-niche");
  const prevNiche = nicheSel.value;
  nicheSel.innerHTML = "";
  nicheSel.append(el("option", { value: "" }, "— belum diatur —"));
  for (const [key, info] of Object.entries(cat)) {
    nicheSel.append(el("option", { value: key }, info.label || key));
  }
  nicheSel.value = prevNiche;
}

function renderStats() {
  const c = STATE.counts || {};
  const wrap = $("#stats");
  wrap.innerHTML = "";
  for (const [label, value] of [
    ["Listing", c.listings ?? 0],
    ["Terposting", c.posted ?? 0],
    ["Gagal", c.failed ?? 0],
    ["Belum posting", c.pending ?? 0],
  ]) {
    wrap.append(el("div", { class: "stat" }, [
      el("span", { class: "stat-value" }, value),
      el("span", { class: "stat-label" }, label),
    ]));
  }
}

function listingRow(it, withCategory = true) {
  const status = it.upload_status === "posted" ? "posted"
    : it.upload_status === "error" ? "error" : "pending";
  const title = el("a", {
    href: it.url || "#", target: "_blank", rel: "noreferrer",
  }, (it.title || "").length > 66
    ? `${it.title.slice(0, 66)}…` : it.title);
  return el("tr", {}, [
    el("td", { class: "title-cell" }, [title]),
    withCategory ? el("td", {}, it.category || "—") : el("td", {}, it.category || "—"),
    el("td", { class: "right num" }, it.price || "—"),
    el("td", {}, it.size || "—"),
    el("td", {}, [listingBadge(status)]),
    el("td", { class: "num" }, timeShort(it.scraped_at)),
  ]);
}

function renderListings() {
  const body = $("#listings-body");
  body.innerHTML = "";
  $("#listings-empty").hidden = STATE.listings.length > 0;
  for (const it of STATE.listings) body.append(listingRow(it));
  $("#listings-count").textContent = `${STATE.listings.length} item`;
}

/* ---------- render: queue ---------- */

function jobLabel(kind) {
  return kind === "scrape" ? "Scrape"
    : kind === "upload" ? "Posting"
    : kind === "check_all" ? "Cek semua akun" : "Cek akun";
}

function renderAccountsSelect() {
  const sel = $("#upload-account");
  const prev = sel.value;
  sel.innerHTML = "";
  if (!STATE.accounts.length) {
    sel.append(el("option", { value: "" }, "Belum ada akun"));
    return;
  }
  sel.append(el("option", { value: "__all__" },
    `Semua akun (${STATE.accounts.length})`));
  for (const a of STATE.accounts) {
    sel.append(el("option", { value: a.id },
      `${a.label}${a.nickname ? ` — @${a.nickname}` : ""}`));
  }
  if (prev) sel.value = prev;
  toggleUploadQuota();
}

function uploadAllMode() {
  return $("#upload-account").value === "__all__";
}

function renderUploadQuotas() {
  const box = $("#upload-quotas");
  const sig = (STATE.accounts || []).map((a) => a.id).join(",");
  if (sig === STATE.uploadQuotaSig) return;
  const prev = {};
  $$("#upload-quotas input[data-account]").forEach((inp) => {
    prev[inp.dataset.account] = inp.value;
  });
  STATE.uploadQuotaSig = sig;
  box.innerHTML = "";
  for (const a of STATE.accounts || []) {
    box.append(el("label", { class: "quota-item" }, [
      el("span", { class: "quota-name" },
        `${a.label}${a.nickname ? ` (@${a.nickname})` : ""}`),
      el("input", {
        type: "number", min: "0", max: "500",
        value: String(prev[a.id] ?? 10), "data-account": a.id,
      }),
      el("span", { class: "micro" }, "posting"),
    ]));
  }
}

function toggleUploadQuota() {
  const all = uploadAllMode();
  $("#upload-limit-field").hidden = all;
  $("#upload-quota-field").hidden = !all;
  if (all) renderUploadQuotas();
}

function renderJobs() {
  const body = $("#jobs-body");
  body.innerHTML = "";
  $("#jobs-empty").hidden = STATE.jobs.length > 0;
  $("#jobs-count").textContent = `${STATE.jobs.length} job`;
  for (const j of STATE.jobs) {
    body.append(el("tr", {}, [
      el("td", { class: "num" }, j.id),
      el("td", {}, jobLabel(j.kind)),
      el("td", {}, [jobBadge(j.status)]),
      el("td", { class: "num" }, timeShort(j.started_at || j.created_at)),
      el("td", {}, [
        el("div", { class: "row-actions" }, [
          j.status === "running"
            ? el("button", {
                class: "btn btn-mini btn-danger", type: "button",
                onclick: () => cancelJob(j.id),
              }, "Batal")
            : null,
          el("button", {
            class: "btn btn-mini", type: "button",
            onclick: () => openJob(j.id),
          }, "Lihat log"),
        ]),
      ]),
    ]));
  }
  const running = STATE.jobs.find((j) => j.status === "running");
  $("#worker-chip").textContent = running
    ? `worker: ${jobLabel(running.kind)} ${running.id}` : "worker idle";
  $("#worker-state").textContent = running ? running.id : "idle";
  $("#node-job").textContent = running ? running.id : "idle";
}

/* ---------- render: user agents ---------- */

function renderUserAgents() {
  const list = STATE.userAgents || [];
  const body = $("#ua-body");
  body.innerHTML = "";

  const enabled = list.filter((u) => u.enabled).length;
  const totalUse = list.reduce((n, u) => n + (u.use_count || 0), 0);
  $("#ua-total").textContent = list.length;
  $("#ua-enabled").textContent = enabled;
  $("#ua-used").textContent = totalUse;
  $("#ua-summary").textContent = `${enabled} aktif`;

  const q = STATE.uaSearch.toLowerCase();
  const rows = q ? list.filter((u) =>
    `${u.label} ${u.ua}`.toLowerCase().includes(q)) : list;
  $("#ua-filter-count").textContent =
    q ? `${rows.length} dari ${list.length} UA` : `${list.length} UA`;
  $("#ua-empty").hidden = rows.length > 0;

  for (const ua of rows) {
    body.append(el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-id" }, [
          el("span", { class: "avatar" }, initials(ua.label)),
          el("div", { class: "id-main" }, [
            el("strong", {}, ua.label),
            el("span", {}, `UA ${ua.id}`),
          ]),
        ]),
      ]),
      el("td", { class: "ua-cell" }, [
        el("code", {}, ua.ua),
      ]),
      el("td", {}, [
        ua.enabled ? badge("aktif", "ok") : badge("nonaktif", "neutral"),
      ]),
      el("td", { class: "right num" }, `${ua.use_count || 0}×`),
      el("td", { class: "num" }, ua.last_used_at ? timeShort(ua.last_used_at) : "—"),
      el("td", {}, [
        el("div", { class: "row-actions" }, [
          el("button", {
            class: "btn btn-mini", type: "button",
            onclick: () => toggleUserAgent(ua),
          }, ua.enabled ? "Nonaktifkan" : "Aktifkan"),
          el("button", {
            class: "btn btn-mini btn-danger", type: "button",
            onclick: () => removeUserAgent(ua),
          }, "Hapus"),
        ]),
      ]),
    ]));
  }
}

async function toggleUserAgent(ua) {
  try {
    await api(`/api/user-agents/${ua.id}?enabled=${ua.enabled ? "false" : "true"}`,
      { method: "PATCH" });
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function removeUserAgent(ua) {
  if (!confirm(`Hapus user agent "${ua.label}"?`)) return;
  try {
    await api(`/api/user-agents/${ua.id}`, { method: "DELETE" });
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  }
}

$("#ua-search").addEventListener("input", (e) => {
  STATE.uaSearch = e.target.value.trim();
  renderUserAgents();
});

$("#ua-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const note = $("#ua-msg");
  const label = $("#ua-label").value.trim();
  const ua = $("#ua-string").value.trim();
  if (!ua) return msg(note, "User agent masih kosong.", "error");
  msg(note, "Menyimpan…");
  try {
    await api("/api/user-agents", {
      method: "POST",
      body: JSON.stringify({ label, ua }),
    });
    msg(note, "User agent ditambahkan.", "ok");
    $("#ua-label").value = "";
    $("#ua-string").value = "";
    await refresh();
  } catch (err) {
    msg(note, err.message, "error");
  }
});

/* ---------- render: proxy ---------- */

function proxyBadge(status) {
  if (status === "ok") return badge("hidup", "ok");
  if (status === "fail") return badge("mati", "bad");
  return badge("belum dicek", "neutral");
}

function renderProxies() {
  const list = STATE.proxies || [];
  const body = $("#proxy-body");
  body.innerHTML = "";
  $("#proxy-empty").hidden = list.length > 0;

  const ok = list.filter((p) => p.status === "ok").length;
  const fail = list.filter((p) => p.status === "fail").length;
  const totalUse = list.reduce((n, p) => n + (p.use_count || 0), 0);
  $("#proxy-total").textContent = list.length;
  $("#proxy-ok").textContent = ok;
  $("#proxy-fail").textContent = fail;
  $("#proxy-used").textContent = totalUse;
  $("#proxy-summary").textContent = `${ok} hidup / ${list.length} proxy`;

  for (const p of list) {
    body.append(el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-id" }, [
          el("span", { class: "avatar" }, initials(p.label)),
          el("div", { class: "id-main" }, [
            el("strong", {}, p.label),
            el("span", {}, `Proxy ${p.id}`),
          ]),
        ]),
      ]),
      el("td", { class: "ua-cell" }, [
        el("code", {}, p.server),
        p.has_auth ? el("span", { class: "auth-dot" }, "auth") : null,
      ]),
      el("td", {}, [
        proxyBadge(p.status),
        p.status === "fail" && p.last_error
          ? el("span", { class: "err-note" }, p.last_error)
          : null,
      ]),
      el("td", { class: "right num" }, `${p.use_count || 0}×`),
      el("td", { class: "right num" },
        p.status === "ok" ? `${p.latency_ms} ms` : "—"),
      el("td", { class: "num" }, p.exit_ip || "—"),
      el("td", { class: "num" }, timeShort(p.checked_at)),
      el("td", {}, [
        el("div", { class: "row-actions" }, [
          el("button", {
            class: "btn btn-mini", type: "button",
            onclick: () => checkProxy(p),
          }, "Cek"),
          el("button", {
            class: "btn btn-mini btn-danger", type: "button",
            onclick: () => removeProxy(p),
          }, "Hapus"),
        ]),
      ]),
    ]));
  }
}

async function checkProxy(p) {
  toast(`Mengecek ${p.label}…`);
  try {
    const res = await api(`/api/proxies/${p.id}/check`, { method: "POST" });
    toast(res.ok
      ? `${p.label}: hidup (${res.latency_ms} ms, IP ${res.exit_ip})`
      : `${p.label}: mati — ${res.error}`, res.ok ? "ok" : "err");
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function removeProxy(p) {
  if (!confirm(`Hapus proxy "${p.label}"?`)) return;
  try {
    await api(`/api/proxies/${p.id}`, { method: "DELETE" });
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  }
}

function renderProxyTest(res) {
  const box = $("#proxy-test-result");
  box.innerHTML = "";
  box.hidden = false;
  box.append(el("div", { class: "test-head" }, [
    el("strong", {}, `${res.ok} hidup`),
    el("span", {}, ` · ${res.fail} mati`),
    el("span", { class: "micro" }, "yang mati tidak ikut ditambahkan"),
  ]));
  for (const r of res.results) {
    box.append(el("div", { class: "test-row" }, [
      el("span", { class: `test-mark ${r.ok ? "ok" : "bad"}` },
        r.ok ? "✓" : "✗"),
      el("code", {}, r.raw),
      el("span", { class: "test-detail" },
        r.ok ? `${r.latency_ms} ms · IP ${r.exit_ip}` : r.error),
    ]));
  }
}

$("#proxy-test").addEventListener("click", async (e) => {
  const note = $("#proxy-msg");
  const raw = $("#proxy-raw").value.trim();
  if (!raw) return msg(note, "Isi minimal satu proxy.", "error");
  e.target.disabled = true;
  msg(note, "Mengecek proxy…");
  try {
    const res = await api("/api/proxies/test", {
      method: "POST",
      body: JSON.stringify({ raw }),
    });
    renderProxyTest(res);
    STATE.proxyTest = {};
    for (const r of res.results) STATE.proxyTest[r.raw] = r.ok;
    msg(note, `${res.ok} hidup, ${res.fail} mati.`,
      res.fail ? "error" : "ok");
  } catch (err) {
    msg(note, err.message, "error");
  } finally {
    e.target.disabled = false;
  }
});

$("#proxy-raw").addEventListener("input", () => {
  STATE.proxyTest = null;
  $("#proxy-test-result").hidden = true;
});

$("#proxy-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const note = $("#proxy-msg");
  const raw = $("#proxy-raw").value.trim();
  const label = $("#proxy-label").value.trim();
  if (!raw) return msg(note, "Isi minimal satu proxy.", "error");

  const lines = raw.split(/\n+/).map((s) => s.trim()).filter(Boolean);
  const tested = STATE.proxyTest;
  const usable = tested ? lines.filter((l) => tested[l]) : lines;
  const skipped = lines.length - usable.length;
  if (tested && !usable.length) {
    return msg(note, "Semua proxy mati, tidak ada yang ditambahkan.", "error");
  }

  msg(note, "Menyimpan…");
  try {
    const res = await api("/api/proxies", {
      method: "POST",
      body: JSON.stringify({ raw: usable.join("\n"), label }),
    });
    const parts = [`${res.added} proxy ditambahkan`];
    if (skipped) parts.push(`${skipped} mati dilewati`);
    if (res.errors && res.errors.length) parts.push(`${res.errors.length} gagal`);
    msg(note, parts.join(", ") + ".", "ok");
    $("#proxy-raw").value = "";
    $("#proxy-label").value = "";
    STATE.proxyTest = null;
    $("#proxy-test-result").hidden = true;
    await refresh();
  } catch (err) {
    msg(note, err.message, "error");
  }
});

$("#proxy-check-all").addEventListener("click", async (e) => {
  const list = STATE.proxies || [];
  if (!list.length) return toast("Belum ada proxy.", "err");
  e.target.disabled = true;
  toast(`Mengecek ${list.length} proxy…`);
  try {
    const res = await api("/api/proxies/check", {
      method: "POST",
      body: JSON.stringify({ ids: [], }),
    });
    toast(`Selesai: ${res.ok} hidup, ${res.fail} mati.`,
      res.fail ? "err" : "ok");
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  } finally {
    e.target.disabled = false;
  }
});

/* ---------- jadwal ---------- */

const DAY_NAMES = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"];

function accountLabel(id) {
  const acc = (STATE.accounts || []).find((a) => a.id === id);
  return acc ? acc.label : "(akun terhapus)";
}

function renderScheduleDays() {
  const box = $("#sched-days");
  if (box.dataset.ready) return;
  box.dataset.ready = "1";
  DAY_NAMES.forEach((name, idx) => {
    box.append(el("label", { class: "day-pill" }, [
      el("input", { type: "checkbox", value: String(idx) }),
      el("span", {}, name),
    ]));
  });
}

function renderScheduleCategories() {
  const sel = $("#sched-category");
  const prev = sel.value;
  sel.innerHTML = "";
  sel.append(el("option", { value: "" }, "Semua kategori"));
  sel.append(el("option", { value: "__account__" }, "Ikut kategori akun"));
  for (const name of Object.keys(STATE.categories || {})) {
    sel.append(el("option", { value: name }, name));
  }
  sel.value = prev;
}

function currentQuotaValues() {
  const out = [];
  $$("#sched-quotas input[data-account]").forEach((inp) => {
    out.push({ account_id: inp.dataset.account, limit: Number(inp.value) || 0 });
  });
  return out;
}

function renderScheduleQuotas(quotas = []) {
  const box = $("#sched-quotas");
  box.innerHTML = "";
  const accounts = STATE.accounts || [];
  if (!accounts.length) {
    box.append(el("p", { class: "empty-note" }, "Belum ada akun."));
    return;
  }
  const map = {};
  for (const q of quotas) map[q.account_id] = q.limit;
  for (const a of accounts) {
    box.append(el("label", { class: "quota-item" }, [
      el("span", { class: "quota-name" },
        `${a.label}${a.nickname ? ` (@${a.nickname})` : ""}`),
      el("input", {
        type: "number", min: "0", max: "500",
        value: String(map[a.id] ?? 0), "data-account": a.id,
      }),
      el("span", { class: "micro" }, "posting"),
    ]));
  }
}

function daysLabel(days) {
  if (!days || !days.length) return "Tiap hari";
  return days.map((d) => DAY_NAMES[d] || "?").join(", ");
}

function nextRunLabel(s) {
  if (!s.enabled) return "nonaktif";
  if (!s.times || !s.times.length) return "—";
  const now = new Date();
  for (let d = 0; d < 8; d += 1) {
    const day = new Date(now);
    day.setDate(now.getDate() + d);
    const weekday = (day.getDay() + 6) % 7;
    if (s.days && s.days.length && !s.days.includes(weekday)) continue;
    for (const t of [...s.times].sort()) {
      const [h, m] = t.split(":").map(Number);
      const dt = new Date(day);
      dt.setHours(h, m, 0, 0);
      if (dt > now) {
        return dt.toLocaleString("id-ID", {
          weekday: "short", hour: "2-digit", minute: "2-digit",
        });
      }
    }
  }
  return "—";
}

function renderSchedules() {
  renderScheduleDays();
  renderScheduleCategories();

  const list = STATE.schedules || [];
  const active = list.filter((s) => s.enabled).length;
  $("#sched-summary").textContent = `${active} aktif / ${list.length} jadwal`;

  const sig = (STATE.accounts || []).map((a) => a.id).join(",");
  if (sig !== STATE.schedQuotaSig) {
    STATE.schedQuotaSig = sig;
    renderScheduleQuotas(currentQuotaValues());
  }

  const body = $("#sched-body");
  body.innerHTML = "";
  $("#sched-empty").hidden = list.length > 0;

  for (const s of list) {
    const quotaChips = (s.quotas || []).map((q) => el("span", { class: "chip" },
      `${accountLabel(q.account_id)} ×${q.limit}`));
    body.append(el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-id" }, [
          el("span", { class: "avatar" }, initials(s.name)),
          el("div", { class: "id-main" }, [
            el("strong", {}, s.name),
            el("span", {}, s.category === "__account__"
              ? "ikut kategori akun"
              : (s.category || "semua kategori")),
          ]),
        ]),
      ]),
      el("td", {}, [
        el("div", { class: "chip-row" },
          (s.times || []).map((t) => el("span", { class: "chip" }, t))),
      ]),
      el("td", { class: "num" }, daysLabel(s.days)),
      el("td", {}, el("div", { class: "chip-row" }, quotaChips)),
      el("td", {}, [
        s.enabled ? badge("aktif", "ok") : badge("nonaktif", "neutral"),
      ]),
      el("td", {}, [
        el("div", {}, nextRunLabel(s)),
        s.last_run_at
          ? el("span", { class: "micro" }, `terakhir ${timeShort(s.last_run_at)}`)
          : null,
      ]),
      el("td", {}, [
        el("div", { class: "row-actions" }, [
          el("button", {
            class: "btn btn-mini", type: "button",
            onclick: () => runScheduleNow(s),
          }, "Jalankan"),
          el("button", {
            class: "btn btn-mini", type: "button",
            onclick: () => editSchedule(s),
          }, "Edit"),
          el("button", {
            class: "btn btn-mini", type: "button",
            onclick: () => toggleSchedule(s),
          }, s.enabled ? "Nonaktifkan" : "Aktifkan"),
          el("button", {
            class: "btn btn-mini btn-danger", type: "button",
            onclick: () => removeSchedule(s),
          }, "Hapus"),
        ]),
      ]),
    ]));
  }
}

function resetScheduleForm() {
  STATE.editingSchedule = null;
  $("#sched-id").value = "";
  $("#sched-name").value = "";
  $("#sched-times").value = "";
  $("#sched-category").value = "";
  $("#sched-fast").checked = false;
  $("#sched-rotate").value = "account";
  $("#sched-proxy").value = "off";
  $$("#sched-days input").forEach((i) => { i.checked = false; });
  renderScheduleQuotas([]);
  $("#sched-form-title").textContent = "Jadwal baru";
  $("#sched-cancel").hidden = true;
  $("#sched-msg").textContent = "";
}

function editSchedule(s) {
  STATE.editingSchedule = s;
  $("#sched-id").value = s.id;
  $("#sched-name").value = s.name;
  $("#sched-times").value = (s.times || []).join(", ");
  $("#sched-category").value = s.category || "";
  $("#sched-fast").checked = !!s.fast;
  $("#sched-rotate").value = s.rotate || "account";
  $("#sched-proxy").value = s.proxy || "off";
  $$("#sched-days input").forEach((i) => {
    i.checked = (s.days || []).includes(Number(i.value));
  });
  renderScheduleQuotas(s.quotas || []);
  $("#sched-form-title").textContent = `Edit: ${s.name}`;
  $("#sched-cancel").hidden = false;
  $("#view-schedules").scrollIntoView({ behavior: "smooth" });
}

async function toggleSchedule(s) {
  try {
    await api(`/api/schedules/${s.id}?enabled=${s.enabled ? "false" : "true"}`,
      { method: "PATCH" });
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function removeSchedule(s) {
  if (!confirm(`Hapus jadwal "${s.name}"?`)) return;
  try {
    await api(`/api/schedules/${s.id}`, { method: "DELETE" });
    if (STATE.editingSchedule && STATE.editingSchedule.id === s.id) {
      resetScheduleForm();
    }
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  }
}

async function runScheduleNow(s) {
  try {
    const res = await api(`/api/schedules/${s.id}/run`, { method: "POST" });
    toast(`Job ${res.id} dijalankan untuk ${s.name}.`, "ok");
    openJob(res.id);
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  }
}

$("#sched-cancel").addEventListener("click", resetScheduleForm);

$("#sched-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const note = $("#sched-msg");
  const times = $("#sched-times").value.split(",")
    .map((s) => s.trim()).filter(Boolean);
  const days = $$("#sched-days input:checked").map((i) => Number(i.value));
  const quotas = currentQuotaValues().filter((q) => q.limit > 0);
  if (!times.length) return msg(note, "Isi minimal satu jam.", "error");
  if (!quotas.length) {
    return msg(note, "Isi kuota minimal satu akun.", "error");
  }
  const payload = {
    name: $("#sched-name").value.trim(),
    times,
    days,
    category: $("#sched-category").value,
    fast: $("#sched-fast").checked,
    rotate: $("#sched-rotate").value,
    proxy: $("#sched-proxy").value,
    enabled: STATE.editingSchedule ? STATE.editingSchedule.enabled : true,
    quotas,
  };
  const editing = $("#sched-id").value;
  msg(note, "Menyimpan…");
  try {
    await api(editing ? `/api/schedules/${editing}` : "/api/schedules", {
      method: editing ? "PUT" : "POST",
      body: JSON.stringify(payload),
    });
    msg(note, "Jadwal disimpan.", "ok");
    resetScheduleForm();
    await refresh();
  } catch (err) {
    msg(note, err.message, "error");
  }
});

/* ---------- pengaturan template ---------- */

function renderSettingsMapping(rows) {
  const body = $("#settings-mapping");
  body.innerHTML = "";
  for (const row of rows) {
    body.append(el("tr", {}, [
      el("td", {}, [
        el("div", { class: "cell-id" }, [
          el("span", { class: "avatar" }, initials(row.label)),
          el("div", { class: "id-main" }, [
            el("strong", {}, row.label),
            el("span", {}, row.category),
          ]),
        ]),
      ]),
      el("td", {}, row.search || "—"),
      el("td", {}, row.leaf || "—"),
    ]));
  }
}

function fillSettings(data) {
  STATE.settings = data;
  const up = data.upload || {};
  $("#set-desc").value = up.description || "";
  $("#set-delivery").value = up.delivery || "";
  $("#set-price-min").value = up.price_min ?? 40000;
  $("#set-price-max").value = up.price_max ?? 60000;
  $("#set-price-step").value = up.price_step ?? 1000;
  const cond = $("#set-condition");
  cond.value = up.condition || "Digunakan dengan baik";
  if (!cond.value) cond.value = "Digunakan dengan baik";
  const preview = data.preview || {};
  $("#preview-desc").textContent = preview.description || "";
  $("#preview-delivery").textContent = preview.delivery || "";
  renderSettingsMapping(data.mapping || []);
}

async function loadSettings() {
  fillSettings(await api("/api/settings"));
}

function settingsFormValues() {
  return {
    description: $("#set-desc").value,
    delivery: $("#set-delivery").value,
    price_min: Number($("#set-price-min").value) || 0,
    price_max: Number($("#set-price-max").value) || 0,
    price_step: Number($("#set-price-step").value) || 1000,
    condition: $("#set-condition").value,
  };
}

let previewTimer = null;
function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    try {
      const res = await api("/api/settings/preview", {
        method: "POST",
        body: JSON.stringify(settingsFormValues()),
      });
      $("#preview-desc").textContent = res.preview.description || "";
      $("#preview-delivery").textContent = res.preview.delivery || "";
    } catch (err) { /* pratinjau gagal, abaikan */ }
  }, 400);
}

$("#set-desc").addEventListener("input", schedulePreview);
$("#set-delivery").addEventListener("input", schedulePreview);

$("#settings-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const note = $("#settings-msg");
  msg(note, "Menyimpan…");
  try {
    const data = await api("/api/settings/upload", {
      method: "PUT",
      body: JSON.stringify(settingsFormValues()),
    });
    fillSettings(data);
    msg(note, "Pengaturan disimpan.", "ok");
    toast("Template listing diperbarui.", "ok");
  } catch (err) {
    msg(note, err.message, "error");
  }
});

$("#set-default").addEventListener("click", () => {
  const defaults = STATE.settings && STATE.settings.defaults;
  if (!defaults) return;
  $("#set-desc").value = defaults.description || "";
  $("#set-delivery").value = defaults.delivery || "";
  schedulePreview();
  toast("Default CLI dimuat — klik Simpan untuk menerapkan.", "ok");
});

/* ---------- refresh ---------- */

async function refresh() {
  STATE.accounts = [];
  const data = await api("/api/state");
  STATE.accounts = data.accounts || [];
  STATE.counts = data.counts || {};
  STATE.categories = data.categories || {};
  STATE.jobs = data.jobs || [];
  STATE.userAgents = data.user_agents || [];
  STATE.proxies = data.proxies || [];
  STATE.schedules = data.schedules || [];
  STATE.currentJob = data.current_job || "";
  STATE.browser = data.browser || {};

  const list = await api("/api/listings?limit=200");
  STATE.listings = list.items || [];

  $("#browser-mode").textContent = STATE.browser.headless
    ? "chromium · headless" : "chromium · tampil";

  renderDashboard();
  renderAccounts();
  renderCategories();
  renderAccountsSelect();
  renderStats();
  renderJobs();
  renderUserAgents();
  renderProxies();
  renderSchedules();
  renderListings();
}

/* ---------- actions ---------- */

$("#btn-refresh").addEventListener("click", () => refresh().catch((e) => toast(e.message, "err")));

$("#open-import").addEventListener("click", openImport);
$("#close-import").addEventListener("click", closeImport);
$("#cancel-import").addEventListener("click", closeImport);
$("#cookie-modal").addEventListener("click", (e) => {
  if (e.target.id === "cookie-modal") closeImport();
});

function openImport() {
  $("#cookie-modal").hidden = false;
  $("#acct-label").focus();
}
function closeImport() {
  $("#cookie-modal").hidden = true;
  msg($("#account-msg"), "");
}

$("#pick-cookie-file").addEventListener("click", () => $("#cookie-file").click());

$("#cookie-file").addEventListener("change", async (e) => {
  const file = e.target.files && e.target.files[0];
  e.target.value = "";
  if (!file) return;
  try {
    const text = await file.text();
    $("#acct-cookies").value = text.trim();
    toast(`${file.name} dimuat (${text.length.toLocaleString("id-ID")} karakter).`, "ok");
  } catch (err) {
    toast(`Gagal membaca file: ${err.message}`, "err");
  }
});

$("#test-cookie").addEventListener("click", async () => {
  const text = $("#acct-cookies").value.trim();
  const note = $("#account-msg");
  const btn = $("#test-cookie");
  if (!text) return msg(note, "Cookie masih kosong.", "error");
  btn.disabled = true;
  msg(note, "Membuka Carousell dengan cookie ini…");
  try {
    const res = await api("/api/accounts/test", {
      method: "POST",
      body: JSON.stringify({ cookies_text: text }),
    });
    const extra = `${res.cookie_count} cookie`
      + (res.has_session ? " · ada cookie sesi" : " · tidak ada cookie sesi");
    msg(note, `${res.message} (${extra})`, res.login ? "ok" : "error");
    toast(res.message, res.login ? "ok" : "err");
  } catch (err) {
    msg(note, err.message, "error");
  } finally {
    btn.disabled = false;
  }
});

$("#submit-account").addEventListener("click", async () => {
  const label = $("#acct-label").value.trim();
  const cookiesText = $("#acct-cookies").value.trim();
  const note = $("#account-msg");
  if (!cookiesText) return msg(note, "Cookie masih kosong.", "error");
  msg(note, "Menyimpan dan memvalidasi cookie…");
  try {
    const res = await api("/api/accounts", {
      method: "POST",
      body: JSON.stringify({
        label, cookies_text: cookiesText, niche: $("#acct-niche").value,
      }),
    });
    msg(note, res.message, res.login ? "ok" : "error");
    toast(res.message, res.login ? "ok" : "err");
    if (res.login) {
      $("#acct-cookies").value = "";
      $("#acct-label").value = "";
      $("#acct-niche").value = "";
      closeImport();
      await refresh();
    }
  } catch (err) {
    msg(note, err.message, "error");
  }
});

$("#account-search").addEventListener("input", (e) => {
  STATE.search = e.target.value.trim();
  renderAccounts();
});

$("#account-filter").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-filter]");
  if (!btn) return;
  STATE.filter = btn.dataset.filter;
  $$("#account-filter button").forEach((b) => b.classList.toggle(
    "is-active", b === btn));
  renderAccounts();
});

async function checkAccount(id) {
  try {
    const { id: jobId } = await api(`/api/jobs/check/${id}`, { method: "POST" });
    openJob(jobId);
    setView("queue");
  } catch (err) {
    toast(err.message, "err");
  }
}

async function removeAccount(acc) {
  if (!confirm(`Hapus akun "${acc.label}"? Cookie ikut terhapus.`)) return;
  try {
    await api(`/api/accounts/${acc.id}`, { method: "DELETE" });
    toast("Akun dihapus.", "ok");
    await refresh();
  } catch (err) {
    toast(err.message, "err");
  }
}

$("#check-all").addEventListener("click", async () => {
  try {
    const { id } = await api("/api/jobs/check-all", { method: "POST" });
    openJob(id);
    setView("queue");
  } catch (err) {
    toast(err.message, "err");
  }
});

$("#scrape-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const note = $("#scrape-msg");
  const cats = $$("#category-list input:checked").map((i) => i.value);
  const limit = Number($("#scrape-limit").value) || 20;
  if (!cats.length) return msg(note, "Pilih minimal satu kategori.", "error");
  msg(note, "Job scrape dikirim…");
  try {
    const { id } = await api("/api/jobs/scrape", {
      method: "POST",
      body: JSON.stringify({ categories: cats, limit }),
    });
    msg(note, `Job ${id} berjalan.`, "ok");
    openJob(id);
    setView("queue");
  } catch (err) {
    msg(note, err.message, "error");
  }
});

$("#upload-account").addEventListener("change", () => {
  toggleUploadQuota();
  if (!uploadAllMode()) {
    const label = document.querySelector('label[for="upload-limit"]');
    if (label) label.textContent = "Jumlah posting";
  }
});

$("#upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const note = $("#upload-msg");
  const account_id = $("#upload-account").value;
  const category = $("#upload-category").value;
  const limit = Number($("#upload-limit").value) || 10;
  const fast = $("#upload-fast").checked;
  const rotate = $("#upload-rotate").value;
  const proxy = $("#upload-proxy").value;
  const all = account_id === "__all__";
  let quotas = {};
  if (all) {
    $$("#upload-quotas input[data-account]").forEach((inp) => {
      const value = Number(inp.value) || 0;
      if (value > 0) quotas[inp.dataset.account] = value;
    });
    if (!Object.keys(quotas).length) {
      return msg(note, "Isi kuota minimal satu akun.", "error");
    }
  }
  if (!account_id) return msg(note, "Pilih akun dulu.", "error");
  msg(note, all ? "Job semua akun dikirim…" : "Job posting dikirim…");
  try {
    const { id } = await api("/api/jobs/upload", {
      method: "POST",
      body: JSON.stringify({
        account_id, category, limit, fast, rotate, proxy,
        quotas: all ? quotas : {},
      }),
    });
    msg(note, `Job ${id} berjalan.`, "ok");
    openJob(id);
  } catch (err) {
    msg(note, err.message, "error");
  }
});

/* ---------- log stream + dock ---------- */

const dock = $("#log-dock");
const dockLog = $("#dock-log");
const dockDot = $("#dock-dot");
const dockJob = $("#dock-job");
let streamJob = "";
let dockHeight = Number(localStorage.getItem("omnicaro.dockH")) || 240;
let dockDrag = null;

function applyDockHeight(value) {
  const max = Math.round(window.innerHeight * 0.7);
  dockHeight = Math.max(120, Math.min(max, Math.round(value)));
  dock.style.setProperty("--dock-h", `${dockHeight}px`);
  try { localStorage.setItem("omnicaro.dockH", String(dockHeight)); } catch (e) {}
}

function setDockOpen(open, remember = true) {
  dock.classList.toggle("is-closed", !open);
  document.body.classList.toggle("dock-open", open);
  $("#dock-toggle").textContent = open ? "Kecilkan" : "Buka";
  if (remember) {
    try { localStorage.setItem("omnicaro.dockOpen", open ? "1" : "0"); } catch (e) {}
  }
  if (open) dockLog.scrollTop = dockLog.scrollHeight;
}

function appendLog(text) {
  if (!text) return;
  dockLog.textContent += text;
  dockLog.scrollTop = dockLog.scrollHeight;
  const qlog = $("#log");
  if (qlog) {
    qlog.textContent += text;
    qlog.scrollTop = qlog.scrollHeight;
  }
}

function openJob(jobId) {
  if (stream) stream.close();
  setDockOpen(true);
  streamJob = jobId;
  dockLog.textContent = "";
  const qlog = $("#log");
  if (qlog) qlog.textContent = "";
  dockJob.textContent = `job ${jobId}`;
  const qtitle = $("#log-title");
  if (qtitle) qtitle.textContent = `job ${jobId}`;
  dockDot.className = "dock-dot is-run";
  const cancelBtn = $("#dock-cancel");
  cancelBtn.hidden = false;
  cancelBtn.disabled = false;
  cancelBtn.textContent = "Batal";

  stream = new EventSource(`/api/jobs/${jobId}/stream`);
  stream.onmessage = (ev) => {
    const data = JSON.parse(ev.data);
    if (data.text) appendLog(data.text);
    if (data.status) {
      const status = String(data.status);
      dockJob.textContent = `job ${jobId} · ${status}`;
      dockDot.className = "dock-dot "
        + (status === "done" ? "is-ok" : status === "error" ? "is-bad"
          : status === "cancelled" ? "is-warn" : "");
      cancelBtn.hidden = true;
      streamJob = "";
      if (stream) stream.close();
      stream = null;
      refresh().catch(() => {});
    }
  };
  stream.onerror = () => {
    if (stream) stream.close();
    stream = null;
  };
}

async function cancelJob(jobId) {
  try {
    await api(`/api/jobs/${jobId}/cancel`, { method: "POST" });
    toast("Permintaan batal dikirim. Job berhenti setelah item berjalan.", "ok");
    return true;
  } catch (err) {
    toast(err.message, "err");
    return false;
  }
}

$("#dock-cancel").addEventListener("click", async () => {
  if (!streamJob) return;
  const btn = $("#dock-cancel");
  const jobId = streamJob;
  btn.disabled = true;
  btn.textContent = "Membatalkan…";
  const ok = await cancelJob(jobId);
  if (!ok) {
    btn.disabled = false;
    btn.textContent = "Batal";
  }
});

$("#log-follow").addEventListener("click", () => {
  const log = $("#log");
  log.scrollTop = log.scrollHeight;
});

$("#dock-follow").addEventListener("click", () => {
  dockLog.scrollTop = dockLog.scrollHeight;
});

$("#dock-clear").addEventListener("click", () => {
  dockLog.textContent = "";
  const qlog = $("#log");
  if (qlog) qlog.textContent = "";
});

$("#dock-toggle").addEventListener("click", () => {
  setDockOpen(dock.classList.contains("is-closed"));
});

$("#dock-head").addEventListener("dblclick", () => {
  setDockOpen(dock.classList.contains("is-closed"));
});

$("#dock-progress").addEventListener("click", () => setView("queue"));

$("#dock-resizer").addEventListener("pointerdown", (e) => {
  dockDrag = { y: e.clientY, h: dockHeight };
  e.target.setPointerCapture(e.pointerId);
  e.preventDefault();
});
window.addEventListener("pointermove", (e) => {
  if (!dockDrag) return;
  applyDockHeight(dockDrag.h + (dockDrag.y - e.clientY));
});
window.addEventListener("pointerup", () => { dockDrag = null; });

applyDockHeight(dockHeight);
let dockWasOpen = false;
try { dockWasOpen = localStorage.getItem("omnicaro.dockOpen") === "1"; } catch (e) {}
if (dockWasOpen) setDockOpen(true, false);

/* ---------- clock & boot ---------- */

function tick() {
  $("#clock").textContent = new Date().toLocaleTimeString("id-ID", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

tick();
setInterval(tick, 1000);

let bootView = viewFromHash();
if (!bootView) {
  try {
    bootView = localStorage.getItem("omnicaro.view") || "";
  } catch (err) { bootView = ""; }
}
setView(bootView || "dashboard");

refresh().then(() => {
  if (STATE.currentJob && !stream) openJob(STATE.currentJob);
}).catch((err) => {
  console.error(err);
  $("#browser-mode").textContent = "state gagal dimuat";
});
setInterval(() => { if (!stream) refresh().catch(() => {}); }, 15000);
