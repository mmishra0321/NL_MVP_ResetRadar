"""Sanity-check detection.py against the synthetic fixture.

Run after generate_synthetic_weeks.py to verify that the math produces
the expected stuck-score trajectory + that both personas trigger at W26.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))                                # let `app.*` import

from app.detection import process_user_weeks, should_trigger_nudge   # noqa: E402

FIXTURE = ROOT / "mock_data" / "synthetic_weeks.json"


def main() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    weeks = fixture["weeks"]
    iso_weeks_sorted = sorted(weeks.keys())

    for user_id in ["demo-karthik-001", "demo-aanya-002"]:
        rows = []
        for iso_week in iso_weeks_sorted:
            snap = next(s for s in weeks[iso_week] if s["user_id"] == user_id)
            rows.append((iso_week, snap["tracks"]))

        result = process_user_weeks(user_id=user_id, weekly_track_rows=rows)
        print(f"=== {user_id} ===")
        print(
            f"  {'week':>8} {'genre':>6} {'lang':>6} {'era':>6} "
            f"{'mood':>6} {'overall':>8} {'sug.scope':>10}"
        )
        for s in result["scores"]:
            pd = s["per_dimension"]
            print(
                f"  {s['iso_week']:>8} "
                f"{pd.genre:>6.3f} {pd.language:>6.3f} "
                f"{pd.era:>6.3f} {pd.mood:>6.3f} "
                f"{s['overall']:>8.3f} {s['suggested_scope']:>10}"
            )

        # Diagnostic: dig into the focal dimension's components week-by-week
        focal = "language" if user_id == "demo-karthik-001" else "genre"
        print(f"\n  --- diagnostic for {focal} ---")
        print(
            f"  {'week':>8} {'n_ref':>5} {'mean_olp':>9} "
            f"{'mean_n_H':>9} {'1-n_H':>7} {'score':>6}"
        )
        for s in result["scores"]:
            c = s["components"][focal]
            no_sig = c.get("no_signal", False)
            print(
                f"  {s['iso_week']:>8} "
                f"{c.get('num_reference_buckets', 0):>5} "
                f"{c['mean_overlap']:>9.3f} "
                f"{c['mean_norm_entropy']:>9.3f} "
                f"{(1.0 - c['mean_norm_entropy']):>7.3f} "
                f"{getattr(s['per_dimension'], focal):>6.3f}"
                f"{' NO_SIGNAL' if no_sig else ''}"
            )

        decision = should_trigger_nudge(
            user_id=user_id,
            recent_scores=result["scores"],
            last_nudge_at=None,
            has_active_session=False,
        )
        print(f"  trigger: {decision}\n")


if __name__ == "__main__":
    main()
