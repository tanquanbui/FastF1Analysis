"""Turn raw FastF1 frames into compact, model-friendly tables.

Everything here is a pure function over pandas DataFrames shaped like FastF1's
``Laps`` / ``SessionResults`` / weather / race-control frames, so it can be
tested without network access. ``fastf1_source.py`` does the loading.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Lap-time gain per lap from burning fuel (~1.6 kg/lap at ~0.035 s/kg). Added
# back to a stint's raw slope to estimate true tyre degradation.
FUEL_EFFECT_S_PER_LAP = 0.055
GREEN = "1"


def secs(series: pd.Series) -> pd.Series:
    """Timedelta (or numeric) series -> float seconds."""
    if pd.api.types.is_timedelta64_dtype(series):
        return series.dt.total_seconds()
    return pd.to_numeric(series, errors="coerce")


def _clean(laps: pd.DataFrame) -> pd.DataFrame:
    out = laps[laps["LapTime"].notna()].copy()
    if "Deleted" in out:
        out = out[out["Deleted"] != True]  # noqa: E712 - column holds True/False/NaN
    out["LapSeconds"] = secs(out["LapTime"])
    return out


def _green(laps: pd.DataFrame) -> pd.DataFrame:
    """Racing laps only: green track, no pit in/out laps."""
    out = laps
    if "TrackStatus" in out:
        out = out[out["TrackStatus"].astype(str) == GREEN]
    for col in ("PitInTime", "PitOutTime"):
        if col in out:
            out = out[out[col].isna()]
    return out


def _r(x: Any, nd: int = 3) -> float | None:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    return round(float(x), nd)


# ---------------------------------------------------------------- practice
def session_pace(laps: pd.DataFrame) -> list[dict[str, Any]]:
    """Per driver: best lap, gap, ideal lap from best sectors, top speed, laps run."""
    if laps is None or laps.empty:
        return []
    clean = _clean(laps)
    if clean.empty:
        return []
    overall = clean["LapSeconds"].min()
    rows = []
    for drv, d in clean.groupby("Driver"):
        sectors = [secs(d[c]).min() for c in ("Sector1Time", "Sector2Time", "Sector3Time") if c in d]
        ideal = sum(sectors) if len(sectors) == 3 and not any(np.isnan(sectors)) else None
        rows.append(
            {
                "driver": drv,
                "team": d["Team"].iloc[0] if "Team" in d else None,
                "best_s": _r(d["LapSeconds"].min()),
                "gap_s": _r(d["LapSeconds"].min() - overall),
                "ideal_s": _r(ideal),
                "top_speed_kph": _r(pd.to_numeric(d["SpeedST"], errors="coerce").max(), 0) if "SpeedST" in d else None,
                "laps": int((laps["Driver"] == drv).sum()),
            }
        )
    return sorted(rows, key=lambda r: r["best_s"])


def long_runs(laps: pd.DataFrame, min_laps: int = 5) -> list[dict[str, Any]]:
    """Every green-flag stint of ``min_laps``+ laps: pace and degradation."""
    if laps is None or laps.empty:
        return []
    green = _green(_clean(laps))
    runs = []
    for (drv, stint), d in green.groupby(["Driver", "Stint"]):
        if len(d) < min_laps:
            continue
        med = d["LapSeconds"].median()
        d = d[d["LapSeconds"] <= med * 1.04]  # drop traffic / mistakes / cool-down laps
        if len(d) < min_laps:
            continue
        x = pd.to_numeric(d["TyreLife"], errors="coerce") if "TyreLife" in d else d["LapNumber"]
        if x.isna().any():
            x = d["LapNumber"]
        slope = float(np.polyfit(x.astype(float), d["LapSeconds"].astype(float), 1)[0]) if x.nunique() > 1 else 0.0
        runs.append(
            {
                "driver": drv,
                "team": d["Team"].iloc[0] if "Team" in d else None,
                "compound": str(d["Compound"].iloc[0]) if "Compound" in d else None,
                "laps": int(len(d)),
                "median_s": _r(d["LapSeconds"].median()),
                "raw_slope_s_per_lap": _r(slope),
                "deg_s_per_lap": _r(slope + FUEL_EFFECT_S_PER_LAP),
                "tyre_age_start": int(x.min()) if not x.isna().all() else None,
            }
        )
    return sorted(runs, key=lambda r: (r["driver"], -r["laps"]))


def best_long_run(runs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Longest run per driver (ties -> faster)."""
    best: dict[str, dict[str, Any]] = {}
    for r in runs:
        cur = best.get(r["driver"])
        if cur is None or (r["laps"], -r["median_s"]) > (cur["laps"], -cur["median_s"]):
            best[r["driver"]] = r
    return best


def compound_summary(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Field-wide view of each compound from practice long runs."""
    if not runs:
        return []
    df = pd.DataFrame(runs)
    rows = []
    for comp, d in df.groupby("compound"):
        rows.append(
            {
                "compound": comp,
                "runs": int(len(d)),
                "median_pace_s": _r(d["median_s"].median()),
                "median_deg_s_per_lap": _r(d["deg_s_per_lap"].median()),
                "high_deg_s_per_lap": _r(d["deg_s_per_lap"].quantile(0.8)),
                "longest_run_laps": int(d["laps"].max()),
            }
        )
    return sorted(rows, key=lambda r: r["median_pace_s"])


# ---------------------------------------------------------------- results
def _fmt_td(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    s = value.total_seconds() if hasattr(value, "total_seconds") else float(value)
    m, rest = divmod(s, 60)
    return f"{int(m)}:{rest:06.3f}" if m else f"{rest:.3f}"


def qualifying_table(results: pd.DataFrame) -> list[dict[str, Any]]:
    if results is None or results.empty:
        return []
    best = []
    for _, r in results.iterrows():
        times = [r.get(c) for c in ("Q3", "Q2", "Q1")]
        vals = [t.total_seconds() for t in times if t is not None and not pd.isna(t)]
        best.append(min(vals) if vals else None)
    pole = min((b for b in best if b), default=None)
    rows = []
    for (_, r), b in zip(results.iterrows(), best):
        pos = r.get("Position")
        rows.append(
            {
                "pos": int(pos) if pos is not None and not pd.isna(pos) else None,
                "driver": r["Abbreviation"],
                "team": r.get("TeamName"),
                "q1": _fmt_td(r.get("Q1")),
                "q2": _fmt_td(r.get("Q2")),
                "q3": _fmt_td(r.get("Q3")),
                "gap_s": _r(b - pole) if b and pole else None,
            }
        )
    return sorted(rows, key=lambda r: (r["pos"] is None, r["pos"] or 99))


def classification(results: pd.DataFrame) -> list[dict[str, Any]]:
    """Race / sprint result rows: finish, grid, status, points."""
    if results is None or results.empty:
        return []
    rows = []
    for _, r in results.iterrows():
        pos, grid = r.get("Position"), r.get("GridPosition")
        rows.append(
            {
                "pos": int(pos) if pos is not None and not pd.isna(pos) else None,
                "driver": r["Abbreviation"],
                "team": r.get("TeamName"),
                "grid": int(grid) if grid is not None and not pd.isna(grid) else None,
                "status": r.get("Status"),
                "points": _r(r.get("Points"), 0),
            }
        )
    return sorted(rows, key=lambda r: (r["pos"] is None, r["pos"] or 99))


# ---------------------------------------------------------------- conditions
def weather_summary(weather: pd.DataFrame) -> dict[str, Any] | None:
    if weather is None or weather.empty:
        return None
    num = lambda c: pd.to_numeric(weather[c], errors="coerce") if c in weather else pd.Series(dtype=float)  # noqa: E731
    rain = weather["Rainfall"].astype(bool) if "Rainfall" in weather else pd.Series([False])
    return {
        "air_c": f"{num('AirTemp').min():.0f}-{num('AirTemp').max():.0f}",
        "track_c": f"{num('TrackTemp').min():.0f}-{num('TrackTemp').max():.0f}",
        "humidity_pct": _r(num("Humidity").mean(), 0),
        "wind_ms": _r(num("WindSpeed").mean(), 1),
        "rain_share": _r(rain.mean(), 2),
    }


PENALTY_WORDS = ("PENALTY", "GRID", "REPRIMAND", "DISQUALIFIED", "UNDER INVESTIGATION", "NO FURTHER")


def race_control_highlights(messages: pd.DataFrame, limit: int = 25) -> list[str]:
    """Penalties, investigations and grid drops from race-control messages."""
    if messages is None or messages.empty or "Message" not in messages:
        return []
    msgs = messages["Message"].astype(str)
    picked = msgs[msgs.str.upper().str.contains("|".join(PENALTY_WORDS))]
    seen, out = set(), []
    for m in picked:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out[-limit:]


def track_limit_deletions(messages: pd.DataFrame) -> dict[str, int]:
    """Lap times deleted for track limits, per car number."""
    if messages is None or messages.empty or "Message" not in messages:
        return {}
    msgs = messages["Message"].astype(str)
    hits = msgs[msgs.str.contains("DELETED") & msgs.str.contains("TRACK LIMITS")]
    counts: dict[str, int] = {}
    for m in hits:
        num = m.split("CAR ")[1].split(" ")[0] if "CAR " in m else "?"
        counts[num] = counts.get(num, 0) + 1
    return counts


# ---------------------------------------------------------------- history
def neutralisations(laps: pd.DataFrame) -> dict[str, list[tuple[int, int]]]:
    """SC / VSC / red-flag periods as (first_lap, last_lap), from lap TrackStatus."""
    out: dict[str, list[tuple[int, int]]] = {"SC": [], "VSC": [], "RED": []}
    if laps is None or laps.empty or "TrackStatus" not in laps:
        return out
    by_lap = laps.groupby("LapNumber")["TrackStatus"].apply(lambda s: "".join(s.astype(str)))
    for kind, codes in (("SC", "4"), ("VSC", "67"), ("RED", "5")):
        flagged = sorted(int(lap) for lap, st in by_lap.items() if any(c in st for c in codes))
        start = prev = None
        for lap in flagged:
            if start is None:
                start = prev = lap
            elif lap == prev + 1:
                prev = lap
            else:
                out[kind].append((start, prev))
                start = prev = lap
        if start is not None:
            out[kind].append((start, prev))
    return out


def strategies(laps: pd.DataFrame) -> dict[str, dict[str, Any]]:
    """Compound sequence and pit laps per driver from race laps."""
    out: dict[str, dict[str, Any]] = {}
    if laps is None or laps.empty:
        return out
    for drv, d in laps.sort_values("LapNumber").groupby("Driver"):
        stints = []
        for _, s in d.groupby("Stint"):
            comp = str(s["Compound"].iloc[0])[:1] if "Compound" in s and pd.notna(s["Compound"].iloc[0]) else "?"
            stints.append((comp, int(s["LapNumber"].min()), int(s["LapNumber"].max())))
        stints.sort(key=lambda t: t[1])
        out[drv] = {
            "sequence": "-".join(c for c, _, _ in stints),
            "pit_laps": [e for _, _, e in stints[:-1]],
        }
    return out


def measured_pit_loss(laps: pd.DataFrame) -> float | None:
    """Median (in-lap + out-lap) minus two typical green laps, green-flag stops only."""
    if laps is None or laps.empty or "PitInTime" not in laps:
        return None
    clean = _clean(laps)
    typical = _green(clean).groupby("Driver")["LapSeconds"].median()
    losses = []
    for drv, d in clean.sort_values("LapNumber").groupby("Driver"):
        d = d.set_index("LapNumber")
        for lap in d.index[d["PitInTime"].notna()]:
            if lap + 1 not in d.index or drv not in typical:
                continue
            pair = d.loc[[lap, lap + 1]]
            if "TrackStatus" in pair and not (pair["TrackStatus"].astype(str) == GREEN).all():
                continue
            losses.append(pair["LapSeconds"].sum() - 2 * typical[drv])
    losses = [x for x in losses if 5 < x < 60]
    return _r(float(np.median(losses)), 1) if losses else None


def lap_one_moves(laps: pd.DataFrame, results: pd.DataFrame) -> list[dict[str, Any]]:
    if laps is None or laps.empty or results is None or results.empty or "Position" not in laps:
        return []
    grid = dict(zip(results["Abbreviation"], results["GridPosition"]))
    lap1 = laps[laps["LapNumber"] == 1]
    moves = []
    for _, r in lap1.iterrows():
        g = grid.get(r["Driver"])
        if g and not pd.isna(g) and g > 0 and not pd.isna(r["Position"]):
            moves.append({"driver": r["Driver"], "grid": int(g), "after_lap1": int(r["Position"]),
                          "gained": int(g - r["Position"])})
    return sorted(moves, key=lambda m: -abs(m["gained"]))


def race_history(year: int, laps: pd.DataFrame, results: pd.DataFrame) -> dict[str, Any]:
    """Compact story of a past race at this circuit."""
    cls = classification(results)
    strat = strategies(laps)
    neutral = neutralisations(laps)
    finishers = [r for r in cls if r["pos"] and str(r["status"] or "").startswith(("Finished", "+", "Lapped"))]
    stops = [len(strat.get(r["driver"], {}).get("pit_laps", [])) for r in finishers]
    top10 = [
        {
            "pos": r["pos"], "driver": r["driver"], "team": r["team"], "grid": r["grid"],
            "strategy": strat.get(r["driver"], {}).get("sequence"),
            "pit_laps": strat.get(r["driver"], {}).get("pit_laps"),
        }
        for r in cls[:10]
    ]
    return {
        "year": year,
        "winner": cls[0]["driver"] if cls else None,
        "winner_grid": cls[0]["grid"] if cls else None,
        "classified": len(finishers),
        "dnfs": [r["driver"] for r in cls if r not in finishers],
        "stops_distribution": {str(k): stops.count(k) for k in sorted(set(stops))},
        "safety_cars": neutral["SC"],
        "vscs": neutral["VSC"],
        "red_flags": neutral["RED"],
        "measured_pit_loss_s": measured_pit_loss(laps),
        "biggest_lap1_moves": lap_one_moves(laps, results)[:4],
        "top10": top10,
    }
