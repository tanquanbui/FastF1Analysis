import { api } from "./api.js";
import { pageHistory } from "./pages/history.js";
import { pageNewSim } from "./pages/newSim.js";
import { pageResult } from "./pages/result.js";
import { esc } from "./util.js";

const app = document.getElementById("app");
let status = null;

function navigate(hash) {
  if (location.hash === hash) route();
  else location.hash = hash;
}

function setNav(name) {
  document.querySelectorAll(".primary-nav a").forEach((a) => a.classList.toggle("is-active", a.dataset.route === name));
}

async function route() {
  const hash = location.hash || "#/";
  app.innerHTML = `<section class="loader"><div class="spinner"></div><p>Loading…</p></section>`;
  window.scrollTo(0, 0);
  try {
    const result = hash.match(/^#\/r\/([\w-]+)/);
    if (result) {
      setNav("history");
      await pageResult(app, result[1], { status, navigate });
    } else if (hash.startsWith("#/history")) {
      setNav("history");
      await pageHistory(app, { status, navigate });
    } else {
      setNav("new");
      await pageNewSim(app, { status, navigate });
    }
  } catch (err) {
    app.innerHTML = `<section class="error">${esc(err.message)}</section>`;
  }
}

async function boot() {
  try {
    status = await api.status();
  } catch (err) {
    app.innerHTML = `<section class="error">Can't reach the simulator server (${esc(err.message)}). Start it with <code>python -m simulator.server</code>.</section>`;
    return;
  }
  const badge = document.getElementById("mode-badge");
  badge.textContent = status.ai_available ? `AI · ${status.model}` : "DEMO MODE";
  badge.classList.toggle("demo", !status.ai_available);
  window.addEventListener("hashchange", route);
  route();
}

boot();
