"""Generate `mock_data/mock_candidates.json` for the Reset Radar demo.

Run once:
    cd 02-mvp/backend
    python scripts/generate_mock_candidates.py

The fixture models what `GET /search` would return in real mode after
the reset_engine builds field-filter queries from the chosen scope.

Each candidate is a real-ish track (artist, title, language, era, mood,
genre tags) chosen to:

- be a plausible discovery for the persona whose stuck axis is THIS
  scope dimension (i.e. carnatic-jazz fusion appears under both
  `language` and `genre` candidates as a bridge from Karthik's Telugu
  taste into something new without being jarring)
- give the LLM enough variety (60 per scope) that ranking is non-trivial
- avoid IDs the LLM might hallucinate from training data: every
  spotify_track_id is `mock-<scope>-<idx>` so the validation guard in
  reset_engine.py has an unambiguous source-of-truth set

60 per scope * 4 scopes = 240 candidates total. JSON output ~70 KB.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT / "mock_data" / "mock_candidates.json"

SEED = 20260626
CANDIDATES_PER_SCOPE = 60


# ============================================================
# Candidate pools per scope dimension
#
# Each scope's pool is a list of (title, artist, genres, language, era, mood)
# tuples. The generator pads to CANDIDATES_PER_SCOPE by sampling with
# replacement and applying small perturbations to the metadata so the LLM
# sees variety. Real-mode candidate generation uses /search with field
# filters and gets pagination of 6-8 x 10 results (per architecture.md
# section 6); these mock pools mimic the post-deduplication shape.
# ============================================================

GENRE_POOL: list[dict[str, Any]] = [
    # New genres for someone stuck in dream-pop: jazz, classical, neo-soul, ambient, electronic
    {"title": "So What",                "artist": "Miles Davis",            "genres": ["modal-jazz", "jazz"],            "language": "en", "era": "1950s", "mood": "chill"},
    {"title": "Blue in Green",          "artist": "Miles Davis",            "genres": ["modal-jazz", "jazz"],            "language": "en", "era": "1950s", "mood": "melancholy"},
    {"title": "Take Five",              "artist": "Dave Brubeck Quartet",   "genres": ["cool-jazz", "jazz"],             "language": "en", "era": "1950s", "mood": "chill"},
    {"title": "Sketches of Spain",      "artist": "Miles Davis",            "genres": ["latin-jazz", "jazz"],            "language": "en", "era": "1960s", "mood": "nostalgic"},
    {"title": "Naima",                  "artist": "John Coltrane",          "genres": ["modal-jazz", "jazz"],            "language": "en", "era": "1950s", "mood": "melancholy"},
    {"title": "Cantaloupe Island",      "artist": "Herbie Hancock",         "genres": ["jazz-funk", "jazz"],             "language": "en", "era": "1960s", "mood": "energetic"},
    {"title": "Black Orpheus",          "artist": "Vince Guaraldi Trio",    "genres": ["bossa-nova", "jazz"],            "language": "en", "era": "1960s", "mood": "chill"},
    {"title": "Round Midnight",         "artist": "Thelonious Monk",        "genres": ["bebop", "jazz"],                 "language": "en", "era": "1940s", "mood": "melancholy"},
    {"title": "On Green Dolphin Street","artist": "Bill Evans Trio",        "genres": ["cool-jazz", "jazz"],             "language": "en", "era": "1960s", "mood": "chill"},
    {"title": "Acknowledgement",        "artist": "John Coltrane",          "genres": ["spiritual-jazz", "jazz"],        "language": "en", "era": "1960s", "mood": "focus"},

    {"title": "Spiegel im Spiegel",     "artist": "Arvo Part",              "genres": ["minimalism", "classical"],       "language": "instrumental", "era": "1970s", "mood": "focus"},
    {"title": "Glassworks",             "artist": "Philip Glass",           "genres": ["minimalism", "classical"],       "language": "instrumental", "era": "1980s", "mood": "focus"},
    {"title": "Metamorphosis Two",      "artist": "Philip Glass",           "genres": ["minimalism", "classical"],       "language": "instrumental", "era": "1980s", "mood": "melancholy"},
    {"title": "Gymnopedie No. 1",       "artist": "Erik Satie",             "genres": ["impressionism", "classical"],    "language": "instrumental", "era": "1890s", "mood": "melancholy"},
    {"title": "Clair de Lune",          "artist": "Claude Debussy",         "genres": ["impressionism", "classical"],    "language": "instrumental", "era": "1890s", "mood": "chill"},
    {"title": "Stir of Echoes",         "artist": "Olafur Arnalds",         "genres": ["neo-classical", "ambient"],      "language": "instrumental", "era": "2010s", "mood": "focus"},
    {"title": "Saman",                  "artist": "Olafur Arnalds",         "genres": ["neo-classical"],                 "language": "instrumental", "era": "2010s", "mood": "melancholy"},
    {"title": "Avril 14th",             "artist": "Aphex Twin",             "genres": ["electronic", "ambient"],         "language": "instrumental", "era": "2000s", "mood": "chill"},
    {"title": "Selected Ambient Works", "artist": "Aphex Twin",             "genres": ["ambient", "electronic"],         "language": "instrumental", "era": "1990s", "mood": "focus"},
    {"title": "An Ending (Ascent)",     "artist": "Brian Eno",              "genres": ["ambient", "electronic"],         "language": "instrumental", "era": "1980s", "mood": "chill"},

    {"title": "Cranes in the Sky",      "artist": "Solange",                "genres": ["neo-soul", "r&b"],               "language": "en", "era": "2010s", "mood": "melancholy"},
    {"title": "Pyramid Schemes",        "artist": "Solange",                "genres": ["neo-soul", "r&b"],               "language": "en", "era": "2010s", "mood": "chill"},
    {"title": "Sandcastles",            "artist": "Beyonce",                "genres": ["neo-soul", "r&b"],               "language": "en", "era": "2010s", "mood": "melancholy"},
    {"title": "The Way",                "artist": "Daniel Caesar",          "genres": ["neo-soul", "r&b"],               "language": "en", "era": "2010s", "mood": "chill"},
    {"title": "Blessed",                "artist": "Daniel Caesar",          "genres": ["neo-soul", "r&b"],               "language": "en", "era": "2010s", "mood": "chill"},
    {"title": "Best Part",              "artist": "Daniel Caesar",          "genres": ["neo-soul"],                      "language": "en", "era": "2010s", "mood": "chill"},
    {"title": "Doomed",                 "artist": "Moses Sumney",           "genres": ["art-pop", "neo-soul"],           "language": "en", "era": "2010s", "mood": "melancholy"},
    {"title": "Plastic",                "artist": "Moses Sumney",           "genres": ["art-pop"],                       "language": "en", "era": "2010s", "mood": "melancholy"},

    {"title": "Brazil",                 "artist": "Antonio Carlos Jobim",   "genres": ["bossa-nova", "samba"],           "language": "pt", "era": "1960s", "mood": "energetic"},
    {"title": "Garota de Ipanema",      "artist": "Joao Gilberto",          "genres": ["bossa-nova"],                    "language": "pt", "era": "1960s", "mood": "chill"},
    {"title": "Aguas de Marco",         "artist": "Elis Regina",            "genres": ["bossa-nova"],                    "language": "pt", "era": "1970s", "mood": "chill"},

    {"title": "Strobe",                 "artist": "Deadmau5",               "genres": ["progressive-house", "electronic"],"language": "en", "era": "2010s", "mood": "focus"},
    {"title": "Resonance",              "artist": "HOME",                   "genres": ["synthwave", "electronic"],       "language": "en", "era": "2010s", "mood": "nostalgic"},
    {"title": "Reflections",            "artist": "MisterWives",            "genres": ["indie-pop", "synth-pop"],        "language": "en", "era": "2010s", "mood": "energetic"},
]

LANGUAGE_POOL: list[dict[str, Any]] = [
    # New languages for someone stuck on Telugu: Tamil, Malayalam, Hindi, Spanish, French, Korean, Portuguese
    {"title": "Munbe Vaa",              "artist": "Naresh Iyer",            "genres": ["tamil-film-pop"],                "language": "ta", "era": "2000s", "mood": "melancholy"},
    {"title": "Vaseegara",              "artist": "Bombay Jayashri",        "genres": ["tamil-film-pop"],                "language": "ta", "era": "2000s", "mood": "melancholy"},
    {"title": "Theera Ula",             "artist": "A.R. Rahman",            "genres": ["tamil-film-pop"],                "language": "ta", "era": "2010s", "mood": "energetic"},
    {"title": "Why This Kolaveri Di",   "artist": "Dhanush",                "genres": ["tamil-film-pop"],                "language": "ta", "era": "2010s", "mood": "energetic"},
    {"title": "Nila Kaigirathu",        "artist": "Madhushree",             "genres": ["tamil-film-pop"],                "language": "ta", "era": "2000s", "mood": "chill"},

    {"title": "Akale",                  "artist": "Vidhu Prathap",          "genres": ["malayalam-film-pop"],            "language": "ml", "era": "2010s", "mood": "melancholy"},
    {"title": "Aaro Nee Aaro",          "artist": "K.J. Yesudas",           "genres": ["malayalam-film-pop"],            "language": "ml", "era": "1970s", "mood": "nostalgic"},
    {"title": "Jeevamshamayi",          "artist": "K.S. Harisankar",        "genres": ["malayalam-film-pop"],            "language": "ml", "era": "2010s", "mood": "melancholy"},

    {"title": "Tum Hi Ho",              "artist": "Arijit Singh",           "genres": ["hindi-film-pop"],                "language": "hi", "era": "2010s", "mood": "melancholy"},
    {"title": "Channa Mereya",          "artist": "Arijit Singh",           "genres": ["hindi-film-pop"],                "language": "hi", "era": "2010s", "mood": "melancholy"},
    {"title": "Kesariya",               "artist": "Arijit Singh",           "genres": ["hindi-film-pop"],                "language": "hi", "era": "2020s", "mood": "nostalgic"},
    {"title": "Mast Magan",             "artist": "Arijit Singh",           "genres": ["hindi-film-pop"],                "language": "hi", "era": "2010s", "mood": "chill"},
    {"title": "Jab Tak",                "artist": "Armaan Malik",           "genres": ["hindi-film-pop"],                "language": "hi", "era": "2010s", "mood": "melancholy"},
    {"title": "Pee Loon",               "artist": "Mohit Chauhan",          "genres": ["hindi-film-pop"],                "language": "hi", "era": "2010s", "mood": "nostalgic"},

    {"title": "Despacito",              "artist": "Luis Fonsi",             "genres": ["reggaeton", "latin-pop"],        "language": "es", "era": "2010s", "mood": "energetic"},
    {"title": "Vivir Mi Vida",          "artist": "Marc Anthony",           "genres": ["salsa", "latin-pop"],            "language": "es", "era": "2010s", "mood": "energetic"},
    {"title": "Bailando",               "artist": "Enrique Iglesias",       "genres": ["latin-pop"],                     "language": "es", "era": "2010s", "mood": "energetic"},
    {"title": "Burbujas de Amor",       "artist": "Juan Luis Guerra",       "genres": ["bachata", "latin-pop"],          "language": "es", "era": "1990s", "mood": "chill"},
    {"title": "Malamente",              "artist": "Rosalia",                "genres": ["flamenco-pop", "latin-pop"],     "language": "es", "era": "2010s", "mood": "energetic"},
    {"title": "Con Altura",             "artist": "Rosalia",                "genres": ["reggaeton"],                     "language": "es", "era": "2010s", "mood": "energetic"},

    {"title": "Tous les Memes",         "artist": "Stromae",                "genres": ["french-pop"],                    "language": "fr", "era": "2010s", "mood": "energetic"},
    {"title": "La Vie en Rose",         "artist": "Edith Piaf",             "genres": ["chanson"],                       "language": "fr", "era": "1940s", "mood": "nostalgic"},
    {"title": "Non, Je Ne Regrette",    "artist": "Edith Piaf",             "genres": ["chanson"],                       "language": "fr", "era": "1960s", "mood": "nostalgic"},
    {"title": "Je Te Promets",          "artist": "Zaz",                    "genres": ["french-pop"],                    "language": "fr", "era": "2010s", "mood": "chill"},

    {"title": "Spring Day",             "artist": "BTS",                    "genres": ["k-pop"],                         "language": "ko", "era": "2010s", "mood": "melancholy"},
    {"title": "Through the Night",      "artist": "IU",                     "genres": ["k-pop", "k-ballad"],             "language": "ko", "era": "2010s", "mood": "chill"},
    {"title": "Eight",                  "artist": "IU",                     "genres": ["k-pop"],                         "language": "ko", "era": "2020s", "mood": "melancholy"},
    {"title": "Stay With Me",           "artist": "Punch",                  "genres": ["k-pop", "k-ballad"],             "language": "ko", "era": "2010s", "mood": "melancholy"},

    {"title": "Garota de Ipanema",      "artist": "Joao Gilberto",          "genres": ["bossa-nova"],                    "language": "pt", "era": "1960s", "mood": "chill"},
    {"title": "Aguas de Marco",         "artist": "Elis Regina",            "genres": ["bossa-nova"],                    "language": "pt", "era": "1970s", "mood": "chill"},
    {"title": "Lenha",                  "artist": "Tim Maia",               "genres": ["mpb", "soul"],                   "language": "pt", "era": "1970s", "mood": "energetic"},
]

ERA_POOL: list[dict[str, Any]] = [
    # Era diversity: 1960s, 1970s, 1980s, 1990s, 2000s
    {"title": "Like a Rolling Stone",   "artist": "Bob Dylan",              "genres": ["folk-rock"],                     "language": "en", "era": "1960s", "mood": "energetic"},
    {"title": "A Day in the Life",      "artist": "The Beatles",            "genres": ["psychedelic-rock"],              "language": "en", "era": "1960s", "mood": "nostalgic"},
    {"title": "Sympathy for the Devil", "artist": "The Rolling Stones",     "genres": ["classic-rock"],                  "language": "en", "era": "1960s", "mood": "energetic"},
    {"title": "Hey Jude",               "artist": "The Beatles",            "genres": ["pop-rock"],                      "language": "en", "era": "1960s", "mood": "nostalgic"},
    {"title": "Good Vibrations",        "artist": "The Beach Boys",         "genres": ["pop-rock"],                      "language": "en", "era": "1960s", "mood": "energetic"},

    {"title": "Stairway to Heaven",     "artist": "Led Zeppelin",           "genres": ["classic-rock", "hard-rock"],     "language": "en", "era": "1970s", "mood": "nostalgic"},
    {"title": "Bohemian Rhapsody",      "artist": "Queen",                  "genres": ["progressive-rock"],              "language": "en", "era": "1970s", "mood": "energetic"},
    {"title": "Hotel California",       "artist": "Eagles",                 "genres": ["soft-rock"],                     "language": "en", "era": "1970s", "mood": "nostalgic"},
    {"title": "Dreams",                 "artist": "Fleetwood Mac",          "genres": ["soft-rock"],                     "language": "en", "era": "1970s", "mood": "chill"},
    {"title": "Heroes",                 "artist": "David Bowie",            "genres": ["art-rock"],                      "language": "en", "era": "1970s", "mood": "energetic"},

    {"title": "Take On Me",             "artist": "a-ha",                   "genres": ["synth-pop", "new-wave"],         "language": "en", "era": "1980s", "mood": "energetic"},
    {"title": "Blue Monday",            "artist": "New Order",              "genres": ["synth-pop", "new-wave"],         "language": "en", "era": "1980s", "mood": "energetic"},
    {"title": "Tainted Love",           "artist": "Soft Cell",              "genres": ["synth-pop", "new-wave"],         "language": "en", "era": "1980s", "mood": "energetic"},
    {"title": "Pictures of You",        "artist": "The Cure",               "genres": ["post-punk", "new-wave"],         "language": "en", "era": "1980s", "mood": "melancholy"},
    {"title": "Just Like Heaven",       "artist": "The Cure",               "genres": ["alt-rock", "new-wave"],          "language": "en", "era": "1980s", "mood": "energetic"},
    {"title": "How Soon Is Now",        "artist": "The Smiths",             "genres": ["alt-rock"],                      "language": "en", "era": "1980s", "mood": "melancholy"},

    {"title": "Smells Like Teen Spirit","artist": "Nirvana",                "genres": ["grunge", "alt-rock"],            "language": "en", "era": "1990s", "mood": "energetic"},
    {"title": "Wonderwall",             "artist": "Oasis",                  "genres": ["britpop", "alt-rock"],           "language": "en", "era": "1990s", "mood": "nostalgic"},
    {"title": "Karma Police",           "artist": "Radiohead",              "genres": ["alt-rock"],                      "language": "en", "era": "1990s", "mood": "melancholy"},
    {"title": "No Surprises",           "artist": "Radiohead",              "genres": ["alt-rock"],                      "language": "en", "era": "1990s", "mood": "melancholy"},
    {"title": "Black Hole Sun",         "artist": "Soundgarden",            "genres": ["grunge"],                        "language": "en", "era": "1990s", "mood": "melancholy"},
    {"title": "1979",                   "artist": "Smashing Pumpkins",      "genres": ["alt-rock"],                      "language": "en", "era": "1990s", "mood": "nostalgic"},

    {"title": "Seven Nation Army",      "artist": "The White Stripes",      "genres": ["garage-rock"],                   "language": "en", "era": "2000s", "mood": "energetic"},
    {"title": "Float On",               "artist": "Modest Mouse",           "genres": ["indie-rock"],                    "language": "en", "era": "2000s", "mood": "energetic"},
    {"title": "Hey Ya",                 "artist": "OutKast",                "genres": ["hip-hop", "funk"],               "language": "en", "era": "2000s", "mood": "energetic"},
    {"title": "Crazy",                  "artist": "Gnarls Barkley",         "genres": ["neo-soul", "alt-pop"],           "language": "en", "era": "2000s", "mood": "energetic"},

    {"title": "Suzanne",                "artist": "Leonard Cohen",          "genres": ["folk", "singer-songwriter"],     "language": "en", "era": "1960s", "mood": "melancholy"},
    {"title": "The Sound of Silence",   "artist": "Simon and Garfunkel",    "genres": ["folk-rock"],                     "language": "en", "era": "1960s", "mood": "melancholy"},
    {"title": "I Will Always Love You", "artist": "Whitney Houston",        "genres": ["pop", "ballad"],                 "language": "en", "era": "1990s", "mood": "melancholy"},
    {"title": "Yesterday",              "artist": "The Beatles",            "genres": ["pop-rock"],                      "language": "en", "era": "1960s", "mood": "melancholy"},
    {"title": "Imagine",                "artist": "John Lennon",            "genres": ["folk-pop"],                      "language": "en", "era": "1970s", "mood": "nostalgic"},
]

MOOD_POOL: list[dict[str, Any]] = [
    # Mood diversity: for someone stuck in melancholy, push energetic / focus / nostalgic
    {"title": "Mr. Blue Sky",           "artist": "Electric Light Orchestra","genres": ["rock", "pop-rock"],             "language": "en", "era": "1970s", "mood": "energetic"},
    {"title": "Walking on Sunshine",    "artist": "Katrina and the Waves",  "genres": ["pop", "new-wave"],               "language": "en", "era": "1980s", "mood": "energetic"},
    {"title": "Happy",                  "artist": "Pharrell Williams",      "genres": ["neo-soul", "pop"],               "language": "en", "era": "2010s", "mood": "energetic"},
    {"title": "Can't Stop the Feeling", "artist": "Justin Timberlake",      "genres": ["pop"],                           "language": "en", "era": "2010s", "mood": "energetic"},
    {"title": "Uptown Funk",            "artist": "Mark Ronson",            "genres": ["funk", "pop"],                   "language": "en", "era": "2010s", "mood": "energetic"},
    {"title": "Good as Hell",           "artist": "Lizzo",                  "genres": ["pop", "r&b"],                    "language": "en", "era": "2010s", "mood": "energetic"},
    {"title": "Levitating",             "artist": "Dua Lipa",               "genres": ["pop", "disco-pop"],              "language": "en", "era": "2020s", "mood": "energetic"},
    {"title": "Don't Stop Me Now",      "artist": "Queen",                  "genres": ["rock"],                          "language": "en", "era": "1970s", "mood": "energetic"},
    {"title": "Dancing Queen",          "artist": "ABBA",                   "genres": ["disco", "pop"],                  "language": "en", "era": "1970s", "mood": "energetic"},
    {"title": "September",              "artist": "Earth, Wind and Fire",   "genres": ["funk", "disco"],                 "language": "en", "era": "1970s", "mood": "energetic"},

    {"title": "Weightless",             "artist": "Marconi Union",          "genres": ["ambient", "electronic"],         "language": "instrumental", "era": "2010s", "mood": "focus"},
    {"title": "Vespers",                "artist": "Olafur Arnalds",         "genres": ["neo-classical"],                 "language": "instrumental", "era": "2010s", "mood": "focus"},
    {"title": "Re: Stacks",             "artist": "Bon Iver",               "genres": ["indie-folk"],                    "language": "en", "era": "2000s", "mood": "focus"},
    {"title": "Music for Airports",     "artist": "Brian Eno",              "genres": ["ambient"],                       "language": "instrumental", "era": "1970s", "mood": "focus"},
    {"title": "Strobe",                 "artist": "Deadmau5",               "genres": ["progressive-house"],             "language": "en", "era": "2010s", "mood": "focus"},
    {"title": "Saman",                  "artist": "Olafur Arnalds",         "genres": ["neo-classical"],                 "language": "instrumental", "era": "2010s", "mood": "focus"},

    {"title": "The Boys of Summer",     "artist": "Don Henley",             "genres": ["soft-rock"],                     "language": "en", "era": "1980s", "mood": "nostalgic"},
    {"title": "Time After Time",        "artist": "Cyndi Lauper",           "genres": ["pop"],                           "language": "en", "era": "1980s", "mood": "nostalgic"},
    {"title": "Born to Run",            "artist": "Bruce Springsteen",      "genres": ["rock"],                          "language": "en", "era": "1970s", "mood": "nostalgic"},
    {"title": "Fast Car",               "artist": "Tracy Chapman",          "genres": ["folk-rock"],                     "language": "en", "era": "1980s", "mood": "nostalgic"},

    {"title": "Lovely Day",             "artist": "Bill Withers",           "genres": ["soul", "r&b"],                   "language": "en", "era": "1970s", "mood": "chill"},
    {"title": "Lean on Me",             "artist": "Bill Withers",           "genres": ["soul"],                          "language": "en", "era": "1970s", "mood": "chill"},
    {"title": "Tennessee Whiskey",      "artist": "Chris Stapleton",        "genres": ["country-soul"],                  "language": "en", "era": "2010s", "mood": "chill"},
    {"title": "Skinny Dippin'",         "artist": "Sabrina Carpenter",      "genres": ["pop"],                           "language": "en", "era": "2020s", "mood": "chill"},
]


# ============================================================
# Generator
# ============================================================

def _pad_pool(base: list[dict[str, Any]], target_size: int, rng: random.Random) -> list[dict[str, Any]]:
    """If the manual pool is shorter than CANDIDATES_PER_SCOPE, sample with
    replacement and append a small uniqueness suffix to track titles."""
    if len(base) >= target_size:
        return base[:target_size]
    out = list(base)
    while len(out) < target_size:
        pick = rng.choice(base)
        clone = dict(pick)
        clone["genres"] = list(clone["genres"])
        out.append(clone)
    return out


def _to_candidate(entry: dict[str, Any], *, scope: str, idx: int) -> dict[str, Any]:
    """Stamp the entry with a stable spotify_track_id + album placeholder."""
    return {
        "spotify_track_id": f"mock-{scope}-{idx:03d}",
        "title": entry["title"],
        "artist": entry["artist"],
        "album": entry.get("album"),
        "genres": list(entry["genres"]),
        "language": entry["language"],
        "era": entry["era"],
        "mood": entry["mood"],
        "scope_origin": scope,                                 # provenance: which scope produced this candidate
    }


def build_candidates() -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    pools = {
        "genre":    GENRE_POOL,
        "language": LANGUAGE_POOL,
        "era":      ERA_POOL,
        "mood":     MOOD_POOL,
    }
    out: list[dict[str, Any]] = []
    for scope, base in pools.items():
        padded = _pad_pool(base, CANDIDATES_PER_SCOPE, rng)
        # Shuffle within scope so the LLM doesn't see them in a fixed order
        rng.shuffle(padded)
        for idx, entry in enumerate(padded):
            out.append(_to_candidate(entry, scope=scope, idx=idx))
    return out


def write_fixture() -> Path:
    candidates = build_candidates()
    payload = {
        "_schema_version": 1,
        "_generated_by": "scripts/generate_mock_candidates.py",
        "_per_scope_count": CANDIDATES_PER_SCOPE,
        "candidates": candidates,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return OUT_FILE


def main() -> None:
    path = write_fixture()
    print(f"wrote: {path}")
    print(f"size:  {path.stat().st_size:,} bytes")
    data = json.loads(path.read_text(encoding="utf-8"))
    candidates = data["candidates"]
    print(f"total candidates: {len(candidates)}")
    from collections import Counter
    by_scope = Counter(c["scope_origin"] for c in candidates)
    for scope, count in sorted(by_scope.items()):
        print(f"  {scope}: {count}")


if __name__ == "__main__":
    main()
