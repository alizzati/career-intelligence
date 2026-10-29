import { useEffect, useState } from "react";
import { ErrorAlert, StatusBanner } from "./components";
import { Details, Evidence, Home, Recommendations, Roadmap, SkillGap, SkillsEvidence, UserProfile } from "./pages";
import * as api from "./services/api";
import type { AnalysisResponse } from "./types/api";

const PAGES = [
  "Home", 
  "User Profile", 
  "Career Recommendations", 
  "Skills & Evidence", 
  "Skill Gap",
  "Learning Roadmap", 
  "Evidence / Sources", 
  "Analysis Details"
] as const;
type Page = typeof PAGES[number];

export default function App() {
  const [page, setPage] = useState<Page>("Home");
  const [userId, setUserId] = useState<number | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [healthText, setHealthText] = useState("");
  const [careers, setCareers] = useState<Array<{ career_id: string; canonical_name: string; domain?: string }>>([]);
  const [careersLoading, setCareersLoading] = useState(false);
  const [careersError, setCareersError] = useState<string | null>(null);

  useEffect(() => {
    setCareersLoading(true);
    setCareersError(null);
    api.listCareers()
      .then(setCareers)
      .catch((e) => setCareersError(e?.message || "Failed to load careers"))
      .finally(() => setCareersLoading(false));
  }, []);

  async function run(job: () => Promise<AnalysisResponse>) {
    setBusy(true); setError(null);
    try { setResult(await job()); setPage("Career Recommendations"); } // HTTP 200 even if unverified
    catch (e) { setError(e); } finally { setBusy(false); }
  }
  async function guard<T>(job: () => Promise<T>): Promise<T | undefined> {
    setBusy(true); setError(null);
    try { return await job(); } catch (e) { setError(e); } finally { setBusy(false); }
  }

  const body = page === "Home" ? (
    <Home userId={userId} busy={busy} healthText={healthText}
      onHealth={() => guard(api.health).then(h => setHealthText(h ? "Backend reachable" : "Backend check failed"))}
      onCreate={async (e, n) => {
        const u = await api.createUser(e, n);
        if (u) setUserId(u.user_id);
        return u;
      }}
      onSelectByEmail={async (email) => {
        const u = await api.getUserByEmail(email);
        if (u) setUserId(u.user_id);
        return u;
      }}
      onProfile={t => userId !== null && run(() => api.analyzeProfile(userId, t))}
      onCv={(f, t) => userId !== null && run(() => api.analyzeCv(userId, f, t))}
      careers={careers}
      careersLoading={careersLoading}
      careersError={careersError} />
  ) : !result ? (
    <div className="card">
      <div style={{ textAlign: 'center', padding: '2rem' }}>
        <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--fg)' }}>No Analysis Yet</h3>
        <p style={{ margin: '0', color: 'var(--fg-muted)' }}>Run an analysis from the Home page to view results.</p>
      </div>
    </div>
  )
    : page === "User Profile" ? <UserProfile r={result} />
    : page === "Skills & Evidence" ? <SkillsEvidence r={result} />
    : page === "Career Recommendations" ? <Recommendations r={result} busy={busy} onTarget={id => run(() => api.analyzeProfile(result.user_id, id))} />
    : page === "Skill Gap" ? <SkillGap r={result} />
    : page === "Learning Roadmap" ? <Roadmap r={result} />
    : page === "Evidence / Sources" ? <Evidence r={result} />
    : <Details r={result} />;

  const pageDescriptions: Record<Page, string> = {
    "Home": "Get started with career analysis",
    "User Profile": "View profile and analysis metadata",
    "Career Recommendations": "Explore AI-powered career matches",
    "Skills & Evidence": "Review skills and supporting evidence",
    "Skill Gap": "Understand skill gaps for your target career",
    "Learning Roadmap": "Personalized learning plan",
    "Evidence / Sources": "Knowledge base sources and provenance",
    "Analysis Details": "Verification and technical details"
  };

  return (
    <>
      <header className="app-header">
        <div className="header-content">
          <div className="brand">
            <div className="brand-icon">CI</div>
            <div className="brand-text">
              <h1>Career Intelligence System</h1>
              <p>AI-Powered Career Guidance for IT Graduates</p>
            </div>
          </div>
          <div className="nav-container">
            <nav aria-label="Main navigation">
              {PAGES.map(p => (
                <button 
                  key={p} 
                  className="nav-button"
                  aria-current={p === page ? "page" : undefined} 
                  onClick={() => setPage(p)}
                  disabled={p !== "Home" && !result}
                >
                  {p}
                </button>
              ))}
            </nav>
          </div>
        </div>
      </header>
      <main>
        {error !== null && <ErrorAlert error={error} />}
        {result && page !== "Home" && page !== "Analysis Details" && (
          <StatusBanner status={result.final_status} revisions={result.revision_count} />
        )}
        {page !== "Home" && (
          <div className="page-header">
            <h2>{page}</h2>
            <p>{pageDescriptions[page]}</p>
          </div>
        )}
        {body}
      </main>
    </>
  );
}
