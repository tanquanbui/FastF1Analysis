"""Simulation-relevant circuit facts.

These are anchors for the model, not ground truth: lap counts and lengths are
official, while pit loss, safety-car likelihood, overtaking difficulty and tyre
stress are typical values from recent seasons. When FastF1 is available the
event schedule comes from FastF1; the calendars here are the offline fallback.
"""
from __future__ import annotations

from typing import Any

# key -> facts. pit_loss_s is green-flag pit-lane time loss (entry to exit vs
# staying out). sc_probability is the chance of at least one SC/VSC per race.
CIRCUITS: dict[str, dict[str, Any]] = {
    "bahrain": dict(name="Bahrain International Circuit", country="Bahrain", laps=57, length_km=5.412,
                    pit_loss_s=23.0, overtaking="easy", sc_probability=0.4, tyre_stress="high",
                    compounds="C1/C2/C3", drs_zones=3,
                    notes="Abrasive surface, high rear deg; undercut is powerful. Night race, cooler track."),
    "jeddah": dict(name="Jeddah Corniche Circuit", country="Saudi Arabia", laps=50, length_km=6.174,
                   pit_loss_s=20.0, overtaking="medium", sc_probability=0.7, tyre_stress="low",
                   compounds="C2/C3/C4", drs_zones=3,
                   notes="Fast street circuit, walls punish mistakes; one-stop, SC often decides strategy."),
    "albert_park": dict(name="Albert Park", country="Australia", laps=58, length_km=5.278,
                        pit_loss_s=19.0, overtaking="medium", sc_probability=0.6, tyre_stress="medium",
                        compounds="C3/C4/C5", drs_zones=4,
                        notes="Semi-street circuit, low pit loss, frequent SC/red flags."),
    "suzuka": dict(name="Suzuka", country="Japan", laps=53, length_km=5.807,
                   pit_loss_s=22.0, overtaking="hard", sc_probability=0.3, tyre_stress="high",
                   compounds="C1/C2/C3", drs_zones=1,
                   notes="High-speed esses; high deg pushes two-stop; track position valuable."),
    "shanghai": dict(name="Shanghai International Circuit", country="China", laps=56, length_km=5.451,
                     pit_loss_s=23.0, overtaking="easy", sc_probability=0.4, tyre_stress="medium",
                     compounds="C2/C3/C4", drs_zones=2,
                     notes="Long back straight, front-left graining; long T1-T2 loads tyres."),
    "miami": dict(name="Miami International Autodrome", country="USA", laps=57, length_km=5.412,
                  pit_loss_s=19.0, overtaking="medium", sc_probability=0.5, tyre_stress="medium",
                  compounds="C2/C3/C4", drs_zones=3,
                  notes="Hot, low-grip surface; mostly one-stop."),
    "imola": dict(name="Autodromo Enzo e Dino Ferrari", country="Italy", laps=63, length_km=4.909,
                  pit_loss_s=28.0, overtaking="hard", sc_probability=0.4, tyre_stress="medium",
                  compounds="C3/C4/C5", drs_zones=1,
                  notes="Narrow, old-school; high pit loss favours one-stop and track position."),
    "monaco": dict(name="Circuit de Monaco", country="Monaco", laps=78, length_km=3.337,
                   pit_loss_s=20.0, overtaking="very hard", sc_probability=0.6, tyre_stress="low",
                   compounds="C3/C4/C5", drs_zones=1,
                   notes="Qualifying decides the race; overtaking almost impossible; SC/red flag pit windows matter."),
    "montreal": dict(name="Circuit Gilles Villeneuve", country="Canada", laps=70, length_km=4.361,
                     pit_loss_s=18.0, overtaking="easy", sc_probability=0.7, tyre_stress="medium",
                     compounds="C3/C4/C5", drs_zones=3,
                     notes="Stop-start, heavy braking, Wall of Champions; frequent SC and changeable weather."),
    "barcelona": dict(name="Circuit de Barcelona-Catalunya", country="Spain", laps=66, length_km=4.657,
                      pit_loss_s=22.0, overtaking="hard", sc_probability=0.3, tyre_stress="high",
                      compounds="C1/C2/C3", drs_zones=2,
                      notes="High-energy front-left; two/three-stop common."),
    "red_bull_ring": dict(name="Red Bull Ring", country="Austria", laps=71, length_km=4.318,
                          pit_loss_s=20.0, overtaking="easy", sc_probability=0.4, tyre_stress="medium",
                          compounds="C3/C4/C5", drs_zones=3,
                          notes="Short lap, track-limits penalties, multiple DRS trains."),
    "silverstone": dict(name="Silverstone", country="Great Britain", laps=52, length_km=5.891,
                        pit_loss_s=20.0, overtaking="medium", sc_probability=0.5, tyre_stress="high",
                        compounds="C1/C2/C3", drs_zones=2,
                        notes="High-speed lateral load; British weather can flip strategy to inters."),
    "hungaroring": dict(name="Hungaroring", country="Hungary", laps=70, length_km=4.381,
                        pit_loss_s=20.0, overtaking="hard", sc_probability=0.3, tyre_stress="medium",
                        compounds="C3/C4/C5", drs_zones=2,
                        notes="Twisty, hot; undercut strong; two-stop typical."),
    "spa": dict(name="Circuit de Spa-Francorchamps", country="Belgium", laps=44, length_km=7.004,
                pit_loss_s=19.0, overtaking="easy", sc_probability=0.4, tyre_stress="medium",
                compounds="C2/C3/C4", drs_zones=2,
                notes="Long lap, microclimate - rain on one part of the track only."),
    "zandvoort": dict(name="Circuit Zandvoort", country="Netherlands", laps=72, length_km=4.259,
                      pit_loss_s=21.0, overtaking="hard", sc_probability=0.4, tyre_stress="high",
                      compounds="C1/C2/C3", drs_zones=2,
                      notes="Banked corners, narrow; coastal showers."),
    "monza": dict(name="Autodromo Nazionale Monza", country="Italy", laps=53, length_km=5.793,
                  pit_loss_s=24.0, overtaking="easy", sc_probability=0.4, tyre_stress="low",
                  compounds="C3/C4/C5", drs_zones=2,
                  notes="Low downforce, slipstream battles; one-stop."),
    "baku": dict(name="Baku City Circuit", country="Azerbaijan", laps=51, length_km=6.003,
                 pit_loss_s=20.0, overtaking="easy", sc_probability=0.7, tyre_stress="low",
                 compounds="C3/C4/C5", drs_zones=2,
                 notes="2.2km flat-out run; walls bring SCs; one-stop."),
    "marina_bay": dict(name="Marina Bay Street Circuit", country="Singapore", laps=62, length_km=4.940,
                       pit_loss_s=28.0, overtaking="hard", sc_probability=0.9, tyre_stress="medium",
                       compounds="C3/C4/C5", drs_zones=4,
                       notes="Humid night race, near-certain SC, huge pit loss so SC timing is everything."),
    "cota": dict(name="Circuit of the Americas", country="USA", laps=56, length_km=5.513,
                 pit_loss_s=21.0, overtaking="easy", sc_probability=0.4, tyre_stress="high",
                 compounds="C2/C3/C4", drs_zones=2,
                 notes="Bumpy, high deg; one or two stops."),
    "mexico": dict(name="Autodromo Hermanos Rodriguez", country="Mexico", laps=71, length_km=4.304,
                   pit_loss_s=22.0, overtaking="medium", sc_probability=0.5, tyre_stress="low",
                   compounds="C3/C4/C5", drs_zones=3,
                   notes="Altitude: thin air, low drag, cooling-limited; long run to T1."),
    "interlagos": dict(name="Autodromo Jose Carlos Pace", country="Brazil", laps=71, length_km=4.309,
                       pit_loss_s=21.0, overtaking="easy", sc_probability=0.6, tyre_stress="medium",
                       compounds="C2/C3/C4", drs_zones=2,
                       notes="Anti-clockwise, sudden rain, frequent SC."),
    "las_vegas": dict(name="Las Vegas Strip Circuit", country="USA", laps=50, length_km=6.201,
                      pit_loss_s=20.0, overtaking="easy", sc_probability=0.4, tyre_stress="low",
                      compounds="C3/C4/C5", drs_zones=2,
                      notes="Very cold night race; graining and warm-up issues, long straights."),
    "lusail": dict(name="Lusail International Circuit", country="Qatar", laps=57, length_km=5.419,
                   pit_loss_s=25.0, overtaking="medium", sc_probability=0.3, tyre_stress="very high",
                   compounds="C1/C2/C3", drs_zones=1,
                   notes="Sustained high-speed corners; mandatory stint limits have been imposed before."),
    "yas_marina": dict(name="Yas Marina Circuit", country="Abu Dhabi", laps=58, length_km=5.281,
                       pit_loss_s=22.0, overtaking="medium", sc_probability=0.3, tyre_stress="low",
                       compounds="C3/C4/C5", drs_zones=2,
                       notes="Twilight race, one-stop typical."),
    # Older venues (2018-2023 seasons)
    "paul_ricard": dict(name="Circuit Paul Ricard", country="France", laps=53, length_km=5.842,
                        pit_loss_s=24.0, overtaking="medium", sc_probability=0.3, tyre_stress="medium",
                        compounds="C2/C3/C4", drs_zones=2, notes="Long Mistral straight with chicane; one-stop."),
    "sochi": dict(name="Sochi Autodrom", country="Russia", laps=53, length_km=5.848,
                  pit_loss_s=26.0, overtaking="medium", sc_probability=0.4, tyre_stress="low",
                  compounds="C3/C4/C5", drs_zones=2, notes="Low deg, long run to T2; one-stop."),
    "hockenheim": dict(name="Hockenheimring", country="Germany", laps=67, length_km=4.574,
                       pit_loss_s=20.0, overtaking="easy", sc_probability=0.5, tyre_stress="medium",
                       compounds="C2/C3/C4", drs_zones=3, notes="Hairpin overtaking spot; changeable weather."),
    "portimao": dict(name="Algarve International Circuit", country="Portugal", laps=66, length_km=4.653,
                     pit_loss_s=22.0, overtaking="medium", sc_probability=0.3, tyre_stress="medium",
                     compounds="C1/C2/C3", drs_zones=1, notes="Undulating, low grip early; one-stop."),
    "mugello": dict(name="Mugello Circuit", country="Italy", laps=59, length_km=5.245,
                    pit_loss_s=26.0, overtaking="hard", sc_probability=0.6, tyre_stress="high",
                    compounds="C1/C2/C3", drs_zones=1, notes="Fast, flowing; restart crashes in 2020."),
    "istanbul": dict(name="Istanbul Park", country="Turkey", laps=58, length_km=5.338,
                     pit_loss_s=22.0, overtaking="medium", sc_probability=0.4, tyre_stress="medium",
                     compounds="C2/C3/C4", drs_zones=2, notes="Turn 8 multi-apex; low grip when resurfaced."),
    "nurburgring": dict(name="Nurburgring GP-Strecke", country="Germany", laps=60, length_km=5.148,
                        pit_loss_s=21.0, overtaking="medium", sc_probability=0.4, tyre_stress="medium",
                        compounds="C2/C3/C4", drs_zones=2, notes="Cold autumn race in 2020."),
    "madring": dict(name="Madring", country="Spain", laps=57, length_km=5.47,
                    pit_loss_s=22.0, overtaking="medium", sc_probability=0.5, tyre_stress="medium",
                    compounds="C3/C4/C5", drs_zones=2,
                    notes="New semi-street venue in Madrid from 2026; values are estimates."),
}

_CAL_2024 = ["bahrain", "jeddah", "albert_park", "suzuka", "shanghai", "miami", "imola", "monaco",
             "montreal", "barcelona", "red_bull_ring", "silverstone", "hungaroring", "spa", "zandvoort",
             "monza", "baku", "marina_bay", "cota", "mexico", "interlagos", "las_vegas", "lusail", "yas_marina"]
_CAL_2025 = ["albert_park", "shanghai", "suzuka", "bahrain", "jeddah", "miami", "imola", "monaco",
             "barcelona", "montreal", "red_bull_ring", "silverstone", "spa", "hungaroring", "zandvoort",
             "monza", "baku", "marina_bay", "cota", "mexico", "interlagos", "las_vegas", "lusail", "yas_marina"]
_CAL_2026 = ["albert_park", "shanghai", "suzuka", "bahrain", "jeddah", "miami", "montreal", "monaco",
             "barcelona", "red_bull_ring", "silverstone", "spa", "hungaroring", "zandvoort", "monza",
             "madring", "baku", "marina_bay", "cota", "mexico", "interlagos", "las_vegas", "lusail", "yas_marina"]

CALENDARS: dict[int, list[str]] = {2024: _CAL_2024, 2025: _CAL_2025, 2026: _CAL_2026}

GRAND_PRIX_NAMES: dict[str, str] = {
    "paul_ricard": "French Grand Prix",
    "sochi": "Russian Grand Prix",
    "hockenheim": "German Grand Prix",
    "portimao": "Portuguese Grand Prix",
    "mugello": "Tuscan Grand Prix",
    "istanbul": "Turkish Grand Prix",
    "nurburgring": "Eifel Grand Prix",
    "bahrain": "Bahrain Grand Prix",
    "jeddah": "Saudi Arabian Grand Prix",
    "albert_park": "Australian Grand Prix",
    "suzuka": "Japanese Grand Prix",
    "shanghai": "Chinese Grand Prix",
    "miami": "Miami Grand Prix",
    "imola": "Emilia-Romagna Grand Prix",
    "monaco": "Monaco Grand Prix",
    "montreal": "Canadian Grand Prix",
    "barcelona": "Spanish Grand Prix",
    "red_bull_ring": "Austrian Grand Prix",
    "silverstone": "British Grand Prix",
    "hungaroring": "Hungarian Grand Prix",
    "spa": "Belgian Grand Prix",
    "zandvoort": "Dutch Grand Prix",
    "monza": "Italian Grand Prix",
    "baku": "Azerbaijan Grand Prix",
    "marina_bay": "Singapore Grand Prix",
    "cota": "United States Grand Prix",
    "mexico": "Mexico City Grand Prix",
    "interlagos": "São Paulo Grand Prix",
    "las_vegas": "Las Vegas Grand Prix",
    "lusail": "Qatar Grand Prix",
    "yas_marina": "Abu Dhabi Grand Prix",
    "madring": "Spanish Grand Prix",
}

# FastF1 "Location" values -> our keys, for mapping live schedules.
_LOCATION_ALIASES = {
    "sakhir": "bahrain", "jeddah": "jeddah", "melbourne": "albert_park", "suzuka": "suzuka",
    "shanghai": "shanghai", "miami": "miami", "imola": "imola", "monaco": "monaco", "monte carlo": "monaco",
    "montréal": "montreal", "montreal": "montreal", "barcelona": "barcelona", "spielberg": "red_bull_ring",
    "silverstone": "silverstone", "budapest": "hungaroring", "spa-francorchamps": "spa", "spa": "spa",
    "zandvoort": "zandvoort", "monza": "monza", "baku": "baku", "marina bay": "marina_bay",
    "singapore": "marina_bay", "austin": "cota", "mexico city": "mexico", "são paulo": "interlagos",
    "sao paulo": "interlagos", "las vegas": "las_vegas", "lusail": "lusail", "yas island": "yas_marina",
    "yas marina": "yas_marina", "abu dhabi": "yas_marina", "madrid": "madring",
    "le castellet": "paul_ricard", "sochi": "sochi", "hockenheim": "hockenheim", "portimão": "portimao",
    "portimao": "portimao", "mugello": "mugello", "istanbul": "istanbul", "nürburgring": "nurburgring",
    "nurburgring": "nurburgring", "spa francorchamps": "spa", "mexico": "mexico",
}


def circuit_key_for_location(location: str) -> str | None:
    return _LOCATION_ALIASES.get((location or "").strip().lower())


def event_name(key: str) -> str:
    return GRAND_PRIX_NAMES.get(key, f"{CIRCUITS[key]['country']} Grand Prix")


def circuit_for_round(year: int, round_number: int) -> str | None:
    calendar = CALENDARS.get(year)
    if not calendar or not 1 <= round_number <= len(calendar):
        return None
    return calendar[round_number - 1]


def list_calendar(year: int) -> list[dict[str, Any]]:
    """Offline calendar for the race picker: round, key, display name."""
    return [
        {
            "round": i + 1,
            "circuit_key": key,
            "event_name": event_name(key),
            "circuit": CIRCUITS[key]["name"],
            "country": CIRCUITS[key]["country"],
        }
        for i, key in enumerate(CALENDARS.get(year, []))
    ]
