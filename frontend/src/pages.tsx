import { useState } from "react";
import { CATEGORY, Card, Icon, MetaRow, ProgressRing, Section, StatCard, StatusBanner, Tag, Unavailable, pct } from "./components";
import type { AnalysisResponse, SkillGapItem, SkillRef } from "./types/api";

export interface HomeProps {
  userId: number | null; busy: boolean; healthText: string;
  onHealth: () => void;
  onCreate: (email: string, name: string) => Promise<any>;
  onSelectByEmail: (email: string) => Promise<any>;
  onProfile: (target?: string) => void;
  onCv: (f: File, target?: string) => void;
  careers: Array<{ career_id: string; canonical_name: string; domain?: string }>;
  careersLoading: boolean;
  careersError: string | null;
}

export function Home(p: HomeProps) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [existingEmail, setExistingEmail] = useState("");
  const [target, setTarget] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [createError, setCreateError] = useState<string | null>(null);
  const [createSuccess, setCreateSuccess] = useState<string | null>(null);
  const [existingError, setExistingError] = useState<string | null>(null);
  const [existingSuccess, setExistingSuccess] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [selecting, setSelecting] = useState(false);
  const t = target.trim() || undefined;

  async function handleCreate() {
    setCreateError(null);
    setCreateSuccess(null);
    setCreating(true);
    try {
      const res = await p.onCreate(email, name);
      setCreateSuccess("Account created successfully.");
    } catch (e: any) {
      const msg = e?.message || String(e);
      if (e?.code === "user_exists" || msg.toLowerCase().includes("already exists")) {
        setCreateError("An account with this email already exists. Please use the existing account option below.");
      } else {
        setCreateError(msg);
      }
    } finally {
      setCreating(false);
    }
  }

  async function handleSelectExisting() {
    setExistingError(null);
    setExistingSuccess(null);
    setSelecting(true);
    try {
      await p.onSelectByEmail(existingEmail);
      setExistingSuccess("Existing account selected.");
    } catch (e: any) {
      const msg = e?.message || String(e);
      if (e?.status === 404 || e?.code === "user_not_found") {
        setExistingError("No account found with this email. Please create a new account.");
      } else {
        setExistingError(msg);
      }
    } finally {
      setSelecting(false);
    }
  }

  return (
    <>
      <section className="hero">
        <div>
          <span className="eyebrow"><Icon name="sparkles" /> AI career guidance</span>
          <h2>Welcome to Career Intelligence</h2>
          <p>
            Discover your ideal IT career path with AI-powered analysis. Get personalized recommendations,
            identify skill gaps, and receive a tailored learning roadmap based on Indonesian occupational standards.
          </p>
          <div className="hero-note">
            <Icon name="info" />
            <span>Research prototype — results are held in browser memory only and are lost on reload</span>
          </div>
        </div>
        <div className="hero-badge" aria-hidden="true">
          <Icon name="target" />
        </div>
      </section>

      <Card title="System status" subtitle="Check backend connectivity">
        <div className="status-line">
          <button className="btn-primary" onClick={p.onHealth}>
            <Icon name="activity" /> Check backend
          </button>
          {p.healthText && (
            <span role="status" className={`health-pill ${p.healthText.includes('reachable') ? "ok" : "bad"}`}>
              <Icon name={p.healthText.includes('reachable') ? "check" : "close"} /> {p.healthText}
            </span>
          )}
        </div>
      </Card>

      <Section title="Step 1 · User setup">
        <div className="split-grid">
          <Card title="Create new account" subtitle="Primary workflow">
            <div className="form-grid">
              <label>
                Email address
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="your.email@example.com"
                  className={createError && createError.includes('email') ? "input-error" : undefined}
                />
              </label>
              {createError && createError.toLowerCase().includes('email') && (
                <div className="field-error">{createError}</div>
              )}
              <label>
                Full name
                <input value={name} onChange={e => setName(e.target.value)} placeholder="Enter your full name" />
              </label>
              <button className="btn-primary" disabled={creating || p.busy || !email || !name} onClick={handleCreate}>
                {creating ? 'Creating...' : 'Create account'}
              </button>
              {createSuccess && <div className="field-success">✓ {createSuccess}</div>}
              {createError && !createError.toLowerCase().includes('email') && <div className="field-error">{createError}</div>}
            </div>
          </Card>

          <Card title="Use existing account" subtitle="Secondary workflow">
            <div className="form-grid">
              <label>
                Email address
                <input
                  type="email"
                  value={existingEmail}
                  onChange={e => setExistingEmail(e.target.value)}
                  placeholder="your.email@example.com"
                />
              </label>
              <button disabled={selecting || p.busy || !existingEmail} onClick={handleSelectExisting}>
                {selecting ? 'Looking up...' : 'Continue with this account'}
              </button>
              {existingSuccess && <div className="field-success">✓ {existingSuccess}</div>}
              {existingError && <div className="field-error">{existingError}</div>}
              <div className="callout">
                <Icon name="user" />
                <div>
                  <strong>Active user:</strong>{" "}
                  {p.userId ? <span className="chip primary">#{p.userId}</span> : <span className="muted">None selected</span>}
                </div>
              </div>
            </div>
          </Card>
        </div>
      </Section>

      <Section title="Step 2 · Run career analysis">
        <Card title="Analyze your profile" subtitle={p.userId === null ? "Please select or create a user first" : "Choose your analysis method"}>
          <div className="form-stack">
            <label className="field">
              Target career (optional)
              <select value={target} onChange={e => setTarget(e.target.value)}>
                <option value="">Choose a target career (optional)</option>
                {p.careersLoading && <option value="" disabled>Loading careers...</option>}
                {p.careersError && <option value="" disabled>Failed to load careers</option>}
                {!p.careersLoading && !p.careersError && p.careers.map(c => (
                  <option key={c.career_id} value={c.career_id}>{c.canonical_name}</option>
                ))}
              </select>
              <span>Leave blank to get automatic recommendations</span>
            </label>

            <div className="option-block">
              <div className="option-heading">
                <span className="option-index">A</span>
                <div>
                  <h4>Analyze stored profile</h4>
                  <p>Use previously stored profile data for analysis.</p>
                </div>
              </div>
              <div>
                <button className="btn-primary" disabled={p.busy || p.userId === null} onClick={() => p.onProfile(t)}>
                  <Icon name="activity" /> {p.busy ? 'Analyzing...' : 'Analyze stored profile'}
                </button>
              </div>
            </div>

            <div className="option-divider" />

            <div className="option-block">
              <div className="option-heading">
                <span className="option-index">B</span>
                <div>
                  <h4>Upload CV</h4>
                  <p>Upload your CV/resume for automatic profile extraction.</p>
                </div>
              </div>
              <div className="form-grid">
                <label className="field">
                  CV file
                  <input type="file" accept=".pdf,.docx,.txt" onChange={e => setFile(e.target.files?.[0] ?? null)} />
                  <span>Supported formats: PDF, DOCX, TXT</span>
                </label>
                {file && (
                  <div className="file-chip">
                    <Icon name="file" />
                    <span>Selected: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)</span>
                  </div>
                )}
                <div>
                  <button className="btn-primary" disabled={p.busy || p.userId === null || !file} onClick={() => file && p.onCv(file, t)}>
                    <Icon name="upload" /> {p.busy ? 'Analyzing...' : 'Upload CV & analyze'}
                  </button>
                </div>
              </div>
            </div>

            {p.busy && (
              <div className="callout info">
                <Icon name="clock" />
                <div>
                  <strong>Analysis in progress</strong>
                  <p>This may take a while as multiple AI agents process your profile...</p>
                </div>
              </div>
            )}
          </div>
        </Card>
      </Section>
    </>
  );
}

const Row = ({ i }: { i: SkillGapItem }) => (
  <tr>
    <td>
      <div className="cell-stack">
        <strong>{i.canonical_name}</strong>
        <span className="chip">{i.skill_id}</span>
      </div>
    </td>
    <td>
      <span className="chip">{i.evidence_class}</span>
    </td>
    <td>
      <span className="cell-value">{i.kb_confidence}</span>
    </td>
    <td>
      {i.matched_user_claim ? (
        <div className="cell-stack">
          <strong>"{i.matched_user_claim.claimed_skill}"</strong>
          <span className="cell-meta">
            Proficiency: {i.matched_user_claim.proficiency ?? "not given"} • Evidence: {i.matched_user_claim.evidence_count} row(s)
          </span>
        </div>
      ) : (
        <span className="muted">—</span>
      )}
    </td>
  </tr>
);

const names = (xs: SkillRef[]) => xs.length ? xs.map(s => s.canonical_name).join(", ") : "None";

export function UserProfile({ r }: { r: AnalysisResponse }) {
  return (
    <>
      <Unavailable what="Stored profile (education, experience, projects, certifications)"
        why="The API has no profile-read endpoint, by design, to avoid exposing personal data without access control." />

      <Card title="Analysis run metadata" subtitle="Information returned by the API">
        <div className="meta-list">
          <MetaRow label="User ID" value={<span className="chip primary">#{r.user_id}</span>} />
          <MetaRow label="Analysis source" value={<span className="chip">{r.source}</span>} />
          {r.document && (
            <>
              <MetaRow label="Document format" value={r.document.format} />
              <MetaRow label="File size" value={`${(r.document.size_bytes / 1024).toFixed(1)} KB`} />
              <MetaRow label="Pages" value={r.document.page_count ?? "N/A"} />
              <MetaRow label="Character count" value={r.document.character_count.toLocaleString()} />
            </>
          )}
        </div>

        {r.redaction && (
          <div className="meta-block">
            <h4>PII redaction (best effort)</h4>
            <p>
              {r.redaction.replacement_count} replacement(s) made
              {r.redaction.detected_types.length > 0 && (
                <span> · Types: {r.redaction.detected_types.join(", ")}</span>
              )}
            </p>
          </div>
        )}

        {r.profile_extraction && (
          <div className="meta-block">
            <h4>Profile extraction</h4>
            <p>Skill claims processed: {r.profile_extraction.skills_persisted}</p>
            <p>Evidence rows processed: {r.profile_extraction.evidence_persisted}</p>
          </div>
        )}
      </Card>
    </>
  );
}

export function SkillsEvidence({ r }: { r: AnalysisResponse }) {
  const g = r.skill_gap?.skill_gap;
  if (!g) return <Unavailable what="Skills & evidence" why="No skill-gap result in this run." />;
  const groups: [keyof typeof CATEGORY, SkillGapItem[]][] = [
    ["matched_evidenced", g.matched_evidenced], ["matched_claimed_only", g.matched_claimed_only], ["missing", g.missing]];
  return (
    <>
      <Card title="Skills analysis" subtitle={`Relative to: ${g.canonical_name} (${g.career_id})`}>
        <div className="callout info">
          <Icon name="info" />
          <div>
            <strong>How to read this</strong>
            <p>
              Proficiency is self-reported and is never compared against requirements.
              Skills are categorized based on evidence in your profile.
            </p>
          </div>
        </div>
      </Card>

      {groups.map(([cat, items]) => (
        <Section key={cat} title={CATEGORY[cat].text}>
          {items.length === 0 ? (
            <p className="empty-inline">None</p>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Required skill</th>
                    <th>KB classification</th>
                    <th>KB confidence</th>
                    <th>User claim & evidence</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map(i => <Row key={i.skill_id} i={i} />)}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      ))}

      <Section title={CATEGORY.unmatched.text}>
        {g.unmatched_user_claims.length === 0 ? (
          <p className="empty-inline">None</p>
        ) : (
          <>
            <p className="muted text-sm" style={{ marginBottom: '0.5rem' }}>
              These skills were mentioned in your profile but are not required for this career.
            </p>
            <ul className="claim-list">
              {g.unmatched_user_claims.map(u => (
                <li key={u.user_skill_id}>
                  <strong>"{u.claimed_skill}"</strong>
                  <span className="muted"> (evidence rows: {u.evidence_count})</span>
                  {u.note && <div className="cell-meta" style={{ marginTop: '0.25rem' }}>{u.note}</div>}
                </li>
              ))}
            </ul>
          </>
        )}
      </Section>

      <Unavailable what="Evidence details (type, description, URL)" why="The API returns only evidence counts per claim." />
    </>
  );
}

const fitTone = (score: number) => score >= 0.7 ? "emerald" : score >= 0.5 ? "amber" : "rose";
const fitLabel = (score: number) => score >= 0.7 ? "Strong match" : score >= 0.5 ? "Moderate match" : "Developing match";

export function Recommendations({ r, busy, onTarget }: { r: AnalysisResponse; busy: boolean; onTarget: (id: string) => void }) {
  if (!r.recommendations.length) return <Unavailable what="Recommendations" why="The run returned none." />;
  return (
    <>
      <div className="stat-grid summary-grid" style={{ marginBottom: '1.25rem' }}>
        <StatCard
          label="Recommendations"
          value={r.recommendations.length}
          hint="Ranked by deterministic fit score"
          tone="indigo"
          icon="layers"
        />
        <StatCard
          label="Active user"
          value={`#${r.user_id}`}
          hint="Browser session context"
          tone="slate"
          icon="user"
        />
        <StatCard
          label="Gap analysis target"
          value={r.target_career_id ? "Selected" : "Auto"}
          hint={r.target_career_id ?? "Top-ranked career selected automatically"}
          tone="emerald"
          icon="target"
        />
      </div>

      <div className="career-list">
        {r.recommendations.map((c, n) => {
          const tone = fitTone(c.fit_score);
          const isTarget = c.career_id === r.target_career_id;
          return (
            <article className={`card career-card ${isTarget ? "is-target" : ""}`} key={c.career_id}>
              <div className="career-head">
                <div className="career-title-group">
                  <div className={`rank-badge ${n === 0 ? "top" : ""}`}>#{n + 1}</div>
                  <div>
                    <div className="career-title-line">
                      <h3>{c.canonical_name}</h3>
                      {isTarget && <span className="chip primary">Target</span>}
                    </div>
                    <div className="career-meta">
                      <span className="chip">{c.career_id}</span>
                      <span className="meta-text">{c.domain}</span>
                    </div>
                  </div>
                </div>
                <button
                  className={isTarget ? "" : "btn-primary"}
                  disabled={busy || isTarget}
                  onClick={() => onTarget(c.career_id)}
                >
                  <Icon name={isTarget ? "check" : "refresh"} />
                  {isTarget ? "Current target" : "Set as target & re-analyze"}
                </button>
              </div>

              <div className="fit-row">
                <ProgressRing value={c.fit_score} label="Career fit score" />
                <div className="fit-copy">
                  <span className="stat-label">Career fit score</span>
                  <span className={`fit-value ${tone}`}>{fitLabel(c.fit_score)}</span>
                  <span className="stat-hint">Deterministic weighted match</span>
                </div>
              </div>

              <div className="skill-summary">
                <div className="skill-line">
                  <div className="skill-line-head">
                    <Tag cat="matched_evidenced" />
                    <span>Skills with evidence</span>
                  </div>
                  <p>{names(c.matched_skills)}</p>
                </div>
                <div className="skill-line">
                  <div className="skill-line-head">
                    <Tag cat="matched_claimed_only" />
                    <span>Skills claimed (no direct evidence)</span>
                  </div>
                  <p>{names(c.claimed_only_skills)}</p>
                </div>
                <div className="skill-line">
                  <div className="skill-line-head">
                    <Tag cat="missing" />
                    <span>Missing skills</span>
                  </div>
                  <p>{names(c.missing_skills_preview)}</p>
                </div>
              </div>

              <div className="reasoning">
                <div className="reasoning-head">
                  <Icon name="sparkles" /> Why this fits
                </div>
                <p>{c.reasoning}</p>
                <span className="text-xs">Reasoning source: {c.reasoning_source}</span>
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}

export function SkillGap({ r }: { r: AnalysisResponse }) {
  const a = r.skill_gap;
  if (!a) return <Unavailable what="Skill gap" why="No skill-gap result in this run." />;
  const g = a.skill_gap, n = a.narrative;
  return (
    <>
      <Card title={g.canonical_name} subtitle={`Career ID: ${g.career_id} • Fit score: ${pct(g.fit_score)}`}>
        <div className="stat-grid">
          <StatCard
            label="Matched · evidenced"
            value={g.matched_evidenced.length}
            hint="Supported by linked evidence"
            tone="emerald"
            icon="check"
          />
          <StatCard
            label="Claimed only"
            value={g.matched_claimed_only.length}
            hint="No linked evidence"
            tone="amber"
            icon="alert"
          />
          <StatCard
            label="Missing"
            value={g.missing.length}
            hint="Required but not in profile"
            tone="rose"
            icon="close"
          />
          <StatCard
            label="Unmatched claims"
            value={g.unmatched_user_claims.length}
            hint="Not career requirements"
            tone="slate"
            icon="info"
          />
        </div>
      </Card>

      <Section title="Analysis explanation">
        <Card>
          <div className="callout info">
            <Icon name="info" />
            <div>
              Narrative source: <strong>{a.narrative_source}</strong> • The deterministic classification is authoritative.
            </div>
          </div>

          {n.summary && <p className="narrative-summary">{n.summary}</p>}

          {n.strengths.length > 0 && (
            <div className="insight-group">
              <h4 className="insight-title ok"><Icon name="trending" /> Strengths</h4>
              <div className="insight-list">
                {n.strengths.map((o, i) => (
                  <div className="insight ok" key={i}>
                    <p>{o.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {[...n.claimed_only_observations, ...n.missing_skill_observations].length > 0 && (
            <div className="insight-group">
              <h4 className="insight-title warn"><Icon name="trending" /> Areas for development</h4>
              <div className="insight-list">
                {[...n.claimed_only_observations, ...n.missing_skill_observations].map((o, i) => (
                  <div className="insight warn" key={i}>
                    <p>{o.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {n.unmatched_claim_observations.length > 0 && (
            <div className="insight-group">
              <h4 className="insight-title muted"><Icon name="info" /> Other observations</h4>
              <div className="insight-list">
                {n.unmatched_claim_observations.map((o, i) => (
                  <div className="insight muted" key={`u${i}`}>
                    <p>{o.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {n.conclusion && (
            <div className="callout info">
              <Icon name="check" />
              <div><strong>Conclusion</strong><p>{n.conclusion}</p></div>
            </div>
          )}

          {a.llm_error && (
            <div className="callout warn">
              <Icon name="alert" />
              <div>An LLM step failed; details omitted by the API.</div>
            </div>
          )}

          {a.validation_notes.length > 0 && (
            <details>
              <summary>Validation notes ({a.validation_notes.length})</summary>
              <ul>
                {a.validation_notes.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </details>
          )}
        </Card>
      </Section>

      <div className="callout">
        <Icon name="chart" />
        <div>
          <strong>Detailed breakdown available</strong>
          <p>See the “Skills & Evidence” page for a per-skill breakdown with evidence details.</p>
        </div>
      </div>
    </>
  );
}

export function Roadmap({ r }: { r: AnalysisResponse }) {
  const m = r.roadmap;
  if (!m) return <Unavailable what="Roadmap" why="No roadmap in this run." />;
  return (
    <>
      <Card title="Learning roadmap summary" subtitle={`Narrative source: ${m.narrative_source}`}>
        <p className="narrative-summary">{m.summary}</p>
      </Card>

      <div className="callout info" style={{ marginBottom: '1.5rem' }}>
        <Icon name="info" />
        <div>
          <strong>Note</strong>
          <p>
            Focus items follow the Knowledge Base order and are not ranked by priority.
            The Knowledge Base provides no courses, resources, prerequisites, or proficiency targets.
          </p>
        </div>
      </div>

      {m.items.length === 0 ? (
        <Card>
          <div className="empty-state" style={{ border: 0, background: 'transparent', padding: '2rem' }}>
            <div className="empty-icon"><Icon name="check" /></div>
            <h3>All skills covered</h3>
            <p>No outstanding learning items identified.</p>
          </div>
        </Card>
      ) : (
        <Section title={`Learning steps (${m.items.length} items)`}>
          <div className="timeline">
            {m.items.map((i, idx) => (
              <article className="card roadmap-card" key={i.skill_id}>
                <div className="roadmap-step">{idx + 1}</div>
                <div className="roadmap-content">
                  <div className="roadmap-head">
                    <h3>{i.canonical_name}</h3>
                    <span className="chip">{i.skill_id}</span>
                    <Tag cat={i.gap_status} />
                  </div>

                  <div className="action-box">
                    <span className="action-icon"><Icon name="target" /></span>
                    <div>
                      <strong>Action required</strong>
                      <p>
                        {i.learning_action === "add_linked_evidence"
                          ? "Add linked evidence to demonstrate this skill"
                          : "Develop and strengthen this skill"}
                      </p>
                    </div>
                  </div>

                  <div className="kb-basis">
                    <span className="stat-label">Knowledge base basis</span>
                    <p>{i.knowledge_base_basis || "Evidence unavailable"}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

export function Evidence({ r }: { r: AnalysisResponse }) {
  const ids = new Set(r.verification?.checks.flatMap(c => c.source_ids) ?? []);
  return (
    <>
      <Unavailable what="Source/provenance records (SKKNI, KBJI, O*NET, ESCO)" why="No API endpoint resolves provenance. Only the IDs below are available, unresolved." />

      <Card title="Knowledge base references" subtitle="Sources for roadmap items">
        {r.roadmap?.items.length ? (
          <div className="reference-list">
            {r.roadmap.items.map(i => (
              <div className="reference-row" key={i.skill_id}>
                <strong>{i.canonical_name}</strong>
                <p>{i.knowledge_base_basis || "Evidence unavailable"}</p>
              </div>
            ))}
          </div>
        ) : (
          <p className="empty-inline">Evidence unavailable</p>
        )}
      </Card>

      <Card title="Referenced record IDs" subtitle="From verification checks">
        {ids.size ? (
          <div className="chip-row">
            {[...ids].map(id => (
              <span className="chip" key={id}>{id}</span>
            ))}
          </div>
        ) : (
          <p className="empty-inline">Evidence unavailable</p>
        )}
      </Card>
    </>
  );
}

const statusPill = (status: string) =>
  status === "PASS" ? "pass" : status === "FAIL" ? "fail" : "revise";

export function Details({ r }: { r: AnalysisResponse }) {
  const v = r.verification, w = r.recommendations[0]?.score_breakdown.weights_used;
  return (
    <>
      <StatusBanner status={r.final_status} revisions={r.revision_count} />

      <Card title="Analysis overview" subtitle="Run configuration and metadata">
        <div className="meta-list">
          <MetaRow
            label="Verified"
            value={
              r.verified
                ? <span className="health-pill ok"><Icon name="check" /> Yes</span>
                : <span className="health-pill bad"><Icon name="close" /> No</span>
            }
          />
          <MetaRow label="Target career" value={r.target_career_id ?? "Auto-selected"} />
          <MetaRow label="Skill gap narrative source" value={<span className="chip">{r.skill_gap?.narrative_source ?? "N/A"}</span>} />
          <MetaRow label="Roadmap narrative source" value={<span className="chip">{r.roadmap?.narrative_source ?? "N/A"}</span>} />
          <MetaRow label="Revisions used" value={<span className="chip">{r.revision_count}</span>} />
        </div>
      </Card>

      <Unavailable what="Analysis ID / history / timestamps / model version" why="Not returned by the API; persistence and logging belong to Step 16." />

      {w && (
        <Card title="Scoring weights" subtitle="Deterministic fit calculation weights">
          <pre>{JSON.stringify(w, null, 2)}</pre>
        </Card>
      )}

      {!v ? (
        <Unavailable what="Verification" why="No verification result in this run." />
      ) : (
        <Card title={`Verification: ${v.status}`} subtitle="Automated verification results">
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Check</th>
                  <th>Status</th>
                  <th>Reason</th>
                  <th>Source IDs</th>
                </tr>
              </thead>
              <tbody>
                {v.checks.map((c, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 600 }}>{c.check}</td>
                    <td>
                      <span className={`status-pill ${statusPill(c.status)}`}>{c.status}</span>
                    </td>
                    <td style={{ lineHeight: 1.7 }}>{c.reason}</td>
                    <td>
                      {c.source_ids.length > 5
                        ? <span className="chip">{c.source_ids.length} IDs</span>
                        : c.source_ids.length
                          ? (
                            <div className="chip-row">
                              {c.source_ids.map(id => <span className="chip" key={id}>{id}</span>)}
                            </div>
                          )
                          : <span className="muted">—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {v.unsupported_claims.length > 0 && (
            <div style={{ marginTop: '1.5rem' }}>
              <h4 className="insight-title" style={{ color: 'var(--bad)', marginBottom: '0.75rem' }}>
                <Icon name="alert" /> Unsupported claims
              </h4>
              <div className="alert-list">
                {v.unsupported_claims.map((c, i) => (
                  <div className="claim-alert" key={i}>
                    <strong>[{c.component}]</strong>
                    <p>{c.claim}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {v.required_revision.length > 0 && (
            <div style={{ marginTop: '1.5rem' }}>
              <h4 className="insight-title warn" style={{ marginBottom: '0.25rem' }}>
                <Icon name="refresh" /> Required revisions
              </h4>
              <ul className="check-list">
                {v.required_revision.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            </div>
          )}

          {v.llm_error && (
            <div className="callout warn" style={{ marginTop: '1rem' }}>
              <Icon name="alert" />
              <div>A semantic-review LLM step failed; details omitted by the API.</div>
            </div>
          )}
        </Card>
      )}
    </>
  );
}


