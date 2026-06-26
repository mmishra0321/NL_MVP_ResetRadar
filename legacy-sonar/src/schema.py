"""Shared data shapes across the MVP.

Pass 1 (current): everything except live Spotify calls works against
Pydantic shapes only, so the LLM pipeline can be developed before any
Spotify Developer credentials are wired in.
Pass 2: the same shapes back real Web API responses.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

NoveltyLevel = int  # 0 (familiar) ... 10 (deep cuts)
SpotifyEndpoint = Literal["search", "recommendations"]


class Intent(BaseModel):
    """Parsed user intent from the natural-language box."""

    raw_text: str
    mood: list[str] = Field(default_factory=list)               # e.g. ["energetic", "uplifting"]
    languages: list[str] = Field(default_factory=list)          # ISO codes, e.g. ["es", "ta"]
    genres: list[str] = Field(default_factory=list)             # ["indie pop", "lo-fi"]
    seed_artists: list[str] = Field(default_factory=list)       # artist names mentioned
    seed_tracks: list[str] = Field(default_factory=list)
    exclude_artists: list[str] = Field(default_factory=list)
    exclude_genres: list[str] = Field(default_factory=list)
    novelty_level: NoveltyLevel = 7                             # 0-10
    target_track_count: int = 20
    activity_context: Optional[str] = None                      # "workout" | "study" | "commute" | "focus" | "party" | "chill" | None
    locale: Optional[str] = None                                # e.g. "en-IN"
    notes: Optional[str] = None                                 # free-form residual from raw_text


class QueryPlan(BaseModel):
    """The planner's blueprint - which Spotify endpoints to hit and with what."""

    endpoints: list[SpotifyEndpoint] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)     # 1-3 raw Spotify search strings
    seed_artist_names: list[str] = Field(default_factory=list)
    target_audio_features: dict[str, float] = Field(default_factory=dict)
    # e.g. {"target_energy": 0.8, "target_danceability": 0.7,
    #       "min_popularity": 20, "max_popularity": 60}
    exclude_artist_names: list[str] = Field(default_factory=list)
    rationale: str = ""                                         # one-sentence why for the deck


class CandidateTrack(BaseModel):
    """A track returned by Spotify Web API (or mock), pre-ranking."""

    track_id: str
    title: str
    artist: str
    artist_id: str
    album: Optional[str] = None
    album_art: Optional[str] = None
    audio_features: dict = Field(default_factory=dict)
    popularity: int = 0
    preview_url: Optional[str] = None
    spotify_url: str
    language: Optional[str] = None                              # ISO code if known
    genres: list[str] = Field(default_factory=list)


class RankedTrack(CandidateTrack):
    """A track after the reasoner has scored + explained it."""

    score: float                                                # 0-1
    explanation: str                                            # one-sentence "why this fits"
    novelty_signal: str                                         # "first time on a Sonar pick", etc.


class Playlist(BaseModel):
    """The final deliverable shown to the user."""

    intent: Intent
    plan: QueryPlan
    tracks: list[RankedTrack]
    generated_at: datetime
    spotify_signed_in: bool = False
    elapsed_ms: int = 0
    using_real_spotify: bool = False                            # Pass 1 = False, Pass 2 = True
