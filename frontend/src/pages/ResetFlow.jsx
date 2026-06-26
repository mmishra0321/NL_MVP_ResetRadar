/**
 * ResetFlow - the four-step reset experience.
 *
 *   step = 'pick'     -> ScopePicker is rendered; clicking Generate ->
 *                        POST /reset/sessions, then step = 'playlist'
 *   step = 'loading'  -> shown during the Groq round-trip
 *   step = 'playlist' -> ResetPlaylistView with the 20 tracks; the
 *                        "Skip to outcome" affordance shows
 *                        KeepOrRevertCard pre-decision
 *   step = 'decide'   -> KeepOrRevertCard with Keep / Revert buttons
 *   step = 'done'     -> KeepOrRevertCard outcome with before/after
 *
 * If the URL contains `?scope=...&user_id=...&nudge_id=...` (the form
 * NudgeCard navigates to), the picker pre-selects that scope.
 *
 * If the URL is /reset/:sessionId the page hydrates that existing
 * session and skips picker/loading.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { api } from '../api/client.js';
import { colors } from '../theme.js';
import ScopePicker from '../components/ScopePicker.jsx';
import ResetPlaylistView from '../components/ResetPlaylistView.jsx';
import KeepOrRevertCard from '../components/KeepOrRevertCard.jsx';
import useDemoUser from '../hooks/useDemoUser.js';


export default function ResetFlow() {
  const navigate = useNavigate();
  const { sessionId: sessionIdParam } = useParams();
  const [searchParams] = useSearchParams();
  const { userId } = useDemoUser();

  const suggestedScope = searchParams.get('scope');                       // from NudgeCard accept
  const queryUserId = searchParams.get('user_id') || userId;

  const [step, setStep] = useState(sessionIdParam ? 'playlist' : 'pick');
  const [session, setSession] = useState(null);
  const [outcome, setOutcome] = useState(null);
  const [error, setError] = useState(null);

  // Hydrate an existing session from the URL.
  useEffect(() => {
    if (!sessionIdParam) return;
    let cancelled = false;
    setStep('loading');
    api.getResetSession(sessionIdParam)
      .then((data) => {
        if (cancelled) return;
        setSession(data);
        if (data && data.decision) {
          setOutcome({
            session_id: data.id,
            before_stuck_score: data.before_stuck_score ?? null,
            after_stuck_score: data.after_stuck_score ?? null,
            decision: data.decision,
          });
          setStep('done');
        } else {
          setStep('playlist');
        }
      })
      .catch((e) => {
        if (cancelled) return;
        setError(`Could not load session ${sessionIdParam}: ${e.message || e}`);
        setStep('pick');
      });
    return () => { cancelled = true; };
  }, [sessionIdParam]);

  const handleGenerate = useCallback(async ({ scope, intent }) => {
    setError(null);
    setStep('loading');
    try {
      const created = await api.createResetSession({
        userId: queryUserId,
        scopeDimensions: [scope],
        freeTextIntent: intent,
      });
      setSession(created);
      setStep('playlist');
      navigate(`/reset/${created.id}`, { replace: true });
    } catch (e) {
      setError(e.message || String(e));
      setStep('pick');
    }
  }, [queryUserId, navigate]);

  const handleSkipToOutcome = useCallback(() => {
    setStep('decide');
  }, []);

  const handleKeep   = useCallback(() => decide('keep'),   /* eslint-disable-line react-hooks/exhaustive-deps */ [session]);
  const handleRevert = useCallback(() => decide('revert'), /* eslint-disable-line react-hooks/exhaustive-deps */ [session]);

  const decide = useCallback(async (decision) => {
    if (!session) return;
    setError(null);
    try {
      const result = await api.decideResetSession(session.id, decision);
      setOutcome(result);
      setStep('done');
    } catch (e) {
      setError(e.message || String(e));
    }
  }, [session]);

  const beforeScore = useMemo(() => {
    if (outcome && outcome.before_stuck_score != null) return outcome.before_stuck_score;
    if (session && session.before_stuck_score != null) return session.before_stuck_score;
    return null;
  }, [outcome, session]);

  return (
    <main>
      <header style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        flexWrap: 'wrap',
        gap: '0.75rem',
      }}>
        <div>
          <h1 style={{ margin: 0, fontSize: '1.5rem' }}>Reset session</h1>
          <div style={{ color: colors.textSecondary, fontSize: '0.92rem', marginTop: 4 }}>
            One scope at a time. 20-track sandboxed trial. Keep or revert at the end.
          </div>
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={() => navigate('/')}
          style={{ fontSize: '0.85rem' }}
        >
          &larr; Back to dashboard
        </button>
      </header>

      {error ? (
        <div style={errorStyle}>{error}</div>
      ) : null}

      <div style={{ display: 'grid', gap: '1.25rem', marginTop: '1.5rem' }}>
        {step === 'pick' ? (
          <ScopePicker
            suggestedScope={suggestedScope}
            onGenerate={handleGenerate}
          />
        ) : null}

        {step === 'loading' ? (
          <LoadingPane />
        ) : null}

        {(step === 'playlist' || step === 'decide' || step === 'done') && session ? (
          <ResetPlaylistView
            session={session}
            onSkipToOutcome={step === 'playlist' ? handleSkipToOutcome : null}
          />
        ) : null}

        {step === 'decide' ? (
          <KeepOrRevertCard
            beforeScore={beforeScore}
            onKeep={handleKeep}
            onRevert={handleRevert}
          />
        ) : null}

        {step === 'done' && outcome ? (
          <KeepOrRevertCard outcome={outcome} beforeScore={beforeScore} />
        ) : null}

        {step === 'done' ? (
          <div style={{ display: 'flex', gap: '0.75rem' }}>
            <button
              type="button"
              className="btn-primary"
              onClick={() => navigate('/')}
            >
              Back to dashboard
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setSession(null);
                setOutcome(null);
                setStep('pick');
                navigate(`/reset${suggestedScope ? `?scope=${suggestedScope}` : ''}`, { replace: true });
              }}
            >
              Start a new reset
            </button>
          </div>
        ) : null}
      </div>
    </main>
  );
}


function LoadingPane() {
  return (
    <div
      style={{
        background: colors.surfaceElevated,
        border: `1px solid ${colors.border}`,
        borderRadius: 12,
        padding: '2rem',
        textAlign: 'center',
      }}
    >
      <div style={{
        fontFamily: 'JetBrains Mono, monospace',
        fontSize: '0.85rem',
        color: colors.spotifyGreen,
        marginBottom: 8,
        letterSpacing: '0.08em',
      }}>
        Generating...
      </div>
      <div style={{ color: colors.textSecondary, fontSize: '0.92rem' }}>
        Filtering the candidate pool by scope, then asking the LLM to rank the
        top 20 and write a per-track "why". Usually 5-30 seconds in mock mode.
      </div>
    </div>
  );
}


const errorStyle = {
  marginTop: '1rem',
  padding: '0.75rem 1rem',
  background: '#2a1212',
  border: '1px solid #5a2020',
  borderRadius: 8,
  color: '#fecaca',
  fontSize: '0.9rem',
};
