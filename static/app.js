"use strict";

// ---- Elements -------------------------------------------------------------
const form = document.getElementById("search-form");
const input = document.getElementById("search-input");
const strictToggle = document.getElementById("strict-toggle");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const cardTemplate = document.getElementById("card-template");

const modal = document.getElementById("preview");
const modalFrame = document.getElementById("preview-frame");
const modalTitle = document.getElementById("preview-title");
const modalOpen = document.getElementById("preview-open");
const modalCopy = document.getElementById("preview-copy");
const modalClose = document.getElementById("preview-close");

let currentUrl = "";
let lastFocused = null;

// ---- Helpers --------------------------------------------------------------
function videoId(url) {
  try {
    const u = new URL(url);
    if (u.searchParams.get("v")) return u.searchParams.get("v");
    if (u.hostname.includes("youtu.be")) return u.pathname.slice(1);
  } catch (_) {}
  return "";
}

function fmtDuration(sec) {
  if (!sec || sec <= 0) return "";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

async function copyUrl(text, btn, labelEl) {
  try {
    await navigator.clipboard.writeText(text);
  } catch (_) {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
  }
  const target = labelEl || btn;
  const original = target.textContent;
  target.textContent = "COPIED!";
  btn.classList.add("copied");
  setTimeout(() => {
    target.textContent = original;
    btn.classList.remove("copied");
  }, 1500);
}

// ---- Rendering ------------------------------------------------------------
function buildCard(item, feature) {
  const node = cardTemplate.content.firstElementChild.cloneNode(true);
  if (feature) node.classList.add("feature");

  const img = node.querySelector(".thumb-img");
  img.src = item.thumbnail || "";
  img.alt = item.title;

  node.querySelector(".score-badge").textContent = String(item.score);

  const dur = node.querySelector(".dur-badge");
  dur.textContent = fmtDuration(item.duration);

  node.querySelector(".card-title").textContent = item.title;
  node.querySelector(".card-channel").textContent = item.channel || "";

  const res = node.querySelector(".res-badge");
  res.textContent = item.resolution || "";

  node.querySelector(".thumb").addEventListener("click", () => openPreview(item));

  const copyBtn = node.querySelector(".copy-btn");
  const copyLabel = node.querySelector(".copy-label");
  copyBtn.addEventListener("click", () => copyUrl(item.url, copyBtn, copyLabel));

  return node;
}

function render(items) {
  resultsEl.innerHTML = "";
  resultsEl.setAttribute("aria-busy", "false");

  if (!items.length) {
    resultsEl.innerHTML =
      '<div class="notice">NO WALLPAPERS FOUND. TRY ANOTHER VIBE.' +
      '<span class="sub">try: synthwave city · lofi rain · 4k forest loop</span></div>';
    return;
  }

  const frag = document.createDocumentFragment();
  items.forEach((item, i) => frag.appendChild(buildCard(item, i === 0)));
  resultsEl.appendChild(frag);
}

function showSkeletons(n = 6) {
  resultsEl.setAttribute("aria-busy", "true");
  resultsEl.innerHTML = "";
  for (let i = 0; i < n; i++) {
    const sk = document.createElement("div");
    sk.className = "skeleton sk-pulse" + (i === 0 ? " feature" : "");
    sk.innerHTML =
      '<div class="sk-thumb"></div><div class="sk-line"></div><div class="sk-line short"></div>';
    resultsEl.appendChild(sk);
  }
}

function showError(msg) {
  resultsEl.setAttribute("aria-busy", "false");
  resultsEl.innerHTML =
    '<div class="notice error">SEARCH FAILED.<span class="sub">' +
    String(msg).replace(/[<>&]/g, "") +
    "</span></div>";
}

// ---- Preview modal --------------------------------------------------------
function openPreview(item) {
  lastFocused = document.activeElement;
  const id = videoId(item.url);
  currentUrl = item.url;
  modalTitle.textContent = item.title;
  modalOpen.href = item.url;
  modalFrame.innerHTML = id
    ? `<iframe src="https://www.youtube.com/embed/${id}?autoplay=1&rel=0" title="${item.title.replace(/"/g, "")}" allow="autoplay; encrypted-media" allowfullscreen></iframe>`
    : "";
  modal.classList.remove("hidden");
  modalClose.focus();
}

function closePreview() {
  modal.classList.add("hidden");
  modalFrame.innerHTML = ""; // stop playback
  if (lastFocused && lastFocused.focus) lastFocused.focus();
}

modalClose.addEventListener("click", closePreview);
modal.addEventListener("click", (e) => {
  if (e.target === modal) closePreview();
});
modalCopy.addEventListener("click", () => copyUrl(currentUrl, modalCopy));
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !modal.classList.contains("hidden")) closePreview();
});

// ---- Strict toggle --------------------------------------------------------
strictToggle.addEventListener("click", () => {
  const on = strictToggle.getAttribute("aria-checked") === "true";
  strictToggle.setAttribute("aria-checked", String(!on));
});

// ---- Search ---------------------------------------------------------------
async function doSearch(query) {
  const strict = strictToggle.getAttribute("aria-checked") === "true";
  statusEl.innerHTML = "SEARCHING YOUTUBE + RANKING LOOPS...";
  showSkeletons();

  try {
    const url = `/api/search?q=${encodeURIComponent(query)}&strict=${strict}`;
    const res = await fetch(url);
    if (!res.ok) {
      let detail = `HTTP ${res.status}`;
      try {
        const j = await res.json();
        if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch (_) {}
      showError(detail);
      statusEl.textContent = "";
      return;
    }
    const items = await res.json();
    statusEl.innerHTML =
      `<span class="count">${items.length}</span> RANKED RESULT${items.length === 1 ? "" : "S"} ` +
      `FOR "${query.toUpperCase()}"` + (strict ? " · STRICT" : "");
    render(items);
  } catch (err) {
    showError("Could not reach the server.");
    statusEl.textContent = "";
    console.error(err);
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const q = input.value.trim();
  if (q) doSearch(q);
});

// Support ?q= and ?strict= deep links.
const params = new URLSearchParams(location.search);
if (params.get("strict") === "true") strictToggle.setAttribute("aria-checked", "true");
if (params.get("q")) {
  input.value = params.get("q");
  doSearch(params.get("q"));
}
