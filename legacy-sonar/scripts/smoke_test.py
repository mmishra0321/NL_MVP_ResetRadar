"""End-to-end smoke test for the Sonar MVP pipeline.

Runs three diverse intents through the full pipeline using the mock Spotify
client (so it works without Spotify credentials) and prints a compact
report. Exits non-zero on any hard failure.

Usage (from 02-mvp/):
    python -m scripts.smoke_test
    python -m scripts.smoke_test --real-spotify     # only if you've set creds
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.pipeline import generate_playlist                        # noqa: E402
from src.spotify.client import (                                  # noqa: E402
    MockSpotifyClient, get_spotify_client,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("smoke")


CASES: list[dict] = [
    {
        "label": "Spanish high-novelty workout",
        "text": "Energetic Spanish music for my morning run, similar vibe to Rosalia but no Rosalia, things I'm unlikely to know",
        "expect_languages": {"es"},
        "expect_novelty_min": 7,
        "expect_excludes": {"rosalia"},
    },
    {
        "label": "Instrumental study, low energy",
        "text": "Soft instrumental stuff for late-night study, nothing with lyrics, calm",
        "expect_languages": set(),
        "expect_activity": "study",
        "expect_max_energy_avg": 0.55,
    },
    {
        "label": "Hindi indie for driving, mixed novelty",
        "text": "Upbeat Hindi indie for a long drive, mix of new and familiar",
        "expect_languages": {"hi"},
    },
]


def _summarise(idx: int, case: dict, playlist) -> list[str]:
    issues: list[str] = []
    intent = playlist.intent
    tracks = playlist.tracks

    if not tracks:
        issues.append("0 tracks returned")
        return issues

    if "expect_languages" in case and case["expect_languages"]:
        if not (set(intent.languages) & case["expect_languages"]):
            issues.append(f"missing language(s): expected any of {case['expect_languages']}, got {intent.languages}")

    if "expect_novelty_min" in case and intent.novelty_level < case["expect_novelty_min"]:
        issues.append(f"novelty too low: {intent.novelty_level} < {case['expect_novelty_min']}")

    if "expect_excludes" in case:
        excl_lc = {a.lower() for a in intent.exclude_artists}
        for needle in case["expect_excludes"]:
            if not any(needle in e for e in excl_lc):
                issues.append(f"missing exclude: {needle!r} (got {sorted(excl_lc)})")
        # Also verify the playlist itself doesn't contain the excluded artist
        for t in tracks:
            for needle in case["expect_excludes"]:
                if needle in t.artist.lower():
                    issues.append(f"excluded artist leaked into playlist: {t.artist}")

    if "expect_activity" in case and intent.activity_context != case["expect_activity"]:
        issues.append(f"activity mismatch: expected {case['expect_activity']!r}, got {intent.activity_context!r}")

    if "expect_max_energy_avg" in case:
        energies = [t.audio_features.get("energy", 0.5) for t in tracks if t.audio_features]
        if energies:
            avg = sum(energies) / len(energies)
            if avg > case["expect_max_energy_avg"]:
                issues.append(f"avg energy {avg:.2f} > {case['expect_max_energy_avg']}")

    # Universal sanity checks
    if any(not t.explanation.strip() for t in tracks):
        issues.append("at least one track has an empty explanation")
    if len({t.track_id for t in tracks}) != len(tracks):
        issues.append("duplicate track IDs in playlist")

    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--real-spotify", action="store_true",
        help="Use live Spotify API (requires SPOTIFY_CLIENT_ID / SECRET).",
    )
    parser.add_argument(
        "--track-count", type=int, default=12,
        help="Tracks per playlist (kept small for the smoke test).",
    )
    args = parser.parse_args()

    sp = get_spotify_client() if args.real_spotify else MockSpotifyClient()
    log.info("Smoke test using Spotify client: %s (real=%s)", sp.name, sp.using_real_api)

    overall_issues: list[tuple[str, list[str]]] = []
    started = time.monotonic()

    for i, case in enumerate(CASES, start=1):
        print("\n" + "=" * 78)
        print(f"CASE {i}/{len(CASES)}: {case['label']}")
        print(f"INPUT: {case['text']}")
        print("=" * 78)

        try:
            playlist = generate_playlist(
                case["text"],
                track_count=args.track_count,
                spotify_client=sp,
            )
        except Exception as exc:                                    # noqa: BLE001
            log.exception("Case %d failed hard: %s", i, exc)
            overall_issues.append((case["label"], [f"hard exception: {exc}"]))
            continue

        # Print compact report
        intent = playlist.intent
        print(f"\n  parsed: mood={intent.mood} langs={intent.languages} "
              f"seeds={intent.seed_artists} excl={intent.exclude_artists} "
              f"novelty={intent.novelty_level} activity={intent.activity_context}")
        print(f"  plan:   endpoints={playlist.plan.endpoints} "
              f"queries={playlist.plan.search_queries}")
        print(f"  picks:  {len(playlist.tracks)} tracks in {playlist.elapsed_ms} ms")
        for j, t in enumerate(playlist.tracks[:5], start=1):
            print(f"    {j:02d}. [{t.score:.2f}] {t.title} - {t.artist} "
                  f"({t.language or '?'}, pop {t.popularity})")
            print(f"        why: {t.explanation}")
        if len(playlist.tracks) > 5:
            print(f"    ... +{len(playlist.tracks) - 5} more")

        issues = _summarise(i, case, playlist)
        if issues:
            print(f"\n  ISSUES ({len(issues)}):")
            for iss in issues:
                print(f"    - {iss}")
            overall_issues.append((case["label"], issues))
        else:
            print("\n  OK · no issues")

    elapsed = time.monotonic() - started
    print("\n" + "=" * 78)
    print(f"DONE in {elapsed:.1f}s · cases: {len(CASES)} · cases with issues: {len(overall_issues)}")
    if overall_issues:
        print("\nSummary of issues:")
        for label, issues in overall_issues:
            print(f"  - {label}: {len(issues)} issue(s)")
        return 1
    print("ALL GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
