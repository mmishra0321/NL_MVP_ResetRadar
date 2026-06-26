/**
 * HomePage - the "Spotify web player where the Reset Radar nudge appears" view.
 *
 * As of R10 (revised), this is laid out like the desktop Spotify web
 * player at open.spotify.com - left sidebar, top bar, wide main
 * content area, "Good afternoon" + nudge card + Recently played grid
 * with proper album-art-style covers (gradient + symbol + label,
 * Spotify's own curated-playlist cover style).
 *
 * Why it matters: the deck claims Reset Radar surfaces inside Spotify
 * itself, not in a separate companion app. The page therefore mirrors
 * Spotify's own desktop chrome - any reviewer who has used the Spotify
 * web player recognises it instantly.
 *
 * Demo-only chrome: a "Viewing as: Aanya | Karthik" pill row sits
 * ABOVE the Spotify frame. In production that row doesn't exist - you
 * are simply whoever is signed into Spotify.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { api } from '../api/client.js';
import { colors } from '../theme.js';
import useDemoUser from '../hooks/useDemoUser.js';


// ============================================================
// Persona configuration: the "Recently played" tiles for each demo
// user. These are the *signature* repetitive items that drove their
// stuck score above threshold - the on-screen proof of what got
// "stuck". Real Spotify would surface these from /me/player/recently-
// played; in mock mode we ship them inline so the slide deck and the
// app stay in sync.
// ============================================================

const PERSONA_TILES = {
  'demo-aanya-002': [
    { title: 'Bollywood Hits 2026',        subtitle: 'Spotify',         theme: 'bollywood',    sym: 'B' },
    { title: 'Romantic Bollywood',         subtitle: 'Spotify',         theme: 'bollywood',    sym: 'R' },
    { title: 'Hindi Pop Now',              subtitle: 'Spotify',         theme: 'hindipop',     sym: 'H' },
    { title: 'Indian Indie',               subtitle: 'Spotify',         theme: 'indiepop',     sym: 'I' },
    { title: 'Bollywood Sing-Along',       subtitle: 'Spotify',         theme: 'bollywood',    sym: 'S' },
    { title: 'Hindi Hits',                 subtitle: 'Spotify',         theme: 'hindipop',     sym: 'H' },
  ],
  'demo-karthik-001': [
    { title: 'Telugu Film Hits',           subtitle: 'Spotify',         theme: 'telugufilm',   sym: 'T' },
    { title: 'Telugu Romance',             subtitle: 'Spotify',         theme: 'telugufilm',   sym: 'R' },
    { title: 'Carnatic Classical',         subtitle: 'Spotify',         theme: 'carnatic',     sym: '\u0950' },  // OM
    { title: 'Latest Telugu',              subtitle: 'Spotify',         theme: 'telugufilm',   sym: 'L' },
    { title: 'Evergreen Telugu',           subtitle: 'Spotify',         theme: 'telugufilm',   sym: 'E' },
    { title: 'Devotional South India',     subtitle: 'Spotify',         theme: 'carnatic',     sym: 'D' },
  ],
};


// Album-cover gradient + accent themes. Each looks like a Spotify
// curated-playlist cover: bold gradient base, single large symbol
// pinned to one corner, subtle texture.
const COVER_THEMES = {
  bollywood:   { from: '#dc2626', mid: '#f59e0b', to: '#7c2d12',   ink: '#fff5ec' },
  hindipop:    { from: '#ec4899', mid: '#8b5cf6', to: '#1e40af',   ink: '#fdf2f8' },
  indiepop:    { from: '#0891b2', mid: '#06b6d4', to: '#0d9488',   ink: '#ecfeff' },
  telugufilm:  { from: '#f97316', mid: '#facc15', to: '#9f1239',   ink: '#fff7ed' },
  carnatic:    { from: '#4f46e5', mid: '#7c3aed', to: '#581c87',   ink: '#ede9fe' },
};


function timeBasedGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}


// ============================================================
// Page root
// ============================================================

export default function HomePage() {
  const { userId, setUser } = useDemoUser();
  const [users, setUsers] = useState([]);
  const [nudge, setNudge] = useState(null);
  const [error, setError] = useState(null);

  const refresh = useCallback(async (uid) => {
    if (!uid) return;
    setError(null);
    try {
      const n = await api.getLatestNudge(uid).catch(() => null);
      setNudge(n);
    } catch (e) {
      setError(e.message || String(e));
    }
  }, []);

  useEffect(() => {
    api.listUsers()
      .then((u) => setUsers(Array.isArray(u) ? u : []))
      .catch(() => {});
  }, []);

  useEffect(() => { refresh(userId); }, [userId, refresh]);

  const greeting = useMemo(timeBasedGreeting, []);
  const tiles = PERSONA_TILES[userId] || [];
  const avatarLetter =
    userId === 'demo-aanya-002' ? 'A'
    : userId === 'demo-karthik-001' ? 'K'
    : (userId?.charAt(0) || '?').toUpperCase();
  const displayName =
    userId === 'demo-aanya-002' ? 'Aanya'
    : userId === 'demo-karthik-001' ? 'Karthik'
    : 'User';

  return (
    <main style={{ padding: '0 0 3rem 0' }}>
      {/* === Demo-only "Viewing as" toggle (production: doesn't exist) === */}
      <ViewingAsBar
        users={users}
        userId={userId}
        onSelect={setUser}
      />

      {/* === Spotify desktop web-player frame === */}
      <SpotifyWebFrame
        avatarLetter={avatarLetter}
        displayName={displayName}
        greeting={greeting}
        nudge={nudge}
        tiles={tiles}
        userId={userId}
        onChange={() => refresh(userId)}
      />

      <DiagnosticFooter />

      {error ? (
        <div style={{
          marginTop: '1rem',
          padding: '0.6rem 1rem',
          background: '#2a1212',
          border: '1px solid #5a2020',
          borderRadius: 8,
          color: '#fecaca',
          fontSize: '0.85rem',
        }}>{error}</div>
      ) : null}
    </main>
  );
}


// ============================================================
// Demo-only persona toggle (NOT part of the Spotify frame)
// ============================================================

function ViewingAsBar({ users, userId, onSelect }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '0.65rem',
      padding: '0.55rem 0',
      marginBottom: '0.85rem',
      borderBottom: `1px dashed ${colors.border}`,
      flexWrap: 'wrap',
    }}>
      <span style={{
        fontSize: '0.72rem',
        color: colors.textMuted,
        textTransform: 'uppercase',
        letterSpacing: '0.08em',
      }}>
        Demo only {'\u00b7'} Viewing as
      </span>
      {users.length === 0 ? (
        <span style={{ color: colors.textMuted, fontSize: '0.82rem' }}>
          (no demo users seeded - run detection from /engine)
        </span>
      ) : users.map((u) => {
        const active = u.id === userId;
        return (
          <button
            key={u.id}
            type="button"
            onClick={() => onSelect(u.id)}
            style={{
              padding: '0.35rem 0.85rem',
              borderRadius: 999,
              background: active ? '#0f2a18' : '#141414',
              color: active ? colors.spotifyGreen : colors.textSecondary,
              border: `1px solid ${active ? colors.spotifyGreen : colors.border}`,
              fontSize: '0.82rem',
              fontWeight: active ? 600 : 500,
              cursor: 'pointer',
            }}
          >
            {(u.display_name || u.id).split('(')[0].trim()}
          </button>
        );
      })}
      <span style={{
        marginLeft: 'auto',
        fontSize: '0.7rem',
        color: colors.textMuted,
        fontStyle: 'italic',
      }}>
        In production this row doesn't exist - you are whoever is signed into Spotify.
      </span>
    </div>
  );
}


// ============================================================
// SpotifyWebFrame - mirrors the desktop Spotify web player
//   - Left sidebar (~240px) with brand + nav links + Library section
//   - Top bar inside the main area with nav arrows + search + avatar
//   - Main content: greeting + nudge + Recently played grid
// ============================================================

function SpotifyWebFrame({
  avatarLetter, displayName, greeting,
  nudge, tiles, userId, onChange,
}) {
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '240px 1fr',
      gap: 8,
      background: '#000',
      borderRadius: 12,
      padding: 8,
    }}>
      <Sidebar />
      <MainArea
        avatarLetter={avatarLetter}
        displayName={displayName}
        greeting={greeting}
        nudge={nudge}
        tiles={tiles}
        userId={userId}
        onChange={onChange}
      />
    </div>
  );
}


function Sidebar() {
  return (
    <aside style={{
      background: '#000',
      borderRadius: 8,
      padding: '1.25rem 0.85rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '1rem',
    }}>
      {/* Spotify brand mark */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 10,
        color: '#fff',
        fontWeight: 700,
        fontSize: '1.15rem',
        letterSpacing: '-0.02em',
        padding: '0 0.5rem',
      }}>
        <span style={{
          display: 'inline-flex',
          alignItems: 'center', justifyContent: 'center',
          width: 30, height: 30,
          borderRadius: '50%',
          background: '#1DB954',
          color: '#0a0a0a',
          fontSize: '0.85rem',
          fontWeight: 800,
        }}>S</span>
        Spotify
      </div>

      {/* Primary nav */}
      <nav style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <SidebarItem icon={'\u2302'} label="Home" active />
        <SidebarItem icon={'\u29BF'} label="Search" />
        <SidebarItem icon={'\u2630'} label="Your Library" />
      </nav>

      <div style={{ borderTop: '1px solid #1a1a1a', paddingTop: '0.85rem', display: 'flex', flexDirection: 'column', gap: 6 }}>
        <SidebarItem icon={'+'}   label="Create Playlist" muted />
        <SidebarItem icon={'\u2661'} label="Liked Songs" muted />
      </div>

      {/* Filler "playlists" - dimmer rows for visual fidelity */}
      <div style={{
        borderTop: '1px solid #1a1a1a',
        paddingTop: '0.85rem',
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        fontSize: '0.84rem',
        color: '#6b7280',
        overflow: 'hidden',
      }}>
        <FillerPlaylist title="Discover Weekly" />
        <FillerPlaylist title="Daily Mix 1" />
        <FillerPlaylist title="Release Radar" />
        <FillerPlaylist title="On Repeat" />
        <FillerPlaylist title="Time Capsule" />
      </div>
    </aside>
  );
}

function SidebarItem({ icon, label, active = false, muted = false }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: 14,
      padding: '0.5rem 0.65rem',
      borderRadius: 6,
      color: active ? '#fff' : muted ? '#b3b3b3' : '#b3b3b3',
      fontWeight: active ? 600 : 500,
      fontSize: '0.92rem',
      background: active ? 'rgba(255,255,255,0.06)' : 'transparent',
      cursor: 'default',
    }}>
      <span style={{ fontSize: '1.1rem', opacity: 0.9, minWidth: 22, textAlign: 'center' }}>
        {icon}
      </span>
      {label}
    </div>
  );
}

function FillerPlaylist({ title }) {
  return (
    <span style={{
      padding: '0.18rem 0.65rem',
      whiteSpace: 'nowrap',
      overflow: 'hidden',
      textOverflow: 'ellipsis',
    }}>{title}</span>
  );
}


// ============================================================
// MainArea - top bar + greeting + nudge + Recently played
// ============================================================

function MainArea({ avatarLetter, displayName, greeting, nudge, tiles, userId, onChange }) {
  return (
    <section style={{
      background: 'linear-gradient(180deg, #1a1a1a 0%, #121212 200px, #121212 100%)',
      borderRadius: 8,
      padding: '0.85rem 1.5rem 1.5rem 1.5rem',
      overflow: 'hidden',
    }}>
      <TopBar avatarLetter={avatarLetter} displayName={displayName} />

      <h1 style={{
        color: '#fff',
        fontSize: '1.75rem',
        fontWeight: 700,
        letterSpacing: '-0.02em',
        margin: '1.25rem 0 1.25rem 0',
      }}>{greeting}</h1>

      <ResetRadarHomeNudge nudge={nudge} userId={userId} onChange={onChange} />

      <h2 style={{
        color: '#fff',
        fontSize: '1.15rem',
        fontWeight: 700,
        letterSpacing: '-0.01em',
        margin: '1.75rem 0 0.85rem 0',
      }}>Recently played</h2>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(6, minmax(0, 1fr))',
        gap: 16,
      }}>
        {tiles.map((t, i) => (
          <RecentTile key={i} {...t} />
        ))}
      </div>
    </section>
  );
}


function TopBar({ avatarLetter, displayName }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0.5rem 0',
    }}>
      <div style={{ display: 'flex', gap: 8 }}>
        <NavArrow direction="left" />
        <NavArrow direction="right" />
      </div>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '0.3rem 0.45rem',
        background: '#000',
        borderRadius: 999,
      }}>
        <div style={{
          width: 30, height: 30, borderRadius: '50%',
          background: '#535353',
          color: '#fff',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '0.85rem',
          fontWeight: 600,
        }}>{avatarLetter}</div>
        <span style={{
          color: '#fff',
          fontSize: '0.85rem',
          fontWeight: 600,
          paddingRight: 6,
        }}>{displayName}</span>
      </div>
    </div>
  );
}

function NavArrow({ direction }) {
  return (
    <div style={{
      width: 32, height: 32,
      borderRadius: '50%',
      background: '#0a0a0a',
      color: '#fff',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: '1.1rem',
      cursor: 'default',
      opacity: 0.55,
    }}>
      {direction === 'left' ? '\u2039' : '\u203A'}
    </div>
  );
}


// ============================================================
// Reset Radar nudge card (embedded in the home feed)
// ============================================================

function ResetRadarHomeNudge({ nudge, userId, onChange }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(null);

  if (!nudge || nudge.status !== 'pending') {
    return (
      <div style={{
        background: '#181818',
        borderLeft: `3px solid ${colors.border}`,
        borderRadius: 8,
        padding: '1rem 1.15rem',
        color: colors.textMuted,
        fontSize: '0.88rem',
      }}>
        No active Reset Radar nudge for this user right now. (Trigger the detection job from
        {' '}<Link to="/engine" style={{ color: colors.spotifyGreen }}>/engine</Link>, or
        pick a different demo user above.)
      </div>
    );
  }

  const pctRepeat = Math.round(nudge.overall_stuck_score * 100);
  const scope = nudge.suggested_scope;

  const handleAccept = async () => {
    setBusy('accept');
    try {
      await api.respondToNudge(nudge.id, 'accept');
      onChange && onChange();
      navigate(
        `/reset?user_id=${encodeURIComponent(userId)}`
        + `&scope=${encodeURIComponent(scope)}&nudge_id=${encodeURIComponent(nudge.id)}`,
      );
    } catch {
      setBusy(null);
    }
  };

  const handleDismiss = async () => {
    setBusy('dismiss');
    try {
      await api.respondToNudge(nudge.id, 'dismiss');
      onChange && onChange();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div style={{
      background: 'linear-gradient(95deg, #14241a 0%, #181818 55%, #181818 100%)',
      borderLeft: `3px solid ${colors.spotifyGreen}`,
      borderRadius: 8,
      padding: '1.1rem 1.35rem',
      display: 'flex',
      alignItems: 'center',
      gap: 18,
    }}>
      <span aria-hidden="true" style={{
        display: 'inline-flex',
        alignItems: 'center', justifyContent: 'center',
        width: 36, height: 36, borderRadius: '50%',
        background: 'rgba(29,185,84,0.18)',
        color: colors.spotifyGreen,
        flexShrink: 0,
        fontSize: '1.1rem',
      }}>{'\u25CE'}</span>
      <div style={{ flex: 1 }}>
        <div style={{
          fontFamily: 'JetBrains Mono, monospace',
          fontSize: '0.65rem',
          textTransform: 'uppercase',
          letterSpacing: '0.1em',
          color: colors.spotifyGreen,
          marginBottom: 4,
        }}>
          Reset Radar nudge {'\u00b7'} pending
        </div>
        <div style={{
          color: '#fff',
          fontSize: '1.02rem',
          fontWeight: 600,
          lineHeight: 1.35,
        }}>
          Your {scope} mix has repeated {pctRepeat}% for 3 weeks
        </div>
        <div style={{
          color: '#b3b3b3',
          fontSize: '0.88rem',
          marginTop: 4,
          lineHeight: 1.5,
        }}>
          Want a scoped reset, just for {scope}, without touching anything else?
        </div>
      </div>
      <div style={{ display: 'flex', gap: 10, flexShrink: 0 }}>
        <button
          type="button"
          onClick={handleAccept}
          disabled={busy !== null}
          style={{
            background: colors.spotifyGreen,
            color: '#0a0a0a',
            border: 'none',
            padding: '0.55rem 1.15rem',
            fontSize: '0.85rem',
            fontWeight: 700,
            borderRadius: 999,
            cursor: 'pointer',
          }}
        >
          {busy === 'accept' ? 'Opening...' : 'Try a scoped reset'}
        </button>
        <button
          type="button"
          onClick={handleDismiss}
          disabled={busy !== null}
          style={{
            background: 'transparent',
            color: '#b3b3b3',
            border: 'none',
            padding: '0.55rem 1.1rem',
            fontSize: '0.85rem',
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          {busy === 'dismiss' ? 'Dismissing...' : 'Dismiss'}
        </button>
      </div>
    </div>
  );
}


// ============================================================
// RecentTile + CoverArt - look like real Spotify playlist tiles
// ============================================================

function RecentTile({ title, subtitle, theme, sym }) {
  return (
    <div style={{
      background: '#181818',
      borderRadius: 8,
      padding: '0.85rem',
      transition: 'background 0.15s',
    }}>
      <CoverArt theme={theme} sym={sym} title={title} />
      <div style={{
        color: '#fff',
        fontSize: '0.88rem',
        fontWeight: 600,
        marginTop: '0.75rem',
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}>{title}</div>
      <div style={{
        color: '#b3b3b3',
        fontSize: '0.76rem',
        marginTop: 2,
        whiteSpace: 'nowrap',
        overflow: 'hidden',
        textOverflow: 'ellipsis',
      }}>{subtitle}</div>
    </div>
  );
}


function CoverArt({ theme, sym, title }) {
  const t = COVER_THEMES[theme] || COVER_THEMES.indiepop;
  return (
    <div style={{
      position: 'relative',
      width: '100%',
      aspectRatio: 1,
      borderRadius: 6,
      background: `linear-gradient(135deg, ${t.from} 0%, ${t.mid} 55%, ${t.to} 100%)`,
      overflow: 'hidden',
      boxShadow: '0 4px 14px rgba(0,0,0,0.45)',
    }}>
      {/* Decorative vinyl/sun ring in top right */}
      <div style={{
        position: 'absolute',
        top: '-30%',
        right: '-30%',
        width: '90%',
        height: '90%',
        borderRadius: '50%',
        background: `radial-gradient(circle at 30% 30%, rgba(255,255,255,0.18), transparent 60%)`,
      }} />
      {/* Inner faint ring */}
      <div style={{
        position: 'absolute',
        top: '15%',
        right: '15%',
        width: '70%',
        height: '70%',
        borderRadius: '50%',
        border: '1px solid rgba(255,255,255,0.12)',
      }} />
      {/* Large symbol pinned bottom-left */}
      <div style={{
        position: 'absolute',
        bottom: 8,
        left: 10,
        fontFamily: 'Georgia, serif',
        fontSize: '2.6rem',
        fontWeight: 700,
        color: t.ink,
        textShadow: '0 2px 8px rgba(0,0,0,0.35)',
        lineHeight: 1,
        letterSpacing: '-0.04em',
      }}>{sym}</div>
      {/* Small "playlist" label top-left */}
      <div style={{
        position: 'absolute',
        top: 8,
        left: 10,
        fontSize: '0.62rem',
        fontWeight: 700,
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'rgba(255,255,255,0.85)',
      }}>Playlist</div>
      {/* No title overlay - title shows below the cover */}
    </div>
  );
}


// ============================================================
// Subtle footer link to the diagnostic view
// ============================================================

function DiagnosticFooter() {
  return (
    <div style={{
      margin: '1rem 0 0 0',
      textAlign: 'center',
      color: colors.textMuted,
      fontSize: '0.75rem',
    }}>
      <Link
        to="/engine"
        style={{
          color: colors.textMuted,
          textDecoration: 'none',
          borderBottom: `1px dashed ${colors.border}`,
          paddingBottom: 1,
        }}
        title="Behind-the-scenes view: stuck-score timeline, per-dimension grid, GH Action run history"
      >
        Engine diagnostics {'\u2192'}
      </Link>
    </div>
  );
}
