"""Race context: everything the simulator knows before the lights go out.

Contexts come from one of three sources:

* ``fastf1``   - the full weekend from live timing: every session's pace, long
                 runs and tyre deg, qualifying, grid, weather, penalties, standings,
                 recent form and the last races at this circuit (see fastf1_source.py).
* ``fixtures`` - DynamoDB-shaped items, e.g. ``scripts/mock_fixtures`` or a table
                 scan, as written by the processor Lambda.
* ``model``    - circuit facts only; Claude fills in the entry list and form from
                 its own knowledge of that season. Works fully offline.

``source="auto"`` tries them in that order.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .circuits import CIRCUITS, circuit_for_round, event_name

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = ROOT / "scripts" / "mock_fixtures"

TEAM_CODES = {
    "red bull racing": "RBR", "red bull": "RBR", "red_bull": "RBR",
    "mclaren": "MCL", "ferrari": "FER", "mercedes": "MER",
    "aston martin": "AST", "aston_martin": "AST", "alpine": "ALP", "williams": "WIL",
    "rb": "RB", "racing bulls": "RB", "visa cash app rb": "RB",
    "kick sauber": "SAU", "kick_sauber": "SAU", "sauber": "SAU", "stake f1 team kick sauber": "SAU",
    "haas f1 team": "HAA", "haas": "HAA", "audi": "AUD", "cadillac": "CAD",
}


def team_code(name: str | None) -> str:
    if not name:
        return "UNK"
    key = name.strip().lower()
    return TEAM_CODES.get(key, key.replace(" ", "")[:3].upper())


class CircuitInfo(BaseModel):
    key: str
    name: str
    country: str
    laps: int
    length_km: float
    pit_loss_s: float
    overtaking: str
    sc_probability: float
    tyre_stress: str
    compounds: str
    drs_zones: int
    notes: str = ""


class DriverEntry(BaseModel):
    code: str
    name: str | None = None
    team: str
    grid: int | None = None
    quali_gap_s: float | None = Field(default=None, description="Gap to pole in qualifying, seconds")
    long_run_pace_s: float | None = Field(default=None, description="Median practice long-run lap, seconds")
    long_run_compound: str | None = None
    notes: str | None = None


class DataTable(BaseModel):
    """A compact table of evidence, rendered into the prompt and the UI."""

    key: str
    section: Literal["weekend", "season", "history"]
    title: str
    columns: list[str]
    rows: list[list[Any]]
    note: str | None = None

    def to_markdown(self) -> str:
        def cell(v: Any) -> str:
            return "-" if v is None or v == "" else str(v).replace("|", "/")

        lines = [f"### {self.title}", "", "| " + " | ".join(self.columns) + " |",
                 "|" + "---|" * len(self.columns)]
        lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in self.rows]
        if self.note:
            lines += ["", f"_{self.note}_"]
        return "\n".join(lines)


SECTION_TITLES = {
    "weekend": "This weekend",
    "season": "Season so far",
    "history": "History at this circuit",
}


class RaceContext(BaseModel):
    year: int
    round: int | None = None
    event_name: str
    weekend_format: str | None = None
    circuit: CircuitInfo
    drivers: list[DriverEntry] = Field(default_factory=list)
    weather: str | None = None
    extra_notes: list[str] = Field(default_factory=list)
    tables: list[DataTable] = Field(default_factory=list)
    data_sources: list[str] = Field(default_factory=list)
    # Real finishing order (driver codes) for past races. Never sent to the
    # model - only used to score a simulation after the fact.
    actual_result: list[str] | None = Field(default=None, exclude=True)

    def to_cache(self) -> dict[str, Any]:
        """Full serialisation for the on-disk cache, including the real result."""
        return {**self.model_dump(mode="json"), "actual_result": self.actual_result}

    @property
    def driver_codes(self) -> list[str]:
        return [d.code for d in self.drivers]

    def to_prompt(self) -> str:
        """Render the context as the stable block of the simulation prompt."""
        c = self.circuit
        lines = [
            f"# {self.year} {self.event_name}" + (f" (round {self.round})" if self.round else ""),
            *([f"Weekend format: {self.weekend_format}"] if self.weekend_format else []),
            "",
            "## Circuit",
            f"- {c.name}, {c.country}",
            f"- Race distance: {c.laps} laps x {c.length_km} km",
            f"- Pit-lane time loss (green flag): ~{c.pit_loss_s:.0f}s",
            f"- Overtaking: {c.overtaking}; DRS zones: {c.drs_zones}",
            f"- Safety car / VSC likelihood: {c.sc_probability:.0%}",
            f"- Tyre stress: {c.tyre_stress}; compounds: {c.compounds} (hard/medium/soft)",
        ]
        if c.notes:
            lines.append(f"- Notes: {c.notes}")
        lines += ["", "## Conditions", f"- {self.weather or 'Unknown - assume typical conditions for this event.'}"]

        lines += ["", "## Entry list"]
        if self.drivers:
            lines.append("| Grid | Code | Driver | Team | Quali gap to pole | Practice long run |")
            lines.append("|---|---|---|---|---|---|")
            for d in sorted(self.drivers, key=lambda d: (d.grid is None, d.grid or 99)):
                gap = f"+{d.quali_gap_s:.3f}s" if d.quali_gap_s is not None else "-"
                run = (
                    f"{d.long_run_pace_s:.3f}s ({d.long_run_compound or '?'})"
                    if d.long_run_pace_s is not None
                    else "-"
                )
                lines.append(f"| {d.grid or '-'} | {d.code} | {d.name or '-'} | {d.team} | {gap} | {run} |")
                if d.notes:
                    lines.append(f"|  |  | note: {d.notes} |  |  |  |")
        else:
            lines.append(
                f"No entry list was supplied. Use the real {self.year} entry list for this event "
                "(official three-letter driver codes) and your best knowledge of the qualifying "
                "order and each team's competitive form at that point of the season."
            )
        for section, heading in SECTION_TITLES.items():
            tables = [t for t in self.tables if t.section == section]
            if tables:
                lines += ["", f"## {heading}", ""]
                lines += [t.to_markdown() + "\n" for t in tables]
        if self.extra_notes:
            lines += ["", "## Additional notes", *[f"- {n}" for n in self.extra_notes]]
        if self.data_sources:
            lines += ["", f"_Data sources: {', '.join(self.data_sources)}_"]
        return "\n".join(lines)


def _circuit_info(key: str) -> CircuitInfo:
    return CircuitInfo(key=key, **CIRCUITS[key])


Source = Literal["auto", "fastf1", "fixtures", "model"]


def build_context(
    year: int,
    round_number: int | None = None,
    *,
    circuit: str | None = None,
    source: Source = "auto",
    fixtures_dir: Path | str | None = None,
    progress: Callable[[str], None] | None = None,
) -> RaceContext:
    """Build a race context for ``year`` + (``round_number`` or ``circuit`` key)."""
    if round_number is None and circuit is None:
        raise ValueError("Pass a round number or a circuit key")

    attempts: list[str] = ["fastf1", "fixtures", "model"] if source == "auto" else [source]
    errors: list[str] = []
    for attempt in attempts:
        try:
            if attempt == "fastf1":
                if round_number is None:
                    raise ValueError("FastF1 source needs a round number")
                from .fastf1_source import from_fastf1

                return from_fastf1(year, round_number, progress=progress)
            if attempt == "fixtures":
                if round_number is None:
                    raise ValueError("fixtures source needs a round number")
                return from_fixtures(year, round_number, fixtures_dir or FIXTURES_DIR)
            return from_model_knowledge(year, round_number, circuit)
        except Exception as exc:  # noqa: BLE001 - fall through to the next source
            logger.info("context source %s failed: %s", attempt, exc)
            errors.append(f"{attempt}: {exc}")
    raise ValueError("Could not build race context - " + "; ".join(errors))


def from_model_knowledge(year: int, round_number: int | None = None, circuit: str | None = None) -> RaceContext:
    key = circuit or (circuit_for_round(year, round_number) if round_number else None)
    if not key or key not in CIRCUITS:
        raise ValueError(f"Unknown circuit for {year} round {round_number} / {circuit!r}")
    info = _circuit_info(key)
    return RaceContext(
        year=year,
        round=round_number,
        event_name=event_name(key),
        circuit=info,
        data_sources=["circuit reference table", "model knowledge (entry list & form)"],
    )


def from_fixtures(year: int, round_number: int, fixtures_dir: Path | str) -> RaceContext:
    items: list[dict[str, Any]] = []
    for fp in Path(fixtures_dir).glob("*.json"):
        payload = json.loads(fp.read_text())
        if isinstance(payload, list):
            items.extend(i for i in payload if i.get("PK") == f"RACE#{year}#{round_number}")
    return from_items(year, round_number, items, source_label=f"fixtures ({fixtures_dir})")


def from_dynamo(year: int, round_number: int, table_name: str | None = None) -> RaceContext:
    import boto3
    from boto3.dynamodb.conditions import Key

    table = boto3.resource("dynamodb").Table(table_name or os.environ["TABLE_NAME"])
    resp = table.query(KeyConditionExpression=Key("PK").eq(f"RACE#{year}#{round_number}"))
    return from_items(year, round_number, resp.get("Items", []), source_label="DynamoDB")


def from_items(year: int, round_number: int, items: list[dict[str, Any]], source_label: str) -> RaceContext:
    """Build a context from processor-shaped DynamoDB items for one race."""
    quali = {i["DriverCode"]: i for i in items if str(i.get("SK", "")).startswith("QUALIFYING#")}
    results = {i["DriverCode"]: i for i in items if str(i.get("SK", "")).startswith("RESULT#")}
    if not quali and not results:
        raise ValueError(f"no RESULT#/QUALIFYING# items for {year} round {round_number}")

    drivers: list[DriverEntry] = []
    for code in sorted(set(quali) | set(results)):
        q, r = quali.get(code, {}), results.get(code, {})
        grid = r.get("Grid") or q.get("Position")
        drivers.append(
            DriverEntry(
                code=code,
                name=r.get("DriverName") or q.get("DriverName"),
                team=r.get("TeamCode") or q.get("TeamCode") or "UNK",
                grid=int(grid) if grid else None,
                quali_gap_s=_float(q.get("GapToPole")),
            )
        )

    actual = None
    if results:
        finished = sorted(
            (r for r in results.values() if r.get("Position")), key=lambda r: int(r["Position"])
        )
        actual = [r["DriverCode"] for r in finished]

    key = circuit_for_round(year, round_number)
    if key is None:
        raise ValueError(f"no circuit mapping for {year} round {round_number}")
    info = _circuit_info(key)
    notes = []
    if len(drivers) < 18:
        notes.append(
            f"Only {len(drivers)} drivers are listed from the data store; add the rest of the "
            f"real {year} field from your knowledge so the race has a full grid."
        )
    return RaceContext(
        year=year,
        round=round_number,
        event_name=event_name(key),
        circuit=info,
        drivers=drivers,
        extra_notes=notes,
        data_sources=[source_label, "circuit reference table"],
        actual_result=actual,
    )


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
