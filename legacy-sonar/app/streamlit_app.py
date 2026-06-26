"""Spotify Sonar - the AI-native discovery MVP.

End-to-end: user types intent + sets novelty/activity controls -> Groq
parses to Intent -> Groq plans Spotify queries -> Spotify client (mock or
real) returns candidates -> Groq reasoner ranks + explains -> Streamlit
renders a 20-track playlist with per-track 'why this song' explanations.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make `src` importable regardless of CWD
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import streamlit as st                                            # noqa: E402

from src.config import DEFAULT_TRACK_COUNT                        # noqa: E402
from src.pipeline import generate_playlist                        # noqa: E402
from src.schema import Playlist                                   # noqa: E402
from src.spotify.client import get_spotify_client                 # noqa: E402

logging.basicConfig(level=logging.INFO)

SPOTIFY_GREEN = "#1DB954"
SPOTIFY_BLACK = "#0a0a0a"
SPOTIFY_GRAY = "#b3b3b3"

# ============================================================
# Page config + theme
# ============================================================

st.set_page_config(
    page_title="Sonar · AI music discovery",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {SPOTIFY_BLACK}; color: #fff; }}
    .block-container {{ padding-top: 2rem !important; max-width: 1180px !important; }}
    h1, h2, h3, h4 {{ color: #fff; letter-spacing: -0.01em; }}
    a {{ color: #b3b3b3; text-decoration: none; }} a:hover {{ color: #fff; }}

    .app-header {{
        display: flex; align-items: center; gap: 12px;
        padding: 4px 0 12px 0;
        border-bottom: 1px solid #2a2a2a;
        margin-bottom: 24px;
    }}
    .logo-box {{
        width: 36px; height: 36px; border-radius: 10px;
        background: rgba(29,185,84,0.18);
        border: 1px solid rgba(29,185,84,0.40);
        display: inline-flex; align-items: center; justify-content: center;
        color: {SPOTIFY_GREEN}; font-size: 18px; font-weight: 700;
    }}
    .brand {{ display: flex; flex-direction: column; line-height: 1.15; }}
    .brand-name {{ font-size: 16px; font-weight: 700; color: #fff; }}
    .brand-sub {{ font-size: 11.5px; color: #6b7280; }}
    .header-right {{ margin-left: auto; display: flex; gap: 12px; }}
    .header-right a {{ font-size: 12px; }}

    .hero {{
        border-radius: 18px;
        border: 1px solid #2a2a2a;
        background: linear-gradient(135deg, #141414 0%, #141414 55%, #1a1a1a 100%);
        padding: 28px 28px; margin-bottom: 24px;
    }}
    .kicker {{
        font-size: 11px; text-transform: uppercase; letter-spacing: 0.10em;
        color: {SPOTIFY_GREEN}; font-weight: 600;
    }}
    .hero h1 {{
        font-size: 28px; font-weight: 700; margin: 6px 0 10px 0;
        color: #fff; line-height: 1.22; max-width: 780px;
    }}
    .hero p {{
        font-size: 14px; color: #b3b3b3; line-height: 1.65; margin: 0; max-width: 780px;
    }}

    .pill {{
        display: inline-block; padding: 3px 10px; margin: 2px 4px 2px 0;
        border-radius: 999px; font-size: 11.5px;
        background: rgba(29,185,84,0.10); color: #6ee7b7;
        border: 1px solid rgba(29,185,84,0.30);
    }}
    .pill.muted {{ background: #1a1a1a; color: #b3b3b3; border-color: #2a2a2a; }}
    .pill.warn  {{ background: rgba(245,158,11,.10); color: #fcd34d; border-color: rgba(245,158,11,.30); }}

    .stTextInput input, .stTextArea textarea {{
        background: #141414;
        color: #fff;
        border: 1px solid #2a2a2a;
        border-radius: 10px;
        font-size: 15px;
    }}
    .stTextInput input:focus, .stTextArea textarea:focus {{
        border-color: {SPOTIFY_GREEN};
        box-shadow: 0 0 0 2px rgba(29,185,84,.20);
    }}
    .stSelectbox > div > div, .stMultiSelect > div > div {{
        background: #141414; border-color: #2a2a2a;
    }}
    .stButton > button {{
        background: #141414; color: #d1d5db; font-weight: 500;
        border: 1px solid #2a2a2a; border-radius: 10px;
    }}
    .stButton > button:hover:not(:disabled) {{
        background: rgba(29,185,84,.10); color: #fff;
        border-color: rgba(29,185,84,.40);
    }}
    .stButton > button[kind="primary"] {{
        background: {SPOTIFY_GREEN}; color: #0a0a0a; font-weight: 700;
        border-color: {SPOTIFY_GREEN};
    }}
    .stButton > button[kind="primary"]:hover {{
        background: #1ED760; border-color: #1ED760;
    }}

    .track-row {{
        display: flex; align-items: center; gap: 14px;
        padding: 10px 14px;
        border: 1px solid #2a2a2a;
        background: rgba(20,20,20,.6);
        border-radius: 12px;
        margin-bottom: 8px;
    }}
    .track-row:hover {{ background: rgba(29,185,84,.04); border-color: rgba(29,185,84,.30); }}
    .track-rank {{
        min-width: 28px; text-align: right;
        color: #6b7280; font-variant-numeric: tabular-nums; font-size: 13px;
    }}
    .track-art {{
        width: 44px; height: 44px; border-radius: 6px;
        background: linear-gradient(135deg, #1f2937, #0f172a);
        display: inline-flex; align-items: center; justify-content: center;
        color: {SPOTIFY_GREEN}; font-size: 18px; flex: 0 0 44px;
    }}
    .track-meta {{ flex: 1; min-width: 0; }}
    .track-title {{ font-size: 14.5px; font-weight: 600; color: #fff;
                    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .track-artist {{ font-size: 12.5px; color: #b3b3b3; }}
    .track-tags {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .track-tag {{
        font-size: 11px; padding: 2px 8px; border-radius: 6px;
        background: rgba(59,130,246,.12); color: #93c5fd;
        border: 1px solid rgba(59,130,246,.30);
    }}
    .track-tag.green {{ background: rgba(29,185,84,.12); color: #6ee7b7;
                        border-color: rgba(29,185,84,.30); }}
    .track-tag.gray  {{ background: #1a1a1a; color: #b3b3b3; border-color: #2a2a2a; }}
    .track-explain {{
        font-size: 13px; color: rgba(255,255,255,.92); line-height: 1.5;
        margin-left: 86px;                              /* aligns under title */
        padding: 8px 14px;
        background: rgba(29,185,84,.04);
        border-left: 3px solid rgba(29,185,84,.55);
        border-radius: 0 8px 8px 0;
        margin-bottom: 10px;
    }}
    .track-novelty {{
        font-size: 11px; color: {SPOTIFY_GREEN}; font-weight: 600;
        text-transform: uppercase; letter-spacing: .05em;
    }}

    .app-footer {{
        margin-top: 32px; padding: 16px 0;
        border-top: 1px solid #2a2a2a;
        color: #6b7280; font-size: 11.5px;
        display: flex; justify-content: space-between; flex-wrap: wrap; gap: 12px;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# Header + Hero
# ============================================================

st.markdown(
    """
    <div class="app-header">
        <div class="logo-box">🎯</div>
        <div class="brand">
            <div class="brand-name">Sonar</div>
            <div class="brand-sub">AI-native music discovery · powered by Groq + Spotify Web API</div>
        </div>
        <div class="header-right">
            <a href="https://github.com/mmishra0321/NL_AIReviewDiscoveryEngine" target="_blank">↗ Review Engine repo</a>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="kicker">PM CAPSTONE · SPOTIFY GROWTH</div>
        <h1>Tell Sonar what you want. In English. It'll point you away from your taste graph, not into it.</h1>
        <p>Type a free-form intent. Sonar parses it with Llama 3.3 70B, plans a Spotify Web API
        query, ranks the candidate set with a second LLM call, and shows you a 20-track playlist
        where every pick comes with a one-sentence explanation tied to what you asked for.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Mode badge (mock vs real Spotify)
_sp_test = get_spotify_client()
if _sp_test.using_real_api:
    st.markdown('<span class="pill">🟢 Live Spotify Web API</span>', unsafe_allow_html=True)
else:
    st.markdown(
        '<span class="pill warn">⚠ Pass-1 mock catalog — set SPOTIFY_CLIENT_ID + SPOTIFY_CLIENT_SECRET in .env to flip to live API</span>',
        unsafe_allow_html=True,
    )

# ============================================================
# Intent input + controls
# ============================================================

SAMPLE_INTENTS = [
    "Energetic Spanish music for my morning run, similar vibe to Rosalia but no Rosalia, things I'm unlikely to know",
    "Soft instrumental stuff for late-night study, nothing with lyrics, calm",
    "Upbeat Hindi indie for a long drive, mix of new and familiar",
    "Tamil post-rock or fusion for deep focus work, deep cuts welcome",
]

st.markdown("##### What do you want to hear?")

with st.form("sonar_form", clear_on_submit=False):
    intent_text = st.text_area(
        label="Intent",
        label_visibility="collapsed",
        placeholder="Describe what you want. Talk about mood, language, activity, what to exclude, how adventurous to be...",
        height=110,
        key="sonar_intent_text",
    )

    sample_col1, sample_col2 = st.columns([7, 5], gap="small")
    with sample_col1:
        st.caption("Try one of these:")
        chip_cols = st.columns(2, gap="small")
        for i, sq in enumerate(SAMPLE_INTENTS):
            if chip_cols[i % 2].form_submit_button(
                f"💡 {sq[:62]}…" if len(sq) > 62 else f"💡 {sq}",
                use_container_width=True,
            ):
                st.session_state["sonar_intent_text"] = sq
                st.session_state["sonar_use_sample"] = sq
                st.rerun()

    ctrl_c1, ctrl_c2, ctrl_c3, ctrl_c4 = st.columns([1.2, 1.4, 1.4, 1])
    with ctrl_c1:
        novelty = st.slider("Novelty", min_value=0, max_value=10, value=7,
                            help="0 = music you already know. 10 = obscure deep cuts.")
    with ctrl_c2:
        activity = st.selectbox(
            "Activity context (optional)",
            ["(none)", "workout", "study", "commute", "focus", "party", "chill", "sleep"],
            index=0,
        )
    with ctrl_c3:
        languages = st.multiselect(
            "Languages (optional)",
            ["en", "es", "hi", "ta", "fr", "pt", "ko", "ja"],
            default=[],
            help="Constrain to these ISO codes. Leave empty for any language.",
        )
    with ctrl_c4:
        track_count = st.number_input("Tracks", min_value=5, max_value=50,
                                       value=DEFAULT_TRACK_COUNT, step=1)

    submitted = st.form_submit_button(
        "🎯 Generate playlist", type="primary", use_container_width=True,
    )

# ============================================================
# Run pipeline
# ============================================================

def _run_pipeline(text: str, *, novelty: int, activity: str,
                  languages: list[str], track_count: int) -> Playlist | None:
    if not text.strip():
        st.warning("Type an intent or pick one of the samples first.")
        return None
    activity_clean = None if activity == "(none)" else activity
    languages_clean = languages or None
    try:
        with st.spinner("Parsing intent → planning Spotify query → ranking candidates…"):
            return generate_playlist(
                text,
                novelty=novelty,
                activity=activity_clean,
                languages=languages_clean,
                track_count=track_count,
            )
    except Exception as exc:                                       # noqa: BLE001
        st.error(f"Pipeline failed: {exc}")
        logging.exception("pipeline failed")
        return None


playlist: Playlist | None = None
if submitted:
    playlist = _run_pipeline(
        st.session_state.get("sonar_intent_text", intent_text),
        novelty=int(novelty), activity=activity,
        languages=list(languages), track_count=int(track_count),
    )
    if playlist is not None:
        st.session_state["sonar_playlist"] = playlist.model_dump(mode="json")
elif "sonar_playlist" in st.session_state:
    playlist = Playlist.model_validate(st.session_state["sonar_playlist"])

# ============================================================
# Render results
# ============================================================

if playlist is not None:
    intent = playlist.intent
    plan = playlist.plan

    st.markdown("---")

    # Intent recap row
    recap_pills: list[str] = []
    if intent.mood:
        recap_pills += [f'<span class="pill">{m}</span>' for m in intent.mood[:4]]
    if intent.languages:
        recap_pills += [f'<span class="pill">lang:{l}</span>' for l in intent.languages]
    if intent.seed_artists:
        recap_pills += [f'<span class="pill">seed:{a}</span>' for a in intent.seed_artists[:3]]
    if intent.exclude_artists:
        recap_pills += [f'<span class="pill warn">−{a}</span>' for a in intent.exclude_artists[:3]]
    if intent.activity_context:
        recap_pills += [f'<span class="pill">for {intent.activity_context}</span>']
    recap_pills.append(f'<span class="pill muted">novelty {intent.novelty_level}/10</span>')

    cols = st.columns([6, 2])
    with cols[0]:
        st.markdown("##### What Sonar heard")
        st.markdown(" ".join(recap_pills), unsafe_allow_html=True)
        if plan.rationale:
            st.caption(f"Plan rationale: {plan.rationale}")
    with cols[1]:
        st.markdown(
            f'<div style="text-align:right;margin-top:6px;">'
            f'<span class="pill muted">⏱ {playlist.elapsed_ms} ms total</span><br/>'
            f'<span class="pill muted">{len(playlist.tracks)} tracks ranked</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    if not playlist.tracks:
        st.warning("No candidates matched your intent. Try widening languages, lowering novelty, or removing exclusions.")
    else:
        st.markdown(f"##### Your 20-track Sonar playlist · `{len(playlist.tracks)} of {intent.target_track_count}` requested")

        for idx, t in enumerate(playlist.tracks, start=1):
            tags_html = []
            if t.language:
                tags_html.append(f'<span class="track-tag">{t.language}</span>')
            if t.popularity:
                tags_html.append(
                    f'<span class="track-tag {"gray" if t.popularity > 60 else "green"}">'
                    f'pop {t.popularity}</span>'
                )
            for g in (t.genres or [])[:2]:
                tags_html.append(f'<span class="track-tag gray">{g}</span>')
            tags_html.append(f'<span class="track-tag green">score {t.score:.2f}</span>')

            st.markdown(
                f"""<div class="track-row">
                    <div class="track-rank">{idx:02d}</div>
                    <div class="track-art">♪</div>
                    <div class="track-meta">
                        <div class="track-title">{t.title}</div>
                        <div class="track-artist">{t.artist}</div>
                    </div>
                    <div class="track-tags">{''.join(tags_html)}</div>
                </div>""",
                unsafe_allow_html=True,
            )
            st.markdown(
                f"""<div class="track-explain">
                    <span class="track-novelty">{t.novelty_signal}</span><br/>
                    {t.explanation}
                </div>""",
                unsafe_allow_html=True,
            )

        # Open-in-Spotify footer
        deep_link_ids = ",".join(t.track_id for t in playlist.tracks[:10])
        st.caption(
            f"Pass-1 mock track IDs are synthetic and won't open in Spotify. "
            f"Wire SPOTIFY_CLIENT_ID/SECRET to switch to live mode "
            f"(then each row deep-links into the Spotify app)."
            if not playlist.using_real_spotify else
            f"All track IDs validated against the live Spotify catalog. Click any title row in production deploy."
        )

# ============================================================
# Footer
# ============================================================

st.markdown(
    """
    <div class="app-footer">
        <div>Powered by Groq (Llama-3.3 70B) · Spotify Web API · Streamlit</div>
        <div>PM Capstone · Spotify Sonar MVP</div>
    </div>
    """,
    unsafe_allow_html=True,
)
