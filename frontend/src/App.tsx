import { useState } from "react";
import { ErrorAlert, StatusBanner } from "./components";
import { Details, Evidence, Home, Recommendations, Roadmap, SkillGap, SkillsEvidence, UserProfile } from "./pages";
import * as api from "./services/api";
import type { AnalysisResponse } from "./types/api";

const PAGES = ["Home", "User Profile", "Skills & Evidence", "Career Recommendations", "Skill Gap",
  "Learning Roadmap", "Evidence / Sources", "Analysis Details"] as const;
type Page = typeof PAGES[number];

export default function App() {
  const [page, setPage] = useState<Page>("Home");
  const [userId, setUserId] = useState<number | null>(null);
  const [result, setResult] = useState<AnalysisResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [healthText, setHealthText] = useState("");

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
      onHealth={() => guard(api.health).then(h => setHealthText(h ? "Backend reachable." : "Backend check failed."))}
      onCreate={(e, n) => guard(() => api.createUser(e, n)).then(u => { if (u) setUserId(u.user_id); })}
      onSelect={setUserId}
      onProfile={t => userId !== null && run(() => api.analyzeProfile(userId, t))}
      onCv={(f, t) => userId !== null && run(() => api.analyzeCv(userId, f, t))} />
  ) : !result ? <p>No analysis yet. Run one from Home.</p>
    : page === "User Profile" ? <UserProfile r={result} />
    : page === "Skills & Evidence" ? <SkillsEvidence r={result} />
    : page === "Career Recommendations" ? <Recommendations r={result} busy={busy} onTarget={id => run(() => api.analyzeProfile(result.user_id, id))} />
    : page === "Skill Gap" ? <SkillGap r={result} />
    : page === "Learning Roadmap" ? <Roadmap r={result} />
    : page === "Evidence / Sources" ? <Evidence r={result} />
    : <Details r={result} />;

  return (
    <>
      <header><h1>Career Intelligence (research prototype)</h1>
        <nav aria-label="Pages">{PAGES.map(p => <button key={p} aria-current={p === page ? "page" : undefined} onClick={() => setPage(p)}>{p}</button>)}</nav></header>
      <main>
        {error !== null && <ErrorAlert error={error} />}
        {result && page !== "Home" && page !== "Analysis Details" && <StatusBanner status={result.final_status} revisions={result.revision_count} />}
        <h2>{page}</h2>{body}
      </main>
    </>
  );
}
