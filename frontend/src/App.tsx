import { useEffect, useState } from "react";
import { EmptyState, ErrorAlert, Icon, StatusBanner } from "./components";
import type { IconName } from "./components";
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

const NAV_GROUPS: ReadonlyArray<{
  label: string;
  items: ReadonlyArray<{ page: Page; icon: IconName }>;
}> = [
  {
    label: "Workspace",
    items: [
      { page: "Home", icon: "home" },
      { page: "User Profile", icon: "user" },
      { page: "Career Recommendations", icon: "target" },
    ],
  },
  {
    label: "Analysis",
    items: [
      { page: "Skills & Evidence", icon: "layers" },
      { page: "Skill Gap", icon: "chart" },
      { page: "Learning Roadmap", icon: "map" },
    ],
  },
  {
    label: "Transparency",
    items: [
      { page: "Evidence / Sources", icon: "database" },
      { page: "Analysis Details", icon: "shield" },
    ],
  },
];

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
  const [navOpen, setNavOpen] = useState(false);

  useEffect(() => {
    setCareersLoading(true);
    setCareersError(null);
    api.listCareers()
      .then(setCareers)
      .catch((e) => setCareersError(e?.message || "Failed to load careers"))
      .finally(() => setCareersLoading(false));
  }, []);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setNavOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

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
    <EmptyState
      title="No analysis yet"
      description="Run an analysis from the Home page to view results."
      action={
        <button className="btn-primary" onClick={() => setPage("Home")}>
          <Icon name="sparkles" /> Start an analysis
        </button>
      }
    />
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

  const navigate = (next: Page) => {
    setPage(next);
    setNavOpen(false);
  };

  return (
    <div className="app-shell">
      <button
        type="button"
        className={`sidebar-overlay ${navOpen ? "is-open" : ""}`}
        aria-label="Close navigation"
        onClick={() => setNavOpen(false)}
        tabIndex={navOpen ? 0 : -1}
      />

      <aside id="app-sidebar" className={`sidebar ${navOpen ? "is-open" : ""}`} aria-label="Application sidebar">
        <div className="sidebar-brand">
          <span className="brand-mark"><Icon name="sparkles" /></span>
          <div>
            <span className="brand-name">Career Intelligence</span>
            <span className="brand-sub">Research prototype</span>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="Main navigation">
          <button className="btn-primary sidebar-cta" onClick={() => navigate("Home")}>
            <Icon name="sparkles" /> New analysis
          </button>

          {NAV_GROUPS.map(group => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group-label">{group.label}</span>
              {group.items.map(item => (
                <button
                  key={item.page}
                  type="button"
                  className="nav-button"
                  aria-current={item.page === page ? "page" : undefined}
                  onClick={() => navigate(item.page)}
                  disabled={item.page !== "Home" && !result}
                >
                  <Icon name={item.icon} />
                  <span>{item.page}</span>
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-user">
            <span className="avatar">{userId !== null ? "CI" : "?"}</span>
            <div className="sidebar-user-copy">
              <span className="sidebar-user-label">Active user</span>
              <span className="sidebar-user-value">{userId !== null ? `#${userId}` : "Not selected"}</span>
            </div>
          </div>
          <p className="sidebar-note">Results live in browser memory only and reset on reload.</p>
        </div>
      </aside>

      <div className="app-main">
        <header className="mobile-bar">
          <button
            type="button"
            className="icon-button"
            aria-label="Open navigation"
            aria-controls="app-sidebar"
            aria-expanded={navOpen}
            onClick={() => setNavOpen(true)}
          >
            <Icon name="menu" />
          </button>
          <div className="mobile-brand">
            <span className="brand-mark"><Icon name="sparkles" /></span>
            <span>Career Intelligence</span>
          </div>
          <span className={`chip ${userId !== null ? "primary" : ""}`}>
            {userId !== null ? `#${userId}` : "No user"}
          </span>
        </header>

        <main className="content">
          {error !== null && <ErrorAlert error={error} />}
          {result && page !== "Home" && page !== "Analysis Details" && (
            <StatusBanner status={result.final_status} revisions={result.revision_count} />
          )}
          {page !== "Home" && (
            <div className="page-heading">
              <span className="eyebrow"><Icon name="activity" /> Analysis workspace</span>
              <h1>{page}</h1>
              <p>{pageDescriptions[page]}</p>
            </div>
          )}
          {body}
        </main>
      </div>
    </div>
  );
}
