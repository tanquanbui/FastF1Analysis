"""Export a simulation as a Markdown race report."""
from __future__ import annotations

from typing import Any


def to_markdown(result: dict[str, Any], event: str | None = None) -> str:
    sim = result["simulation"]
    points = result.get("points", {})
    strategies = {s["driver"]: s for s in sim["strategies"]}
    out = [f"# {sim['headline']}", ""]
    if event:
        out.append(f"**{event}**" + (f" · scenario: _{result['prompt']}_" if result.get("prompt") else ""))
        out.append("")
    out += [f"Conditions: {sim['weather_summary']}", "", "## Classification", "",
            "| Pos | Driver | Team | Grid | Gap | Tyres | Stops | Pts |", "|---|---|---|---|---|---|---|---|"]
    for c in sim["classification"]:
        s = strategies.get(c["driver"], {})
        tyres = "-".join(st["compound"][0] for st in s.get("stints", []))
        fl = " (FL)" if c["fastest_lap"] else ""
        out.append(f"| {c['position']} | {c['driver']}{fl} | {c['team']} | {c['grid']} | {c['gap']} | {tyres} | "
                   f"{len(s.get('pit_stops', []))} | {points.get(c['driver'], 0)} |")
    out += ["", "## Strategy brief", ""]
    out += [f"- **{i['title']}** — {i['detail']}" for i in sim["insights"]]
    out += ["", "## Key moments", ""]
    out += [f"- L{e['lap']} · {e['type'].replace('_', ' ').title()} — {e['description']}" for e in sim["events"]]
    out += ["", "## Pit stops", ""]
    for c in sim["classification"]:
        for p in strategies.get(c["driver"], {}).get("pit_stops", []):
            sc = " under SC/VSC" if p["under_neutralisation"] else ""
            out.append(f"- {c['driver']} L{p['lap']}: {p['from_compound']} → {p['to_compound']} "
                       f"({p['stationary_s']:.1f}s{sc}) — {p['reason']}")
    out += ["", "## Race report", "", sim["narrative"], ""]
    if sim.get("assumptions"):
        out += ["## Assumptions", ""] + [f"- {a}" for a in sim["assumptions"]] + [""]
    comp = result.get("comparison")
    if comp:
        out += ["## vs the real race", "",
                f"- Winner: {'correct' if comp['winner_correct'] else 'actual ' + comp['actual_order'][0]}",
                f"- Podium overlap: {comp['podium_overlap']}/3",
                f"- Mean position error: {comp['mean_abs_position_error']}", ""]
    out.append(f"_Simulated by {result.get('model', 'unknown model')}._")
    return "\n".join(out)
