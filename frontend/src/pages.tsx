import { useState } from "react";
import { CATEGORY, Section, StatusBanner, Tag, Unavailable, pct } from "./components";
import type { AnalysisResponse, SkillGapItem, SkillRef } from "./types/api";

export interface HomeProps {
  userId: number | null; busy: boolean; healthText: string;
  onHealth: () => void; onCreate: (email: string, name: string) => void;
  onSelect: (id: number) => void; onProfile: (target?: string) => void; onCv: (f: File, target?: string) => void;
}

export function Home(p: HomeProps) {
  const [email, setEmail] = useState(""); const [name, setName] = useState("");
  const [idText, setIdText] = useState(""); const [target, setTarget] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const t = target.trim() || undefined;
  return (
    <>
      <p>Research prototype. Results are held in browser memory only and are lost on reload.</p>
      <div className="card"><button onClick={p.onHealth}>Check backend</button> <span role="status">{p.healthText}</span></div>
      <Section title="1. Create or select a user">
        <div className="card">
          <label>Email <input type="email" value={email} onChange={e => setEmail(e.target.value)} /></label>
          <label>Full name <input value={name} onChange={e => setName(e.target.value)} /></label>
          <button disabled={p.busy || !email || !name} onClick={() => p.onCreate(email, name)}>Create user</button>
          <hr />
          <label>Existing user ID <input inputMode="numeric" value={idText} onChange={e => setIdText(e.target.value)} /></label>
          <button disabled={!/^[1-9]\d*$/.test(idText)} onClick={() => p.onSelect(Number(idText))}>Use this user</button>
          <p>Active user: {p.userId ?? "none"}</p>
        </div>
      </Section>
      <Section title="2. Run analysis">
        <div className="card">
          <label>Target career ID (optional; blank = top-ranked; must be a canonical ID)
            <input value={target} onChange={e => setTarget(e.target.value)} /></label>
          <button disabled={p.busy || p.userId === null} onClick={() => p.onProfile(t)}>Analyze stored profile</button>
          <hr />
          <label>CV file (PDF, DOCX or TXT) <input type="file" accept=".pdf,.docx,.txt" onChange={e => setFile(e.target.files?.[0] ?? null)} /></label>
          <button disabled={p.busy || p.userId === null || !file} onClick={() => file && p.onCv(file, t)}>Upload CV and analyze</button>
          {p.busy && <p role="status">Analyzing… this can take a while (several LLM calls).</p>}
        </div>
      </Section>
    </>
  );
}

export function UserProfile({ r }: { r: AnalysisResponse }) {
  return (
    <>
      <Unavailable what="Stored profile (education, experience, projects, certifications)"
        why="The API has no profile-read endpoint, by design, to avoid exposing personal data without access control." />
      <Section title="Run metadata returned by the API">
        <ul>
          <li>User ID: {r.user_id}; source: {r.source}</li>
          {r.document && <li>Document: {r.document.format}, {r.document.size_bytes} bytes, {r.document.page_count ?? "n/a"} page(s), {r.document.character_count} characters (filename not returned)</li>}
          {r.redaction && <li>PII redaction (best-effort): {r.redaction.replacement_count} replacement(s); types: {r.redaction.detected_types.join(", ") || "none"}</li>}
          {r.profile_extraction && <li>Extraction: {r.profile_extraction.skills_persisted} skill claim(s) processed, {r.profile_extraction.evidence_persisted} evidence row(s) processed</li>}
        </ul>
      </Section>
    </>
  );
}

const Row = ({ i }: { i: SkillGapItem }) => (
  <tr><td>{i.canonical_name} <span className="muted">({i.skill_id})</span></td><td>{i.evidence_class}</td><td>{i.kb_confidence}</td>
    <td>{i.matched_user_claim ? `“${i.matched_user_claim.claimed_skill}”, proficiency (self-reported): ${i.matched_user_claim.proficiency ?? "not given"}, evidence rows: ${i.matched_user_claim.evidence_count}` : "—"}</td></tr>
);

export function SkillsEvidence({ r }: { r: AnalysisResponse }) {
  const g = r.skill_gap?.skill_gap;
  if (!g) return <Unavailable what="Skills & evidence" why="No skill-gap result in this run." />;
  const groups: [keyof typeof CATEGORY, SkillGapItem[]][] = [
    ["matched_evidenced", g.matched_evidenced], ["matched_claimed_only", g.matched_claimed_only], ["missing", g.missing]];
  return (
    <>
      <p>Skills relative to <strong>{g.canonical_name}</strong>. Proficiency is self-reported and is never compared against a requirement.</p>
      {groups.map(([cat, items]) => (
        <Section key={cat} title={CATEGORY[cat].text}>
          {items.length === 0 ? <p className="muted">None.</p> :
            <table><thead><tr><th>Required skill</th><th>KB class</th><th>KB confidence</th><th>User claim</th></tr></thead>
              <tbody>{items.map(i => <Row key={i.skill_id} i={i} />)}</tbody></table>}
        </Section>
      ))}
      <Section title={CATEGORY.unmatched.text}>
        {g.unmatched_user_claims.length === 0 ? <p className="muted">None.</p> :
          <ul>{g.unmatched_user_claims.map(u => <li key={u.user_skill_id}>“{u.claimed_skill}” (evidence rows: {u.evidence_count}). {u.note}</li>)}</ul>}
      </Section>
      <Unavailable what="Evidence details (type, description, URL)" why="The API returns only evidence counts per claim." />
    </>
  );
}

const names = (xs: SkillRef[]) => xs.length ? xs.map(s => s.canonical_name).join(", ") : "none";
export function Recommendations({ r, busy, onTarget }: { r: AnalysisResponse; busy: boolean; onTarget: (id: string) => void }) {
  if (!r.recommendations.length) return <Unavailable what="Recommendations" why="The run returned none." />;
  return (
    <>
      <p>All canonical careers, ranked by the deterministic fit score. Target career for gap analysis: <strong>{r.target_career_id ?? "n/a"}</strong>.</p>
      {r.recommendations.map((c, n) => (
        <article className="card" key={c.career_id}>
          <h3>{n + 1}. {c.canonical_name} <span className="muted">({c.career_id}, {c.domain})</span></h3>
          <label>Fit score: {pct(c.fit_score)}<meter min={0} max={1} value={c.fit_score} /></label>
          <p><Tag cat="matched_evidenced" /> {names(c.matched_skills)}</p>
          <p><Tag cat="matched_claimed_only" /> {names(c.claimed_only_skills)}</p>
          <p><Tag cat="missing" /> {names(c.missing_skills_preview)}</p>
          <p>{c.reasoning} <span className="muted">[reasoning source: {c.reasoning_source}]</span></p>
          <button disabled={busy || c.career_id === r.target_career_id} onClick={() => onTarget(c.career_id)}>
            {c.career_id === r.target_career_id ? "Current target" : "Re-run with this target"}</button>
        </article>
      ))}
    </>
  );
}

export function SkillGap({ r }: { r: AnalysisResponse }) {
  const a = r.skill_gap;
  if (!a) return <Unavailable what="Skill gap" why="No skill-gap result in this run." />;
  const g = a.skill_gap, n = a.narrative;
  return (
    <>
      <h2>{g.canonical_name} <span className="muted">({g.career_id})</span>: fit {pct(g.fit_score)}</h2>
      <p>Counts: evidenced {g.matched_evidenced.length}, claimed-only {g.matched_claimed_only.length}, missing {g.missing.length}, unmatched claims {g.unmatched_user_claims.length}.</p>
      <Section title="Explanation">
        <p className="muted">Narrative source: {a.narrative_source}. The deterministic classification is authoritative.</p>
        <p>{n.summary}</p>
        {[...n.strengths, ...n.claimed_only_observations, ...n.missing_skill_observations].map((o, i) => <p key={i}>{o.text}</p>)}
        {n.unmatched_claim_observations.map((o, i) => <p key={`u${i}`}>{o.text}</p>)}
        <p>{n.conclusion}</p>
        {a.llm_error && <p className="muted">An LLM step failed; details omitted by the API.</p>}
        {a.validation_notes.length > 0 && <details><summary>Validation notes ({a.validation_notes.length})</summary><ul>{a.validation_notes.map((x, i) => <li key={i}>{x}</li>)}</ul></details>}
      </Section>
      <p>See “Skills & Evidence” for the per-skill breakdown.</p>
    </>
  );
}

export function Roadmap({ r }: { r: AnalysisResponse }) {
  const m = r.roadmap;
  if (!m) return <Unavailable what="Roadmap" why="No roadmap in this run." />;
  return (
    <>
      <p>{m.summary} <span className="muted">[source: {m.narrative_source}]</span></p>
      <p className="muted">Focus items follow the KB order and are not ranked. The KB provides no courses, resources, prerequisites or proficiency targets.</p>
      {m.items.length === 0 ? <p>No outstanding items.</p> : <ol>
        {m.items.map(i => (
          <li key={i.skill_id}><strong>{i.canonical_name}</strong> <span className="muted">({i.skill_id})</span>{" "}
            <Tag cat={i.gap_status} /> Action: {i.learning_action === "add_linked_evidence" ? "add linked evidence" : "develop skill"}.
            <div className="muted">KB basis: {i.knowledge_base_basis || "Evidence unavailable"}</div></li>
        ))}</ol>}
    </>
  );
}

export function Evidence({ r }: { r: AnalysisResponse }) {
  const ids = new Set(r.verification?.checks.flatMap(c => c.source_ids) ?? []);
  return (
    <>
      <Unavailable what="Source/provenance records (SKKNI, KBJI, O*NET, ESCO)" why="No API endpoint resolves provenance. Only the IDs below are available, unresolved." />
      <Section title="Knowledge-base basis for roadmap items">
        {r.roadmap?.items.length ? <ul>{r.roadmap.items.map(i => <li key={i.skill_id}><strong>{i.canonical_name}</strong>: {i.knowledge_base_basis || "Evidence unavailable"}</li>)}</ul>
          : <p className="muted">Evidence unavailable.</p>}
      </Section>
      <Section title="Record IDs referenced by verification checks">
        {ids.size ? <p>{[...ids].join(", ")}</p> : <p className="muted">Evidence unavailable.</p>}
      </Section>
    </>
  );
}

export function Details({ r }: { r: AnalysisResponse }) {
  const v = r.verification, w = r.recommendations[0]?.score_breakdown.weights_used;
  return (
    <>
      <StatusBanner status={r.final_status} revisions={r.revision_count} />
      <p>Verified flag: {String(r.verified)}; target: {r.target_career_id ?? "n/a"}; narrative sources: skill gap {r.skill_gap?.narrative_source ?? "n/a"}, roadmap {r.roadmap?.narrative_source ?? "n/a"}.</p>
      <Unavailable what="Analysis ID / history / timestamps / model version" why="Not returned by the API; persistence and logging belong to Step 16." />
      {w && <Section title="Scoring weights used"><pre>{JSON.stringify(w, null, 2)}</pre></Section>}
      {!v ? <Unavailable what="Verification" why="No verification result in this run." /> : (
        <Section title={`Verification: ${v.status}`}>
          <table><thead><tr><th>Check</th><th>Status</th><th>Reason</th><th>Source IDs</th></tr></thead>
            <tbody>{v.checks.map((c, i) => <tr key={i}><td>{c.check}</td><td>{c.status}</td><td>{c.reason}</td><td>{c.source_ids.length > 5 ? `${c.source_ids.length} IDs` : c.source_ids.join(", ") || "—"}</td></tr>)}</tbody></table>
          {v.unsupported_claims.length > 0 && <><h3>Unsupported claims</h3><ul>{v.unsupported_claims.map((c, i) => <li key={i}>[{c.component}] {c.claim}</li>)}</ul></>}
          {v.required_revision.length > 0 && <><h3>Required revision</h3><ul>{v.required_revision.map((x, i) => <li key={i}>{x}</li>)}</ul></>}
          {v.llm_error && <p className="muted">A semantic-review LLM step failed; details omitted by the API.</p>}
        </Section>)}
    </>
  );
}
