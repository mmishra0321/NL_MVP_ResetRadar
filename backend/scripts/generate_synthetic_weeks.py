"""Generate `mock_data/synthetic_weeks.json` for the Reset Radar demo.

Run once after R0 scaffold completes:
    cd 02-mvp/backend
    python scripts/generate_synthetic_weeks.py

The fixture models 8 ISO weeks (2026-W19 through 2026-W26) for two
synthetic users. Listening trajectories are designed so:

- **demo-karthik-001** (multilingual, English-Telugu-Hindi): language
  diversity collapses progressively. By W26 the language axis stuck
  score crosses STUCK_THRESHOLD=0.6 -> nudge fires with
  `suggested_scope="language"`.

- **demo-aanya-002** (English-only indie): genre diversity collapses
  progressively from a 5-subgenre mix into mostly dream-pop. By W26 the
  genre axis stuck score crosses STUCK_THRESHOLD=0.6 -> nudge fires
  with `suggested_scope="genre"`.

The script is deterministic (fixed `random.seed`) so re-runs produce
identical output. The output JSON is what ships - the script exists for
review + tweakability, not as runtime code.
"""
from __future__ import annotations

import json
import random
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# Make the script importable as part of the backend package without
# changing sys.path manipulation - this is a dev utility, not runtime.
ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "mock_data" / "synthetic_weeks.json"

SEED = 20260626                                                  # deterministic
TRACKS_PER_WEEK = 28                                              # ~4 per day, low sampling variance
ISO_WEEKS = [f"2026-W{w:02d}" for w in range(19, 27)]            # W19..W26 inclusive


# ============================================================
# Track catalogues per persona
# Each catalogue entry is a single track with all detection metadata
# pre-populated. The fixture mirrors what `spotify_client.fetch_recent_snapshot`
# would return in real mode (after LLM language/mood classification).
# ============================================================

KARTHIK_CATALOG: dict[str, list[dict[str, Any]]] = {
    # Bucket: language code. Each bucket has multiple tracks the user
    # genuinely listens to. The week-by-week mix shifts the *play counts*,
    # not the catalogue.
    "te": [
        {"title": "Vachindamma", "artist": "Sid Sriram", "genres": ["telugu-film-pop"], "era": "2010s", "mood": "melancholy"},
        {"title": "Manasanamaha", "artist": "Sid Sriram", "genres": ["telugu-film-pop"], "era": "2010s", "mood": "melancholy"},
        {"title": "Inkem Inkem", "artist": "Sid Sriram", "genres": ["telugu-film-pop"], "era": "2010s", "mood": "nostalgic"},
        {"title": "Samajavaragamana", "artist": "Sid Sriram", "genres": ["telugu-film-pop"], "era": "2010s", "mood": "nostalgic"},
        {"title": "Sahana", "artist": "Karthik Sivasankar", "genres": ["carnatic", "classical-indian"], "era": "2020s", "mood": "focus"},
        {"title": "Bhairavi raga alap", "artist": "M.S. Subbulakshmi", "genres": ["carnatic", "classical-indian"], "era": "1990s", "mood": "focus"},
        {"title": "Vatapi Ganapatim", "artist": "M.S. Subbulakshmi", "genres": ["carnatic", "classical-indian"], "era": "1990s", "mood": "focus"},
        {"title": "Endaro Mahanubhavulu", "artist": "T.M. Krishna", "genres": ["carnatic", "classical-indian"], "era": "2010s", "mood": "focus"},
        {"title": "Aatma Raama", "artist": "Sanjay Subrahmanyan", "genres": ["carnatic", "classical-indian"], "era": "2010s", "mood": "focus"},
        {"title": "Butta Bomma", "artist": "Armaan Malik", "genres": ["telugu-film-pop"], "era": "2020s", "mood": "energetic"},
        {"title": "Oo Antava", "artist": "Indravathi Chauhan", "genres": ["telugu-film-pop"], "era": "2020s", "mood": "energetic"},
        {"title": "Saami Saami", "artist": "Mounika Yadav", "genres": ["telugu-film-pop"], "era": "2020s", "mood": "energetic"},
    ],
    "en": [
        {"title": "Mr. Brightside", "artist": "The Killers", "genres": ["alt-rock", "indie-rock"], "era": "2000s", "mood": "energetic"},
        {"title": "Pumped Up Kicks", "artist": "Foster the People", "genres": ["indie-pop", "alt-rock"], "era": "2010s", "mood": "chill"},
        {"title": "Float On", "artist": "Modest Mouse", "genres": ["indie-rock", "alt-rock"], "era": "2000s", "mood": "energetic"},
        {"title": "The Night We Met", "artist": "Lord Huron", "genres": ["indie-folk", "alt-rock"], "era": "2010s", "mood": "melancholy"},
        {"title": "Ho Hey", "artist": "The Lumineers", "genres": ["indie-folk", "folk-rock"], "era": "2010s", "mood": "energetic"},
        {"title": "Skinny Love", "artist": "Bon Iver", "genres": ["indie-folk"], "era": "2000s", "mood": "melancholy"},
        {"title": "Holocene", "artist": "Bon Iver", "genres": ["indie-folk"], "era": "2010s", "mood": "melancholy"},
        {"title": "Re: Stacks", "artist": "Bon Iver", "genres": ["indie-folk"], "era": "2000s", "mood": "melancholy"},
    ],
    "hi": [
        {"title": "Tum Hi Ho", "artist": "Arijit Singh", "genres": ["hindi-film-pop"], "era": "2010s", "mood": "melancholy"},
        {"title": "Channa Mereya", "artist": "Arijit Singh", "genres": ["hindi-film-pop"], "era": "2010s", "mood": "melancholy"},
        {"title": "Kesariya", "artist": "Arijit Singh", "genres": ["hindi-film-pop"], "era": "2020s", "mood": "nostalgic"},
    ],
}


AANYA_CATALOG: dict[str, list[dict[str, Any]]] = {
    # All tracks are English. Buckets here are *genre tags*.
    "dream-pop": [
        {"title": "Space Song", "artist": "Beach House", "language": "en", "era": "2010s", "mood": "chill"},
        {"title": "Myth", "artist": "Beach House", "language": "en", "era": "2010s", "mood": "chill"},
        {"title": "Norway", "artist": "Beach House", "language": "en", "era": "2010s", "mood": "chill"},
        {"title": "Levitation", "artist": "Beach House", "language": "en", "era": "2010s", "mood": "chill"},
        {"title": "Fade Into You", "artist": "Mazzy Star", "language": "en", "era": "1990s", "mood": "melancholy"},
        {"title": "Cherry-coloured Funk", "artist": "Cocteau Twins", "language": "en", "era": "1990s", "mood": "chill"},
        {"title": "Heaven Or Las Vegas", "artist": "Cocteau Twins", "language": "en", "era": "1990s", "mood": "chill"},
        {"title": "Pink Rabbits", "artist": "The National", "language": "en", "era": "2010s", "mood": "melancholy"},
        {"title": "Sometimes Always", "artist": "The Jesus and Mary Chain", "language": "en", "era": "1990s", "mood": "chill"},
    ],
    "shoegaze": [
        {"title": "Sometimes", "artist": "My Bloody Valentine", "language": "en", "era": "1990s", "mood": "melancholy"},
        {"title": "Only Shallow", "artist": "My Bloody Valentine", "language": "en", "era": "1990s", "mood": "energetic"},
        {"title": "Vapour Trail", "artist": "Ride", "language": "en", "era": "1990s", "mood": "melancholy"},
        {"title": "Souvlaki Space Station", "artist": "Slowdive", "language": "en", "era": "1990s", "mood": "chill"},
        {"title": "Star Roving", "artist": "Slowdive", "language": "en", "era": "2010s", "mood": "energetic"},
    ],
    "indie-pop": [
        {"title": "Archie, Marry Me", "artist": "Alvvays", "language": "en", "era": "2010s", "mood": "energetic"},
        {"title": "Belinda Says", "artist": "Alvvays", "language": "en", "era": "2020s", "mood": "energetic"},
        {"title": "Green Eyes", "artist": "Lucy Dacus", "language": "en", "era": "2010s", "mood": "melancholy"},
        {"title": "Solitude", "artist": "Lucy Dacus", "language": "en", "era": "2020s", "mood": "melancholy"},
        {"title": "Liability", "artist": "Lorde", "language": "en", "era": "2010s", "mood": "melancholy"},
    ],
    "post-punk": [
        {"title": "Love Will Tear Us Apart", "artist": "Joy Division", "language": "en", "era": "1970s", "mood": "melancholy"},
        {"title": "Atmosphere", "artist": "Joy Division", "language": "en", "era": "1980s", "mood": "melancholy"},
        {"title": "Obstacle 1", "artist": "Interpol", "language": "en", "era": "2000s", "mood": "energetic"},
        {"title": "Evil", "artist": "Interpol", "language": "en", "era": "2000s", "mood": "energetic"},
        {"title": "Munich", "artist": "Editors", "language": "en", "era": "2000s", "mood": "energetic"},
    ],
    "alt-rock": [
        {"title": "Mr. Brightside", "artist": "The Killers", "language": "en", "era": "2000s", "mood": "energetic"},
        {"title": "Take Me Out", "artist": "Franz Ferdinand", "language": "en", "era": "2000s", "mood": "energetic"},
        {"title": "Last Nite", "artist": "The Strokes", "language": "en", "era": "2000s", "mood": "energetic"},
        {"title": "Reptilia", "artist": "The Strokes", "language": "en", "era": "2000s", "mood": "energetic"},
        {"title": "Maps", "artist": "Yeah Yeah Yeahs", "language": "en", "era": "2000s", "mood": "melancholy"},
    ],
}


# ============================================================
# Per-week mix weights - the driver of the stuck story
# Each row is (weight_per_bucket_at_week_N). Values do not need to
# sum to 1 - the sampler normalises before drawing.
# ============================================================

# Karthik: balanced -> very-strong Telugu collapse on the language axis.
# Designed so the stuck_score crosses 0.6 by W23 and stays above for
# W23-W26 (4-week streak) by W26.
# Week:           W19   W20   W21   W22   W23   W24   W25   W26
KARTHIK_WEIGHTS = {
    "en": [0.35, 0.30, 0.22, 0.12, 0.06, 0.03, 0.02, 0.01],
    "te": [0.35, 0.50, 0.70, 0.84, 0.92, 0.96, 0.98, 0.99],
    "hi": [0.30, 0.20, 0.08, 0.04, 0.02, 0.01, 0.00, 0.00],
}

# Aanya: even 5-genre mix -> very-strong dream-pop collapse on the genre
# axis. Same design target as Karthik: cross 0.6 by W23, 4-week streak
# through W26.
# Week:            W19   W20   W21   W22   W23   W24   W25   W26
AANYA_WEIGHTS = {
    "dream-pop":  [0.20, 0.32, 0.50, 0.70, 0.85, 0.92, 0.96, 0.98],
    "shoegaze":   [0.20, 0.18, 0.13, 0.08, 0.05, 0.03, 0.02, 0.01],
    "indie-pop":  [0.20, 0.18, 0.14, 0.10, 0.05, 0.03, 0.01, 0.01],
    "post-punk":  [0.20, 0.18, 0.13, 0.07, 0.03, 0.01, 0.01, 0.00],
    "alt-rock":   [0.20, 0.14, 0.10, 0.05, 0.02, 0.01, 0.00, 0.00],
}


# ============================================================
# Sampling helpers
# ============================================================

def _normalise(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("All-zero weights")
    return {k: v / total for k, v in weights.items()}


def _weighted_picks(
    catalog: dict[str, list[dict[str, Any]]],
    bucket_weights: dict[str, float],
    n: int,
    rng: random.Random,
) -> list[dict[str, Any]]:
    """Pick `n` tracks from `catalog`, weighted by bucket then uniform within."""
    norm = _normalise(bucket_weights)
    buckets = list(norm.keys())
    probs = [norm[b] for b in buckets]
    picks: list[dict[str, Any]] = []
    for _ in range(n):
        bucket = rng.choices(buckets, weights=probs, k=1)[0]
        track = rng.choice(catalog[bucket])
        picks.append({**track, "_bucket": bucket})
    return picks


def _track_to_record(
    track: dict[str, Any],
    user_id: str,
    week_idx: int,
    track_idx: int,
    bucket_field: str,
) -> dict[str, Any]:
    """Convert a sampled track into the wire-shape used by the detection job."""
    record: dict[str, Any] = {
        "spotify_track_id": f"mock-{user_id}-w{week_idx:02d}-t{track_idx:03d}",
        "title": track["title"],
        "artist": track["artist"],
        "genres": list(track.get("genres", [])),
        "language": track.get("language"),
        "era": track.get("era"),
        "mood": track.get("mood"),
        "play_count": 1,
    }
    # The "bucket" key carried over from sampling tells us where this track
    # was placed in the language (Karthik) or genre (Aanya) mix.
    bucket = track.get("_bucket")
    if bucket_field == "language" and bucket is not None:
        record["language"] = bucket
    elif bucket_field == "genre" and bucket is not None:
        # Anchor the primary genre for the genre axis. Keep additional genres
        # in the `genres` list for downstream consumers that want richer signal.
        if bucket not in record["genres"]:
            record["genres"] = [bucket] + record["genres"]
    return record


def _aggregate_play_counts(records: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Collapse identical (title, artist) entries by summing play_count.

    Models real Spotify behaviour where the same track gets played multiple
    times during a week. Aggregation keeps the JSON compact.
    """
    keyed: dict[tuple[str, str], dict[str, Any]] = {}
    for r in records:
        key = (r["title"], r["artist"])
        if key in keyed:
            keyed[key]["play_count"] += r["play_count"]
        else:
            keyed[key] = dict(r)
    return list(keyed.values())


# ============================================================
# Per-user generator
# ============================================================

def _build_user_weeks(
    *,
    user_id: str,
    catalog: dict[str, list[dict[str, Any]]],
    week_weights: dict[str, list[float]],
    bucket_field: str,
    rng: random.Random,
) -> dict[str, dict[str, Any]]:
    """Build {iso_week: snapshot} for one user across all weeks."""
    out: dict[str, dict[str, Any]] = {}
    for week_idx, iso_week in enumerate(ISO_WEEKS):
        bucket_weights = {b: ws[week_idx] for b, ws in week_weights.items()}
        picks = _weighted_picks(catalog, bucket_weights, TRACKS_PER_WEEK, rng)
        raw_records = [
            _track_to_record(t, user_id, week_idx + 19, t_idx, bucket_field)
            for t_idx, t in enumerate(picks)
        ]
        agg = _aggregate_play_counts(raw_records)
        out[iso_week] = {
            "iso_week": iso_week,
            "user_id": user_id,
            "tracks": agg,
        }
    return out


# ============================================================
# Top-level driver
# ============================================================

def build_synthetic_weeks() -> dict[str, dict[str, Any]]:
    """Produce the full {iso_week: snapshot} mapping for both personas.

    Both personas share the iso_week key namespace - the snapshot dict
    contains `user_id` so the detection job can disambiguate.
    """
    rng = random.Random(SEED)

    karthik = _build_user_weeks(
        user_id="demo-karthik-001",
        catalog=KARTHIK_CATALOG,
        week_weights=KARTHIK_WEIGHTS,
        bucket_field="language",
        rng=rng,
    )
    aanya = _build_user_weeks(
        user_id="demo-aanya-002",
        catalog=AANYA_CATALOG,
        week_weights=AANYA_WEIGHTS,
        bucket_field="genre",
        rng=rng,
    )

    # The fixture is a dict whose values are LISTS of snapshots
    # because two users share each iso_week.
    out: dict[str, list[dict[str, Any]]] = {}
    for iso_week in ISO_WEEKS:
        out[iso_week] = [karthik[iso_week], aanya[iso_week]]
    return out


def write_fixture() -> Path:
    payload = {
        "_schema_version": 1,
        "_generated_by": "scripts/generate_synthetic_weeks.py",
        "_personas": {
            "demo-karthik-001": {
                "display_name": "Karthik (demo · multilingual)",
                "stuck_axis": "language",
                "trajectory_summary": "balanced en/te/hi -> 91% Telugu by W26",
            },
            "demo-aanya-002": {
                "display_name": "Aanya (demo · English indie)",
                "stuck_axis": "genre",
                "trajectory_summary": "5-subgenre mix -> 85% dream-pop by W26",
            },
        },
        "weeks": build_synthetic_weeks(),
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return OUT_FILE


def main() -> None:
    path = write_fixture()
    print(f"wrote: {path}")
    print(f"size:  {path.stat().st_size:,} bytes")
    print(f"weeks: {len(ISO_WEEKS)}")
    print(f"users: 2 (demo-karthik-001, demo-aanya-002)")


if __name__ == "__main__":
    main()
