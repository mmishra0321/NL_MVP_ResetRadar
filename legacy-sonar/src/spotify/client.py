"""Spotify client - Pass 1 (mock) and Pass 2 (real) live behind one interface.

In Pass 1 (today): MockSpotifyClient generates deterministic candidate
tracks from a curated synthetic catalog so we can wire and demo the full
LLM pipeline without registering for the Spotify Developer Dashboard.

In Pass 2: a RealSpotifyClient subclass will call spotipy. Both expose
the same `search` / `recommendations` / `audio_features` methods so
`get_spotify_client()` is the only switch.
"""
from __future__ import annotations

import hashlib
import logging
import random
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.config import (
    MAX_CANDIDATES_FROM_SPOTIFY, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET,
)
from src.schema import CandidateTrack, QueryPlan

log = logging.getLogger("mvp.spotify")


# ============================================================
# Mock catalog
# ============================================================

@dataclass(frozen=True)
class _MockArtist:
    name: str
    language: str               # "en" | "es" | "ta" | "hi" | "pt" | "ko" | "ja" | ...
    primary_genre: str
    secondary_genres: tuple[str, ...]
    popularity: int             # 0-100
    energy: float               # 0-1
    danceability: float
    valence: float
    acousticness: float
    track_titles: tuple[str, ...]


# Hand-curated synthetic catalog. Mixes mainstream + long-tail across
# 7 languages and 14 genres so the reasoner has real differentiation to
# work with. Names are FICTIONAL (so we never imply we host real catalog).
_MOCK_CATALOG: tuple[_MockArtist, ...] = (
    _MockArtist("Vela Cordero",   "es", "indie pop",       ("dream pop", "alt"),         48, 0.78, 0.70, 0.66, 0.18,
                ("Noches de Tinta", "Camino al Sur", "Espejo Roto", "Brisa Eléctrica")),
    _MockArtist("Marea Profunda", "es", "alt rock",        ("post-punk", "indie"),       62, 0.83, 0.55, 0.42, 0.10,
                ("Faro Apagado", "Ruido Blanco", "Casa Vacía", "Marejada")),
    _MockArtist("Sol Verbena",    "es", "flamenco fusion", ("electronic", "pop"),        71, 0.72, 0.81, 0.74, 0.22,
                ("Tinta Roja", "Verbena", "Sol y Sombra", "Café del Río")),
    _MockArtist("Quintet Ocaso",  "es", "latin jazz",      ("bossa", "jazz"),            44, 0.50, 0.68, 0.58, 0.55,
                ("Lluvia en Buenos Aires", "Madrugada Suave", "Vals del Olvido")),
    _MockArtist("Indra Patel",    "hi", "indie pop",       ("bollywood alt", "fusion"),  55, 0.66, 0.72, 0.60, 0.30,
                ("Saanjh", "Rooh", "Khwaab", "Aasmaan Tak")),
    _MockArtist("Aarya Joshi",    "hi", "alt rock",        ("rock", "fusion"),           69, 0.81, 0.58, 0.48, 0.12,
                ("Bekarar", "Jugnu", "Sahil", "Aaina")),
    _MockArtist("Karthik Iyer",   "ta", "carnatic fusion", ("indie", "fusion"),          41, 0.62, 0.55, 0.62, 0.45,
                ("Nilave", "Kaatru", "Megam", "Vaanam Pesum")),
    _MockArtist("Meera Devan",    "ta", "indie pop",       ("alt pop", "fusion"),        53, 0.70, 0.68, 0.66, 0.25,
                ("Velli Vaanil", "Mounam", "Vidiyal", "Kanavu")),
    _MockArtist("North Hollow",   "en", "indie rock",      ("post-rock", "shoegaze"),    47, 0.69, 0.49, 0.40, 0.15,
                ("Telegraph Wires", "Coast Static", "Half Light", "Borrowed Sky")),
    _MockArtist("Avery Linde",    "en", "alt pop",         ("dream pop", "indie"),       66, 0.65, 0.62, 0.60, 0.20,
                ("Glass Animals", "Slow Dial", "Open Hour", "After You Sleep")),
    _MockArtist("Mira Calder",    "en", "electronic",      ("synthwave", "dance"),       72, 0.86, 0.83, 0.55, 0.08,
                ("Voltage Bloom", "Night Cargo", "Strobe Heart", "Tower Lights")),
    _MockArtist("Tobias Sand",    "en", "folk",            ("acoustic", "americana"),    51, 0.32, 0.40, 0.62, 0.78,
                ("Paper Lanterns", "Quiet Hours", "Mountain Sunday", "Pinegrove Letters")),
    _MockArtist("Coral Reach",    "en", "ambient",         ("downtempo", "post-rock"),   38, 0.28, 0.30, 0.50, 0.85,
                ("Tidewater", "Sundown Loop", "Distant Lamps")),
    _MockArtist("Lupin & Vine",   "fr", "chanson",         ("indie pop", "alt"),         49, 0.55, 0.60, 0.58, 0.40,
                ("Pluie Légère", "Avenue Bleue", "Cinq Heures", "Île Verte")),
    _MockArtist("Joana Pires",    "pt", "MPB",             ("bossa", "samba"),           58, 0.60, 0.72, 0.72, 0.35,
                ("Manhã em Lisboa", "Cor de Maré", "Saudade Curta", "Rua das Flores")),
    _MockArtist("Hwan Yoo",       "ko", "alt pop",         ("k-indie", "dream pop"),     43, 0.62, 0.65, 0.55, 0.22,
                ("Bom Bi", "Hayan Bam", "Geori", "Buran Gil")),
    _MockArtist("Setsuko Mori",   "ja", "city pop",        ("nu-disco", "jazz funk"),    60, 0.74, 0.78, 0.66, 0.18,
                ("Neon Asagohan", "Tokyo Glide", "Late Showa", "Yokohama 84")),
    _MockArtist("Static Cradle",  "en", "lo-fi",           ("bedroom pop", "ambient"),   55, 0.48, 0.45, 0.42, 0.55,
                ("Two AM Bus", "Slow Friday", "Window Tape")),
    _MockArtist("Helia Voss",     "en", "synth-pop",       ("electronic", "dance"),      77, 0.84, 0.86, 0.62, 0.10,
                ("Pulse Architect", "Mirror Cassette", "Closer Than", "Wireframe")),
    _MockArtist("Dust Auriga",    "en", "shoegaze",        ("dream pop", "indie"),       33, 0.55, 0.42, 0.32, 0.20,
                ("Cassette Halo", "Slow Burn", "Half a Page")),
    _MockArtist("Kavi Rangan",    "ta", "post-rock",       ("instrumental", "alt"),      36, 0.58, 0.40, 0.45, 0.35,
                ("Idi Velicham", "Therinda Theru", "Maatram")),
    _MockArtist("Rio Hyacinth",   "en", "afrobeats",       ("dance", "pop"),             70, 0.82, 0.88, 0.70, 0.12,
                ("Morning Lagos", "Sunset Rule", "Crown Print")),
)


def _short_id(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:22]


def _features_for(artist: _MockArtist, jitter: float = 0.05) -> dict:
    """Each track jitters slightly off the artist baseline for realism."""
    return {
        "energy":       round(min(1.0, max(0.0, artist.energy       + (random.random() - 0.5) * jitter)), 3),
        "danceability": round(min(1.0, max(0.0, artist.danceability + (random.random() - 0.5) * jitter)), 3),
        "valence":      round(min(1.0, max(0.0, artist.valence      + (random.random() - 0.5) * jitter)), 3),
        "acousticness": round(min(1.0, max(0.0, artist.acousticness + (random.random() - 0.5) * jitter)), 3),
        "tempo":        round(80 + (artist.energy * 100), 1),
    }


def _candidate_from(artist: _MockArtist, title: str) -> CandidateTrack:
    tid = _short_id(f"{artist.name}|{title}")
    aid = _short_id(f"artist|{artist.name}")
    pop = max(0, min(100, artist.popularity + random.randint(-8, 8)))
    return CandidateTrack(
        track_id=tid,
        title=title,
        artist=artist.name,
        artist_id=aid,
        album=f"{title} - Single",
        album_art=None,
        audio_features=_features_for(artist),
        popularity=pop,
        preview_url=None,
        spotify_url=f"https://open.spotify.com/track/{tid}",
        language=artist.language,
        genres=[artist.primary_genre, *artist.secondary_genres],
    )


# ============================================================
# Interface
# ============================================================

class SpotifyClient(ABC):
    name: str = "abstract"
    using_real_api: bool = False

    @abstractmethod
    def search(self, query: str, *, limit: int = 30) -> list[CandidateTrack]: ...

    @abstractmethod
    def recommendations(
        self, *,
        seed_artist_names: list[str],
        target_audio_features: dict[str, float],
        limit: int = 30,
    ) -> list[CandidateTrack]: ...

    def fetch_candidates(self, plan: QueryPlan) -> list[CandidateTrack]:
        """Convenience: run a whole QueryPlan and return a deduped candidate list."""
        seen: set[str] = set()
        out: list[CandidateTrack] = []
        per_call = max(15, MAX_CANDIDATES_FROM_SPOTIFY // max(1, len(plan.endpoints) + len(plan.search_queries)))

        if "search" in plan.endpoints:
            for q in plan.search_queries or ["popular"]:
                for c in self.search(q, limit=per_call):
                    if c.track_id not in seen:
                        seen.add(c.track_id)
                        out.append(c)

        if "recommendations" in plan.endpoints and plan.seed_artist_names:
            for c in self.recommendations(
                seed_artist_names=plan.seed_artist_names,
                target_audio_features=plan.target_audio_features,
                limit=per_call,
            ):
                if c.track_id not in seen:
                    seen.add(c.track_id)
                    out.append(c)

        # Apply hard exclude
        excl_lc = {a.lower() for a in plan.exclude_artist_names}
        if excl_lc:
            out = [c for c in out if c.artist.lower() not in excl_lc]
        return out[:MAX_CANDIDATES_FROM_SPOTIFY]


# ============================================================
# Mock implementation
# ============================================================

class MockSpotifyClient(SpotifyClient):
    name = "mock"
    using_real_api = False

    def _parse_filters(self, query: str) -> dict[str, list[str]]:
        """Pull out `artist:"X"` and `genre:"Y"` operators from a Spotify-style query."""
        filters: dict[str, list[str]] = {"artist": [], "genre": [], "freetext": []}
        rest = query
        for op in ("artist", "genre"):
            for m in re.finditer(rf'{op}:"([^"]+)"', rest, flags=re.IGNORECASE):
                filters[op].append(m.group(1).strip().lower())
            rest = re.sub(rf'{op}:"[^"]+"', " ", rest, flags=re.IGNORECASE)
        free = re.sub(r"\s+", " ", rest).strip().lower()
        if free:
            filters["freetext"].append(free)
        return filters

    def _score_match(self, artist: _MockArtist, filters: dict[str, list[str]]) -> float:
        score = 0.0
        if filters["artist"]:
            for needle in filters["artist"]:
                if needle in artist.name.lower():
                    score += 5.0
                elif any(needle in g.lower() for g in (artist.primary_genre, *artist.secondary_genres)):
                    score += 1.0
        if filters["genre"]:
            for needle in filters["genre"]:
                if needle in artist.primary_genre.lower():
                    score += 3.0
                elif any(needle in g.lower() for g in artist.secondary_genres):
                    score += 1.5
        if filters["freetext"]:
            text_blob = (
                f"{artist.name} {artist.primary_genre} "
                f"{' '.join(artist.secondary_genres)} {artist.language}"
            ).lower()
            for tok in filters["freetext"][0].split():
                if len(tok) >= 3 and tok in text_blob:
                    score += 0.5
        return score

    def search(self, query: str, *, limit: int = 30) -> list[CandidateTrack]:
        random.seed(hash(query) & 0xFFFFFFFF)
        filters = self._parse_filters(query)
        ranked = sorted(
            ((self._score_match(a, filters), a) for a in _MOCK_CATALOG),
            key=lambda t: t[0],
            reverse=True,
        )
        # Take artists with non-zero score; if none match, return a diverse fallback set
        chosen = [a for s, a in ranked if s > 0]
        if not chosen:
            chosen = random.sample(list(_MOCK_CATALOG), k=min(8, len(_MOCK_CATALOG)))

        out: list[CandidateTrack] = []
        for artist in chosen:
            for title in artist.track_titles:
                out.append(_candidate_from(artist, title))
                if len(out) >= limit:
                    return out
        return out

    def recommendations(
        self, *,
        seed_artist_names: list[str],
        target_audio_features: dict[str, float],
        limit: int = 30,
    ) -> list[CandidateTrack]:
        # Deterministic seed so the demo is reproducible for a given intent
        seed_str = "|".join(seed_artist_names) + str(sorted(target_audio_features.items()))
        random.seed(hash(seed_str) & 0xFFFFFFFF)

        seed_lc = {n.lower() for n in seed_artist_names}
        seed_artists = [a for a in _MOCK_CATALOG if a.name.lower() in seed_lc]

        # Score every catalog artist by audio-feature distance to the targets
        def feature_distance(a: _MockArtist) -> float:
            t = target_audio_features
            d = 0.0
            if "target_energy" in t:        d += abs(a.energy       - t["target_energy"])
            if "target_danceability" in t:  d += abs(a.danceability - t["target_danceability"])
            if "target_valence" in t:       d += abs(a.valence      - t["target_valence"])
            if "target_acousticness" in t:  d += abs(a.acousticness - t["target_acousticness"])
            return d

        min_pop = int(target_audio_features.get("min_popularity", 0))
        max_pop = int(target_audio_features.get("max_popularity", 100))

        # Boost artists sharing language/genre with seeds; filter by popularity
        seed_languages = {a.language for a in seed_artists}
        seed_genres = {g for a in seed_artists for g in (a.primary_genre, *a.secondary_genres)}

        def affinity(a: _MockArtist) -> float:
            bonus = 0.0
            if a.language in seed_languages:
                bonus -= 0.4
            if a.primary_genre in seed_genres:
                bonus -= 0.3
            if a in seed_artists:
                bonus += 99.0                                 # never recommend the seed itself
            return feature_distance(a) + bonus

        eligible = [a for a in _MOCK_CATALOG if min_pop <= a.popularity <= max_pop and a not in seed_artists]
        if not eligible:                                       # popularity window too tight, relax it
            eligible = [a for a in _MOCK_CATALOG if a not in seed_artists]
        eligible.sort(key=affinity)

        out: list[CandidateTrack] = []
        for artist in eligible:
            for title in artist.track_titles:
                out.append(_candidate_from(artist, title))
                if len(out) >= limit:
                    return out
        return out


# ============================================================
# Real implementation (Pass 2 - stub for now)
# ============================================================

class RealSpotifyClient(SpotifyClient):
    """Live spotipy-backed client. Wired in Pass 2 once credentials exist."""

    name = "real"
    using_real_api = True

    def __init__(self) -> None:
        if not (SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET):
            raise RuntimeError(
                "SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET not set. "
                "Either register a Spotify Developer app, or stay in mock mode."
            )
        import spotipy
        from spotipy.oauth2 import SpotifyClientCredentials

        self._sp = spotipy.Spotify(
            auth_manager=SpotifyClientCredentials(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
            ),
            requests_timeout=10,
        )

    @staticmethod
    def _to_candidate(t: dict, audio_feat: dict | None = None) -> CandidateTrack:
        return CandidateTrack(
            track_id=t["id"],
            title=t["name"],
            artist=", ".join(a["name"] for a in t.get("artists", [])),
            artist_id=(t.get("artists") or [{"id": ""}])[0]["id"],
            album=(t.get("album") or {}).get("name"),
            album_art=((t.get("album") or {}).get("images") or [{}])[0].get("url"),
            audio_features=audio_feat or {},
            popularity=t.get("popularity", 0),
            preview_url=t.get("preview_url"),
            spotify_url=(t.get("external_urls") or {}).get("spotify", ""),
            language=None,
            genres=[],
        )

    def search(self, query: str, *, limit: int = 30) -> list[CandidateTrack]:
        res = self._sp.search(q=query, type="track", limit=min(50, limit))
        return [self._to_candidate(t) for t in (res.get("tracks", {}).get("items", []) or [])]

    def recommendations(
        self, *,
        seed_artist_names: list[str],
        target_audio_features: dict[str, float],
        limit: int = 30,
    ) -> list[CandidateTrack]:
        seed_ids: list[str] = []
        for name in seed_artist_names[:5]:
            res = self._sp.search(q=f'artist:"{name}"', type="artist", limit=1)
            items = res.get("artists", {}).get("items", []) or []
            if items:
                seed_ids.append(items[0]["id"])
        if not seed_ids:
            return []
        # spotipy passes target_* / min_* / max_* through unchanged
        recs = self._sp.recommendations(
            seed_artists=seed_ids[:5],
            limit=min(100, limit),
            **{k: v for k, v in target_audio_features.items() if v is not None},
        )
        return [self._to_candidate(t) for t in (recs.get("tracks", []) or [])]


# ============================================================
# Factory
# ============================================================

def get_spotify_client(force_mock: bool = False) -> SpotifyClient:
    """Auto-pick real if creds are set; mock otherwise (or if forced)."""
    if force_mock or not (SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET):
        log.info("Using MockSpotifyClient (no Spotify credentials configured).")
        return MockSpotifyClient()
    log.info("Using RealSpotifyClient (Spotify credentials detected).")
    return RealSpotifyClient()


__all__ = ["SpotifyClient", "MockSpotifyClient", "RealSpotifyClient", "get_spotify_client"]
