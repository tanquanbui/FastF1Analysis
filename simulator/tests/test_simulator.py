"""Tests for the AI race simulator, with a fake Anthropic client."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from simulator import RaceSimulator, SimulationError, build_context, validate
from simulator.demo import demo_simulation
from simulator.engine import aggregate


class _Stream:
    def __init__(self, message):
        self._message = message

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self._message


class FakeClient:
    """Mimics client.beta.messages.stream(), returning queued simulations."""

    def __init__(self, outputs, stop_reason="end_turn"):
        self.outputs = list(outputs)
        self.calls = []
        self.stop_reason = stop_reason
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))

    def _stream(self, **kwargs):
        # Snapshot messages: the session list keeps growing after the call.
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        parsed = self.outputs.pop(0) if self.outputs else None
        usage = SimpleNamespace(input_tokens=100, output_tokens=50, cache_read_input_tokens=10,
                                cache_creation_input_tokens=0)
        return _Stream(SimpleNamespace(parsed_output=parsed, stop_reason=self.stop_reason,
                                       content=[{"type": "text", "text": "{}"}], usage=usage))


@pytest.fixture
def ctx():
    return build_context(2024, 5, source="fixtures")


def test_fixture_context_renders_grid(ctx):
    prompt = ctx.to_prompt()
    assert "2024 Chinese Grand Prix" in prompt
    assert "| 1 | VER |" in prompt
    assert ctx.actual_result[0] == "VER"
    assert "actual_result" not in ctx.model_dump()


def test_model_source_has_no_entry_list():
    ctx = build_context(2025, 8, source="model")
    assert ctx.circuit.key == "monaco"
    assert "No entry list was supplied" in ctx.to_prompt()


def test_demo_simulation_is_consistent(ctx):
    assert validate.check(demo_simulation(ctx), ctx) == []


def test_run_sends_structured_request(ctx):
    client = FakeClient([demo_simulation(ctx)])
    result = RaceSimulator(client, model="claude-opus-5-5", effort="high").simulate(ctx, "Rain on lap 30")

    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"] == {"effort": "high"}
    assert call["fallbacks"] == "default"
    assert "Scenario: Rain on lap 30" in call["messages"][0]["content"][1]["text"]
    assert result.issues == []
    assert result.comparison is not None
    assert sum(result.points.values()) > 0


def test_what_if_appends_to_conversation(ctx):
    client = FakeClient([demo_simulation(ctx), demo_simulation(ctx, seed=3)])
    session = RaceSimulator(client).start(ctx)
    session.run()
    follow = session.what_if("NOR pits under the safety car")

    roles = [m["role"] for m in client.calls[1]["messages"]]
    assert roles == ["user", "assistant", "user"]
    assert follow.kind == "what_if" and follow.comparison is None
    assert len(session.results) == 2


def test_inconsistent_output_triggers_one_repair(ctx):
    broken = demo_simulation(ctx).model_copy(deep=True)
    broken.lap_chart = broken.lap_chart[:-1]
    client = FakeClient([broken, demo_simulation(ctx)])
    result = RaceSimulator(client).simulate(ctx)
    assert len(client.calls) == 2
    assert "consistency problems" in client.calls[1]["messages"][-1]["content"]
    assert result.issues == []


def test_refusal_raises_and_rolls_back(ctx):
    client = FakeClient([None], stop_reason="refusal")
    session = RaceSimulator(client).start(ctx)
    with pytest.raises(SimulationError):
        session.run()
    assert session.messages == []


def test_monte_carlo_aggregates(ctx):
    sims = [demo_simulation(ctx, seed=s) for s in range(4)]
    client = FakeClient(sims)
    summary = RaceSimulator(client).simulate_many(ctx, runs=4, max_workers=1)
    assert summary.runs == 4
    assert abs(sum(summary.win_probability.values()) - 1) < 1e-6
    direct = aggregate(summary.results)
    assert direct.average_finish == summary.average_finish


def test_validation_flags_duplicates(ctx):
    sim = demo_simulation(ctx).model_copy(deep=True)
    sim.classification[1].driver = sim.classification[0].driver
    assert any("more than once" in i for i in validate.check(sim, ctx))
