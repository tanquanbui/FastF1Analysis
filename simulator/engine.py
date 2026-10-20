"""Claude-driven race simulation.

One ``SimulationSession`` is one conversation with Claude about one race:
``run()`` simulates the race (optionally under a scenario), and each
``what_if()`` re-simulates it from a changed premise, with the earlier
simulation still in context so Claude can explain what changed and why.

``RaceSimulator.simulate_many`` runs several independent sessions in parallel
and aggregates them into win / podium / points probabilities.
"""
from __future__ import annotations

import logging
import os
import uuid
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anthropic
from pydantic import BaseModel, Field

from . import validate
from .context import RaceContext
from .schema import RaceSimulation

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("SIM_MODEL", "claude-opus-5-5")
DEFAULT_EFFORT = os.environ.get("SIM_EFFORT", "high")
MAX_TOKENS = 64000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

SYSTEM_PROMPT = """\
You are the race simulation engine and chief strategist for an F1 analysis tool. \
Given a race context (circuit, entry list, qualifying, practice pace, conditions) \
and optionally a scenario, you simulate the Grand Prix lap by lap and return it \
in the requested JSON structure.

How to simulate:
- Ground pace in the data. Qualifying gaps and practice long runs are the best \
evidence of each car's speed; where data is missing, use your knowledge of that \
season's competitive order and say so in `assumptions`.
- Model the race, not just the grid: fuel burn makes cars faster through a stint, \
tyres degrade per the circuit's tyre stress, softer compounds are faster but \
shorter-lived, and dirty air plus the circuit's overtaking difficulty limit passes. \
A pit stop costs roughly the circuit's pit-loss time under green flag and about \
half that under a safety car or VSC.
- Make strategy calls the way a pit wall would: planned windows, undercut and \
overcut threats, covering rivals, reacting to safety cars, weather and degradation. \
Explain notable calls in each pit stop's `reason`.
- Let racing randomness happen at a realistic rate for this circuit: lap-one \
incidents, safety cars per the stated likelihood, the occasional mechanical DNF, \
penalties. Don't force drama, and don't remove it either.
- In dry races each finisher must use at least two different dry compounds.
- A scenario from the user is a fact of this race. Apply it at the stated time and \
follow its consequences through the strategies and the result.

Output rules:
- Use exactly the driver codes from the entry list. Every starter appears once in \
`classification` and once in `strategies`.
- `lap_chart` has one entry per lap from 1 to the final lap, leader first. Drivers \
who retire drop out from the lap after they stop. The final lap must match the \
classification order of the finishers.
- Stints are contiguous: the first starts on lap 1, each next one starts the lap \
after the previous `end_lap`, and the last ends at the driver's `laps_completed`. \
Stints minus one equals the number of pit stops.
- Write the narrative and insights like a sharp race engineer briefing the team: \
specific laps, gaps and decisions, no filler.
"""

FOLLOW_UP_PROMPT = """\
What-if: {question}

Re-simulate the whole race with this change. Keep everything before the point \
of divergence the same unless the change itself affects it, then let the \
consequences play out. Return the complete simulation in the same structure. \
In `insights`, start with what changed compared with the previous simulation \
and why."""

REPAIR_PROMPT = """\
The simulation has consistency problems:
{issues}

Return the complete corrected simulation. Keep the same race story; only fix \
what's needed to make the data consistent."""


class SimulationError(RuntimeError):
    pass


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def add(self, usage: Any) -> None:
        for field in Usage.model_fields:
            setattr(self, field, getattr(self, field) + (getattr(usage, field, 0) or 0))


class SimulationResult(BaseModel):
    id: str
    session_id: str
    kind: str = Field(description="'run' or 'what_if'")
    prompt: str | None
    model: str
    simulation: RaceSimulation
    points: dict[str, int]
    issues: list[str] = Field(description="Consistency problems still present after repair")
    comparison: dict[str, Any] | None = Field(description="Accuracy vs the real result, past races only")
    usage: Usage


class MonteCarloSummary(BaseModel):
    runs: int
    scenario: str | None
    win_probability: dict[str, float]
    podium_probability: dict[str, float]
    points_probability: dict[str, float]
    dnf_probability: dict[str, float]
    average_finish: dict[str, float]
    position_distribution: dict[str, dict[int, int]]
    results: list[SimulationResult]


class SimulationSession:
    """A multi-turn conversation with Claude about one race."""

    def __init__(self, simulator: "RaceSimulator", context: RaceContext):
        self.id = uuid.uuid4().hex[:12]
        self.simulator = simulator
        self.context = context
        self.messages: list[dict[str, Any]] = []
        self.results: list[SimulationResult] = []
        self.usage = Usage()

    def run(self, scenario: str | None = None, *, run_note: str | None = None) -> SimulationResult:
        if self.messages:
            raise SimulationError("run() already called - use what_if() for follow-ups")
        task = "Simulate this race."
        if scenario:
            task += f"\n\nScenario: {scenario}"
        if run_note:
            task += f"\n\n{run_note}"
        return self._turn(
            "run",
            scenario,
            {
                "role": "user",
                "content": [
                    # Stable race context first, cached so what-ifs and parallel
                    # runs re-read it cheaply.
                    {"type": "text", "text": self.context.to_prompt(), "cache_control": {"type": "ephemeral"}},
                    {"type": "text", "text": task},
                ],
            },
        )

    def what_if(self, question: str) -> SimulationResult:
        if not self.messages:
            raise SimulationError("call run() before what_if()")
        return self._turn(
            "what_if", question, {"role": "user", "content": FOLLOW_UP_PROMPT.format(question=question)}
        )

    def _turn(self, kind: str, prompt: str | None, user_message: dict[str, Any]) -> SimulationResult:
        start = len(self.messages)
        self.messages.append(user_message)
        try:
            return self._complete_turn(kind, prompt)
        except Exception:
            # Drop the failed turn so the session can be retried cleanly.
            del self.messages[start:]
            raise

    def _complete_turn(self, kind: str, prompt: str | None) -> SimulationResult:
        usage = Usage()
        sim = self._call(usage)
        issues = validate.check(sim, self.context)
        if issues and self.simulator.repair:
            logger.info("repairing %d consistency issues", len(issues))
            self.messages.append(
                {"role": "user", "content": REPAIR_PROMPT.format(issues="\n".join(f"- {i}" for i in issues))}
            )
            sim = self._call(usage)
            issues = validate.check(sim, self.context)
        self.usage.add(usage)
        result = SimulationResult(
            id=uuid.uuid4().hex[:12],
            session_id=self.id,
            kind=kind,
            prompt=prompt,
            model=self.simulator.model,
            simulation=sim,
            points=validate.points_for(sim, self.context.year),
            issues=issues,
            # A what-if is counterfactual by design, so only score the base run.
            comparison=validate.compare_to_actual(sim, self.context.actual_result) if kind == "run" else None,
            usage=usage,
        )
        self.results.append(result)
        return result

    def _call(self, usage: Usage) -> RaceSimulation:
        sim = self.simulator
        try:
            with sim.client.beta.messages.stream(
                model=sim.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=self.messages,
                output_format=RaceSimulation,
                output_config={"effort": sim.effort},
                cache_control={"type": "ephemeral"},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            ) as stream:
                message = stream.get_final_message()
        except anthropic.APIError as exc:
            raise SimulationError(f"Claude API error: {exc}") from exc

        usage.add(message.usage)
        if message.stop_reason == "refusal":
            raise SimulationError("Claude declined to simulate this scenario")
        if message.stop_reason == "max_tokens":
            raise SimulationError("Simulation was cut off at the output limit")
        if message.parsed_output is None:
            raise SimulationError(f"No structured output (stop_reason={message.stop_reason})")
        # Append-only history: the full assistant content (including thinking
        # blocks) goes back so follow-ups build on the same reasoning.
        self.messages.append({"role": "assistant", "content": message.content})
        return message.parsed_output


class RaceSimulator:
    def __init__(
        self,
        client: Any = None,
        *,
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        repair: bool = True,
    ):
        self.client = client or anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.repair = repair

    def start(self, context: RaceContext) -> SimulationSession:
        return SimulationSession(self, context)

    def simulate(self, context: RaceContext, scenario: str | None = None) -> SimulationResult:
        return self.start(context).run(scenario)

    def simulate_many(
        self,
        context: RaceContext,
        scenario: str | None = None,
        runs: int = 5,
        max_workers: int = 4,
    ) -> MonteCarloSummary:
        """Independent runs in parallel, aggregated into probabilities."""

        def one(i: int) -> SimulationResult:
            note = (
                f"This is independent run {i + 1} of {runs}. Sample one plausible way this race "
                "unfolds rather than the single most likely outcome: let incidents, safety cars "
                "and strategy gambles land where they realistically might."
            )
            return self.start(context).run(scenario, run_note=note)

        with ThreadPoolExecutor(max_workers=max(1, min(max_workers, runs))) as pool:
            results = list(pool.map(one, range(runs)))
        return aggregate(results, scenario)


def aggregate(results: list[SimulationResult], scenario: str | None = None) -> MonteCarloSummary:
    n = len(results)
    dist: dict[str, Counter] = defaultdict(Counter)
    dnfs: Counter = Counter()
    for r in results:
        for c in r.simulation.classification:
            dist[c.driver][c.position] += 1
            if c.status.upper().startswith(("DNF", "DSQ")):
                dnfs[c.driver] += 1

    def prob(pred) -> dict[str, float]:
        out = {d: round(sum(v for p, v in cnt.items() if pred(p)) / n, 3) for d, cnt in dist.items()}
        return dict(sorted(((d, p) for d, p in out.items() if p > 0), key=lambda kv: -kv[1]))

    avg = {d: round(sum(p * v for p, v in cnt.items()) / sum(cnt.values()), 2) for d, cnt in dist.items()}
    return MonteCarloSummary(
        runs=n,
        scenario=scenario,
        win_probability=prob(lambda p: p == 1),
        podium_probability=prob(lambda p: p <= 3),
        points_probability=prob(lambda p: p <= 10),
        dnf_probability=dict(sorted(((d, round(c / n, 3)) for d, c in dnfs.items()), key=lambda kv: -kv[1])),
        average_finish=dict(sorted(avg.items(), key=lambda kv: kv[1])),
        position_distribution={d: dict(sorted(cnt.items())) for d, cnt in dist.items()},
        results=results,
    )
