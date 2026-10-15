// IA 4 — start strony: bramka, zakładki, magistrala, zegary (instrukcja, sekcja 9).
// Wersja projektu: 1.44 (2026-10-15)
//
// Nowa zakładka: plik js/views/<nazwa>.js eksportujący { id, title, render(el, changed), tick?(el) },
// wpis w VIEWS niżej i link w <nav> w index.html (docs/README.md). Zakładki: #system, #inwestor, #fx, #ai (klawisze 1–4).

import { store, startPolling, gateRemembered, gateTry, gateForget, age, t, $ } from "./core.js";
import { nodes, overall } from "./health.js";
import system from "./views/system.js";
import investor from "./views/investor.js";
import fx from "./views/fx.js";
import ai from "./views/ai.js";
import { initHelp } from "./help.js";

const VIEWS = [system, investor, fx, ai];
let current = null;
const lastTs = {}, pulseUntil = {};

// ------------------------------------------------------------------ bramka
async function gate() {
  if (gateRemembered()) return start();
  const form = $("#gateForm"), pw = $("#gatePw"), msg = $("#gateMsg");
  form.addEventListener("submit", async ev => {
    ev.preventDefault();
    msg.textContent = "sprawdzam…";
    try {
      if (await gateTry(pw.value)) { msg.textContent = ""; start(); return; }
      msg.textContent = "błędne hasło";
    } catch (e) { msg.textContent = e.message; }
    pw.value = "";
    form.classList.remove("shake"); void form.offsetWidth; form.classList.add("shake");
    pw.focus();
  });
}

function start() {
  $("#gate").hidden = true;
  $("#app").hidden = false;
  $("#logout").addEventListener("click", () => { gateForget(); location.reload(); });
  initHelp();
  document.addEventListener("keydown", e => {
    if (e.target.closest("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
    const v = VIEWS[+e.key - 1];
    if (v) location.hash = v.id;
  });
  window.addEventListener("hashchange", route);
  window.addEventListener("resize", () => current && current.render($(`#view-${current.id}`), [], true));
  store.on(changed => {
    bus();
    if (current) current.render($(`#view-${current.id}`), changed);
  });
  route();
  startPolling();
  setInterval(second, 1000);
  second();
}

// ------------------------------------------------------------------ zakładki
function route() {
  const id = (location.hash || "").slice(1).split("/")[0];
  const mobile = matchMedia("(max-width: 760px)").matches;
  const v = VIEWS.find(x => x.id === id) || (mobile ? system : VIEWS.find(x => x.id === localStorage.getItem("ia4.view")) || system);
  current = v;
  try { localStorage.setItem("ia4.view", v.id); } catch (e) { /* bez pamięci */ }
  document.querySelectorAll(".tabs a").forEach(a => a.setAttribute("aria-selected", a.dataset.view === v.id ? "true" : "false"));
  document.querySelectorAll(".view").forEach(s => { s.hidden = s.dataset.view !== v.id; });
  $("#brandView").textContent = v.title;
  $("#app").dataset.view = v.id;
  document.title = `IA4 · ${v.title}`;
  v.render($(`#view-${v.id}`), [], true);
  window.scrollTo(0, 0);
}

// ------------------------------------------------------------------ magistrala
function bus() {
  const el = $("#bus"), N = nodes(), now = Date.now();
  if (el.childElementCount !== N.length) {
    el.innerHTML = N.map(n => `<div class="node" data-id="${n.id}"><div class="node-h"><span class="led"></span><span class="nm"></span></div>` +
      `<div class="node-age"></div><div class="node-sub"></div><div class="node-bar"><i></i></div></div>`).join("");
  }
  N.forEach(n => {
    const d = el.querySelector(`[data-id="${n.id}"]`);
    d.className = `node ${n.status}` + (pulseUntil[n.id] > now ? " pulse" : "");
    d.querySelector(".led").className = `led ${n.status}${n.status === "ok" ? " beat" : ""}`;
    d.querySelector(".nm").textContent = n.name;
    const s = isFinite(n.ts) ? (now - n.ts) / 1000 : null;
    d.querySelector(".node-age").innerHTML = s === null ? "—" : `${age(s)}<small>temu</small>`;
    d.querySelector(".node-sub").textContent = n.sub || n.every;
    d.title = `${n.name}: ${n.sub || ""} · rytm: ${n.every}`;
    // pasek: ile z typowego odstępu minęło (pełny = pora na kolejny znak życia)
    const span = { yahoo: 3600, gas: 3600, fs: 3600, gh: 3600, mac: 120, ai: 300, web: 60 }[n.id];
    d.querySelector(".node-bar i").style.width = s === null ? "0" : Math.min(100, 100 * s / span) + "%";
    if (isFinite(n.ts) && lastTs[n.id] && n.ts > lastTs[n.id]) { pulseUntil[n.id] = now + 1600; d.classList.remove("pulse"); void d.offsetWidth; d.classList.add("pulse"); }
    if (isFinite(n.ts)) lastTs[n.id] = n.ts;
  });
  const o = overall(N);
  const tag = $("#liveTag");
  tag.className = `live-tag ${o.status}`;
  tag.textContent = o.text;
}

function second() {
  const now = Date.now();
  $("#clkPL").textContent = t.hms(now);
  $("#clkNY").textContent = t.nyhm(now);
  bus();
  if (current && current.tick) current.tick($(`#view-${current.id}`));
  const errs = Object.entries(store.meta).filter(([, m]) => !m.ok && m.err && m.err !== "brak pliku");
  $("#netStat").textContent = errs.length ? `błędy źródeł: ${errs.map(([k, m]) => `${k} (${m.err})`).join(", ")}` : "";
}

gate();
