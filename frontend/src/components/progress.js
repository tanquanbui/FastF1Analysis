import { esc } from "../util.js";

// Live view of a running job: stage, Claude's summarised reasoning, lap progress.
// Built once, then updated in place on each poll so animations and the
// reasoning box's scroll position aren't reset every second.
export function renderProgress(el, job, title) {
  let card = el.querySelector(".sim-running");
  if (!card) {
    el.innerHTML = `
      <div class="card sim-running">
        <div class="race-lights">${"<span></span>".repeat(5)}</div>
        <h3>${esc(title)}</h3>
        <p class="progress-stage"></p>
        <div class="lap-progress" hidden><span></span></div>
        <p class="muted small mono lap-label" hidden></p>
        <div class="thinking" hidden><span class="eyebrow-inline">Strategist's reasoning</span><p></p></div>
        <p class="muted small elapsed"></p>
      </div>`;
    card = el.querySelector(".sim-running");
  }
  const runs = job.runs_total ? ` · ${job.runs_done || 0}/${job.runs_total} runs finished` : "";
  card.querySelector(".progress-stage").textContent = `${job.stage || "Starting"}${runs}`;

  const lapsPct = job.laps_total && job.laps_done ? Math.min(100, Math.round((job.laps_done / job.laps_total) * 100)) : 0;
  card.querySelector(".lap-progress").hidden = !lapsPct;
  card.querySelector(".lap-label").hidden = !lapsPct;
  if (lapsPct) {
    card.querySelector(".lap-progress span").style.width = `${lapsPct}%`;
    card.querySelector(".lap-label").textContent = `lap chart ${job.laps_done}/${job.laps_total}`;
  }

  const thinking = card.querySelector(".thinking");
  thinking.hidden = !job.thinking;
  if (job.thinking) {
    const p = thinking.querySelector("p");
    const atBottom = p.scrollTop + p.clientHeight >= p.scrollHeight - 8;
    p.textContent = job.thinking;
    if (atBottom) p.scrollTop = p.scrollHeight;
  }
  card.querySelector(".elapsed").textContent =
    `${Math.round(job.elapsed_s || 0)}s · full-context simulations usually take 1–4 minutes`;
}
