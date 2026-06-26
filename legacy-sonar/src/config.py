"""Central configuration for the MVP."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent

# --- API keys ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8501/callback")

# --- LLM models ---
GROQ_MODEL_REASONER = "llama-3.3-70b-versatile"      # for intent parsing + result reasoning
GROQ_MODEL_FAST = "llama-3.1-8b-instant"              # for cheap planning / validation calls

# --- App knobs ---
DEFAULT_TRACK_COUNT = 20
MAX_CANDIDATES_FROM_SPOTIFY = 100                     # before LLM re-rank
LATENCY_BUDGET_SECONDS = 8                            # first-playlist target
