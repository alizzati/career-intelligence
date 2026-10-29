import { useState } from "react";
import { CATEGORY, Section, StatusBanner, Tag, Unavailable, pct, Card } from "./components";
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
      <div className="card" style={{ background: 'linear-gradient(135deg, var(--bg-elevated) 0%, var(--bg-subtle) 100%)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
          <div style={{ fontSize: '2rem', flexShrink: 0 }}>🎯</div>
          <div>
            <h2 style={{ margin: '0 0 0.5rem 0', fontSize: '1.5rem', fontWeight: 700 }}>Welcome to Career Intelligence</h2>
            <p style={{ margin: '0 0 0.75rem 0', color: 'var(--fg-muted)', lineHeight: 1.7 }}>
              Discover your ideal IT career path with AI-powered analysis. Get personalized recommendations, 
              identify skill gaps, and receive a tailored learning roadmap based on Indonesian occupational standards.
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem', color: 'var(--fg-subtle)' }}>
              <span>⚠️</span>
              <span>Research prototype - Results are held in browser memory only and are lost on reload</span>
            </div>
          </div>
        </div>
      </div>

      <Card title="System Status" subtitle="Check backend connectivity">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <button className="btn-primary" onClick={p.onHealth}>
            Check Backend
          </button>
          {p.healthText && (
            <span role="status" style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '0.5rem',
              color: p.healthText.includes('reachable') ? 'var(--ok)' : 'var(--bad)',
              fontWeight: 500
            }}>
              {p.healthText.includes('reachable') ? '✓' : '✗'} {p.healthText}
            </span>
          )}
        </div>
      </Card>

      <Section title="Step 1: User Setup">
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
          <Card title="Create New Account" subtitle="Primary workflow">
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              <label>
                Email Address
                <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder="your.email@example.com" style={{ borderColor: createError && createError.includes('email') ? 'var(--bad)' : undefined }} />
              </label>
              {createError && createError.toLowerCase().includes('email') && (
                <div style={{ color: 'var(--bad)', fontSize: '0.8125rem', marginTop: '-0.25rem' }}>{createError}</div>
              )}
              <label>
                Full Name
                <input value={name} onChange={e => setName(e.target.value)} placeholder="Enter your full name" />
              </label>
              <button className="btn-primary" disabled={creating || p.busy || !email || !name} onClick={handleCreate}>
                {creating ? 'Creating...' : 'Create Account'}
              </button>
              {createSuccess && <div style={{ color: 'var(--ok)', fontSize: '0.875rem' }}>✓ {createSuccess}</div>}
              {createError && !createError.toLowerCase().includes('email') && <div style={{ color: 'var(--bad)', fontSize: '0.875rem' }}>{createError}</div>}
            </div>
          </Card>

          <Card title="Use Existing Account" subtitle="Secondary workflow">
            <div style={{ display: 'grid', gap: '0.75rem' }}>
              <label>
                Email Address
                <input type="email" value={existingEmail} onChange={e => setExistingEmail(e.target.value)} placeholder="your.email@example.com" />
              </label>
              <button disabled={selecting || p.busy || !existingEmail} onClick={handleSelectExisting}>
                {selecting ? 'Looking up...' : 'Continue with this account'}
              </button>
              {existingSuccess && <div style={{ color: 'var(--ok)', fontSize: '0.875rem' }}>✓ {existingSuccess}</div>}
              {existingError && <div style={{ color: 'var(--bad)', fontSize: '0.875rem' }}>{existingError}</div>}
              <div style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem' }}>
                <strong>Active User:</strong> {p.userId ? <span style={{ color: 'var(--primary)', fontWeight: 600 }}>#{p.userId}</span> : <span className="muted">None selected</span>}
              </div>
            </div>
          </Card>
        </div>
      </Section>

      <Section title="Step 2: Run Career Analysis">
        <Card title="Analyze Your Profile" subtitle={p.userId === null ? "Please select or create a user first" : "Choose your analysis method"}>
          <div style={{ display: 'grid', gap: '1.5rem' }}>
            <label style={{ maxWidth: '400px' }}>
              Target Career (Optional)
              <select value={target} onChange={e => setTarget(e.target.value)}>
                <option value="">Choose a target career (optional)</option>
                {p.careersLoading && <option value="" disabled>Loading careers...</option>}
                {p.careersError && <option value="" disabled>Failed to load careers</option>}
                {!p.careersLoading && !p.careersError && p.careers.map(c => (
                  <option key={c.career_id} value={c.career_id}>{c.canonical_name}</option>
                ))}
              </select>
              <span style={{ fontSize: '0.75rem', color: 'var(--fg-muted)', fontWeight: 400 }}>
                Leave blank to get automatic recommendations
              </span>
            </label>
            
            <div>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', fontWeight: 600 }}>Option A: Analyze Stored Profile</h4>
              <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
                Use previously stored profile data for analysis
              </p>
              <button className="btn-primary" disabled={p.busy || p.userId === null} onClick={() => p.onProfile(t)}>
                {p.busy ? 'Analyzing...' : 'Analyze Stored Profile'}
              </button>
            </div>
            
            <hr />
            
            <div>
              <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '0.9rem', fontWeight: 600 }}>Option B: Upload CV</h4>
              <p style={{ margin: '0 0 0.75rem 0', fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
                Upload your CV/resume for automatic profile extraction
              </p>
              <div style={{ display: 'grid', gap: '0.75rem', maxWidth: '400px' }}>
                <label>
                  CV File
                  <input type="file" accept=".pdf,.docx,.txt" onChange={e => setFile(e.target.files?.[0] ?? null)} />
                  <span style={{ fontSize: '0.75rem', color: 'var(--fg-muted)', fontWeight: 400 }}>
                    Supported formats: PDF, DOCX, TXT
                  </span>
                </label>
                {file && (
                  <div style={{ padding: '0.5rem 0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem' }}>
                    📄 Selected: <strong>{file.name}</strong> ({(file.size / 1024).toFixed(1)} KB)
                  </div>
                )}
                <button className="btn-primary" disabled={p.busy || p.userId === null || !file} onClick={() => file && p.onCv(file, t)}>
                  {p.busy ? 'Analyzing...' : 'Upload CV & Analyze'}
                </button>
              </div>
            </div>
          </div>
          
          {p.busy && (
            <div style={{ 
              marginTop: '1.5rem', 
              padding: '1rem', 
              background: 'var(--info-bg)', 
              border: '1px solid var(--info-border)',
              borderRadius: 'var(--radius-md)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.75rem'
            }}>
              <div style={{ fontSize: '1.25rem' }}>⏳</div>
              <div>
                <strong style={{ color: 'var(--info)' }}>Analysis in Progress</strong>
                <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
                  This may take a while as multiple AI agents process your profile...
                </p>
              </div>
            </div>
          )}
        </Card>
      </Section>
    </>
  );
}

const Row = ({ i }: { i: SkillGapItem }) => (
  <tr>
    <td>
      <div>
        <strong>{i.canonical_name}</strong>
        <div style={{ fontSize: '0.75rem', color: 'var(--fg-muted)', marginTop: '0.25rem' }}>{i.skill_id}</div>
      </div>
    </td>
    <td>
      <span style={{ 
        padding: '0.25rem 0.5rem', 
        background: 'var(--bg-subtle)', 
        borderRadius: 'var(--radius-sm)',
        fontSize: '0.75rem'
      }}>
        {i.evidence_class}
      </span>
    </td>
    <td>
      <span style={{ fontWeight: 500 }}>{i.kb_confidence}</span>
    </td>
    <td>
      {i.matched_user_claim ? (
        <div style={{ fontSize: '0.875rem' }}>
          <div style={{ marginBottom: '0.25rem' }}>
            <strong>"{i.matched_user_claim.claimed_skill}"</strong>
          </div>
          <div style={{ color: 'var(--fg-muted)' }}>
            Proficiency: {i.matched_user_claim.proficiency ?? "not given"} • Evidence: {i.matched_user_claim.evidence_count} row(s)
          </div>
        </div>
      ) : (
        <span style={{ color: 'var(--fg-subtle)' }}>—</span>
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
      
      <Card title="Analysis Run Metadata" subtitle="Information returned by the API">
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
            <span style={{ fontWeight: 500 }}>User ID</span>
            <span style={{ fontWeight: 600, color: 'var(--primary)' }}>#{r.user_id}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
            <span style={{ fontWeight: 500 }}>Analysis Source</span>
            <span>{r.source}</span>
          </div>
          {r.document && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
                <span style={{ fontWeight: 500 }}>Document Format</span>
                <span>{r.document.format}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
                <span style={{ fontWeight: 500 }}>File Size</span>
                <span>{(r.document.size_bytes / 1024).toFixed(1)} KB</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
                <span style={{ fontWeight: 500 }}>Pages</span>
                <span>{r.document.page_count ?? "N/A"}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
                <span style={{ fontWeight: 500 }}>Character Count</span>
                <span>{r.document.character_count.toLocaleString()}</span>
              </div>
            </>
          )}
          {r.redaction && (
            <>
              <div style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
                <div style={{ fontWeight: 500, marginBottom: '0.5rem' }}>PII Redaction (Best Effort)</div>
                <div style={{ fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
                  {r.redaction.replacement_count} replacement(s) made
                  {r.redaction.detected_types.length > 0 && (
                    <div style={{ marginTop: '0.25rem' }}>
                      Types: {r.redaction.detected_types.join(", ")}
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
          {r.profile_extraction && (
            <>
              <div style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
                <div style={{ fontWeight: 500, marginBottom: '0.5rem' }}>Profile Extraction</div>
                <div style={{ fontSize: '0.875rem', color: 'var(--fg-muted)', display: 'grid', gap: '0.25rem' }}>
                  <div>Skill claims processed: {r.profile_extraction.skills_persisted}</div>
                  <div>Evidence rows processed: {r.profile_extraction.evidence_persisted}</div>
                </div>
              </div>
            </>
          )}
        </div>
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
      <Card title="Skills Analysis" subtitle={`Relative to: ${g.canonical_name} (${g.career_id})`}>
        <div style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem', lineHeight: 1.7 }}>
          <strong>Note:</strong> Proficiency is self-reported and is never compared against requirements. 
          Skills are categorized based on evidence in your profile.
        </div>
      </Card>

      {groups.map(([cat, items]) => (
        <Section key={cat} title={CATEGORY[cat].text}>
          {items.length === 0 ? (
            <Card>
              <p style={{ margin: 0, color: 'var(--fg-muted)', textAlign: 'center', padding: '1rem' }}>None</p>
            </Card>
          ) : (
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Required Skill</th>
                    <th>KB Classification</th>
                    <th>KB Confidence</th>
                    <th>User Claim & Evidence</th>
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
          <Card>
            <p style={{ margin: 0, color: 'var(--fg-muted)', textAlign: 'center', padding: '1rem' }}>None</p>
          </Card>
        ) : (
          <Card>
            <p style={{ margin: '0 0 1rem 0', fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
              These skills were mentioned in your profile but are not required for this career.
            </p>
            <ul style={{ margin: 0 }}>
              {g.unmatched_user_claims.map(u => (
                <li key={u.user_skill_id}>
                  <strong>"{u.claimed_skill}"</strong> 
                  <span style={{ color: 'var(--fg-muted)' }}> (evidence rows: {u.evidence_count})</span>
                  {u.note && <div style={{ marginTop: '0.25rem', fontSize: '0.875rem', color: 'var(--fg-muted)' }}>{u.note}</div>}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </Section>
      
      <Unavailable what="Evidence details (type, description, URL)" why="The API returns only evidence counts per claim." />
    </>
  );
}

export function Recommendations({ r, busy, onTarget }: { r: AnalysisResponse; busy: boolean; onTarget: (id: string) => void }) {
  if (!r.recommendations.length) return <Unavailable what="Recommendations" why="The run returned none." />;
  return (
    <>
      <Card title="Analysis Summary" subtitle="Career recommendations ranked by fit score">
        <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', fontSize: '0.875rem' }}>
          <div>
            <span className="muted">Target Career for Gap Analysis:</span>{" "}
            <strong style={{ color: 'var(--primary)' }}>{r.target_career_id ?? "Auto-selected (top-ranked)"}</strong>
          </div>
          <div>
            <span className="muted">Total Recommendations:</span>{" "}
            <strong>{r.recommendations.length}</strong>
          </div>
          <div>
            <span className="muted">User ID:</span>{" "}
            <strong>#{r.user_id}</strong>
          </div>
        </div>
      </Card>

      {r.recommendations.map((c, n) => (
        <article className="card" key={c.career_id} style={{ border: c.career_id === r.target_career_id ? '2px solid var(--primary)' : '1px solid var(--border)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
                <div style={{ 
                  width: '2rem', 
                  height: '2rem', 
                  borderRadius: '50%', 
                  background: n === 0 ? 'linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%)' : 'var(--bg-subtle)',
                  color: n === 0 ? 'white' : 'var(--fg)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontWeight: 700,
                  fontSize: '0.875rem',
                  flexShrink: 0
                }}>
                  #{n + 1}
                </div>
                <h3 style={{ margin: 0, fontSize: '1.25rem', fontWeight: 600 }}>
                  {c.canonical_name}
                </h3>
                {c.career_id === r.target_career_id && (
                  <span style={{ 
                    padding: '0.25rem 0.5rem', 
                    background: 'var(--primary)', 
                    color: 'white', 
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.75rem',
                    fontWeight: 600
                  }}>
                    TARGET
                  </span>
                )}
              </div>
              <div style={{ display: 'flex', gap: '1rem', fontSize: '0.875rem', color: 'var(--fg-muted)', flexWrap: 'wrap' }}>
                <span>ID: <code style={{ background: 'var(--bg-subtle)', padding: '0.125rem 0.375rem', borderRadius: 'var(--radius-sm)' }}>{c.career_id}</code></span>
                <span>Domain: {c.domain}</span>
              </div>
            </div>
            <button 
              className={c.career_id === r.target_career_id ? "" : "btn-primary"}
              disabled={busy || c.career_id === r.target_career_id} 
              onClick={() => onTarget(c.career_id)}
            >
              {c.career_id === r.target_career_id ? "✓ Current Target" : "Set as Target & Re-analyze"}
            </button>
          </div>

          <div style={{ marginBottom: '1.5rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>Career Fit Score</span>
              <span style={{ fontWeight: 700, fontSize: '1.125rem', color: c.fit_score >= 0.7 ? 'var(--ok)' : c.fit_score >= 0.5 ? 'var(--warn)' : 'var(--bad)' }}>
                {pct(c.fit_score)}
              </span>
            </div>
            <div style={{ 
              width: '100%', 
              height: '0.75rem', 
              background: 'var(--bg-subtle)', 
              borderRadius: 'var(--radius-sm)',
              overflow: 'hidden'
            }}>
              <div style={{ 
                width: `${c.fit_score * 100}%`, 
                height: '100%', 
                background: c.fit_score >= 0.7 ? 'linear-gradient(90deg, var(--ok) 0%, #22c55e 100%)' : 
                           c.fit_score >= 0.5 ? 'linear-gradient(90deg, var(--warn) 0%, #fb923c 100%)' : 
                           'linear-gradient(90deg, var(--bad) 0%, #f87171 100%)',
                transition: 'width 0.3s ease'
              }} />
            </div>
          </div>

          <div style={{ display: 'grid', gap: '0.75rem', marginBottom: '1rem' }}>
            <div>
              <div style={{ marginBottom: '0.5rem' }}>
                <Tag cat="matched_evidenced" />
                <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>Skills with Evidence</span>
              </div>
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--fg-muted)', lineHeight: 1.6 }}>
                {names(c.matched_skills)}
              </p>
            </div>
            <div>
              <div style={{ marginBottom: '0.5rem' }}>
                <Tag cat="matched_claimed_only" />
                <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>Skills Claimed (No Direct Evidence)</span>
              </div>
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--fg-muted)', lineHeight: 1.6 }}>
                {names(c.claimed_only_skills)}
              </p>
            </div>
            <div>
              <div style={{ marginBottom: '0.5rem' }}>
                <Tag cat="missing" />
                <span style={{ fontSize: '0.875rem', fontWeight: 500 }}>Missing Skills</span>
              </div>
              <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--fg-muted)', lineHeight: 1.6 }}>
                {names(c.missing_skills_preview)}
              </p>
            </div>
          </div>

          <div style={{ padding: '1rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', borderLeft: '3px solid var(--primary)' }}>
            <p style={{ margin: '0 0 0.5rem 0', fontSize: '0.875rem', lineHeight: 1.7 }}>
              {c.reasoning}
            </p>
            <span className="text-xs" style={{ color: 'var(--fg-subtle)' }}>
              Reasoning source: {c.reasoning_source}
            </span>
          </div>
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
      <Card title={`${g.canonical_name}`} subtitle={`Career ID: ${g.career_id} • Fit Score: ${pct(g.fit_score)}`}>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem' }}>
          <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--ok-bg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--ok-border)' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--ok)' }}>{g.matched_evidenced.length}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--ok)', fontWeight: 500 }}>Evidenced</div>
          </div>
          <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--warn-bg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--warn-border)' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--warn)' }}>{g.matched_claimed_only.length}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--warn)', fontWeight: 500 }}>Claimed Only</div>
          </div>
          <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--bad-bg)', borderRadius: 'var(--radius-md)', border: '1px solid var(--bad-border)' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--bad)' }}>{g.missing.length}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--bad)', fontWeight: 500 }}>Missing</div>
          </div>
          <div style={{ textAlign: 'center', padding: '1rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--fg-muted)' }}>{g.unmatched_user_claims.length}</div>
            <div style={{ fontSize: '0.875rem', color: 'var(--fg-muted)', fontWeight: 500 }}>Unmatched Claims</div>
          </div>
        </div>
      </Card>

      <Section title="Analysis Explanation">
        <Card>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
            <span>ℹ️</span>
            <span>Narrative source: <strong>{a.narrative_source}</strong> • The deterministic classification is authoritative</span>
          </div>
          
          {n.summary && (
            <div style={{ padding: '1rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)', marginBottom: '1rem' }}>
              <p style={{ margin: 0, lineHeight: 1.8 }}>{n.summary}</p>
            </div>
          )}
          
          {n.strengths.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <h4 style={{ margin: '0 0 0.75rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--ok)' }}>
                <span>💪</span> Strengths
              </h4>
              <div style={{ display: 'grid', gap: '0.5rem' }}>
                {n.strengths.map((o, i) => (
                  <div key={i} style={{ padding: '0.75rem', background: 'var(--ok-bg)', borderLeft: '3px solid var(--ok)', borderRadius: '0 var(--radius-md) var(--radius-md) 0' }}>
                    <p style={{ margin: 0, fontSize: '0.875rem', lineHeight: 1.7 }}>{o.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {[...n.claimed_only_observations, ...n.missing_skill_observations].length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <h4 style={{ margin: '0 0 0.75rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--warn)' }}>
                <span>📈</span> Areas for Development
              </h4>
              <div style={{ display: 'grid', gap: '0.5rem' }}>
                {[...n.claimed_only_observations, ...n.missing_skill_observations].map((o, i) => (
                  <div key={i} style={{ padding: '0.75rem', background: 'var(--warn-bg)', borderLeft: '3px solid var(--warn)', borderRadius: '0 var(--radius-md) var(--radius-md) 0' }}>
                    <p style={{ margin: 0, fontSize: '0.875rem', lineHeight: 1.7 }}>{o.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {n.unmatched_claim_observations.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <h4 style={{ margin: '0 0 0.75rem 0', display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--fg-muted)' }}>
                <span>❓</span> Other Observations
              </h4>
              <div style={{ display: 'grid', gap: '0.5rem' }}>
                {n.unmatched_claim_observations.map((o, i) => (
                  <div key={`u${i}`} style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderLeft: '3px solid var(--border-strong)', borderRadius: '0 var(--radius-md) var(--radius-md) 0' }}>
                    <p style={{ margin: 0, fontSize: '0.875rem', lineHeight: 1.7 }}>{o.text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {n.conclusion && (
            <div style={{ padding: '1rem', background: 'var(--info-bg)', border: '1px solid var(--info-border)', borderRadius: 'var(--radius-md)' }}>
              <p style={{ margin: 0, lineHeight: 1.8, fontWeight: 500 }}>{n.conclusion}</p>
            </div>
          )}
          
          {a.llm_error && (
            <div style={{ marginTop: '1rem', padding: '0.75rem', background: 'var(--warn-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem', color: 'var(--warn)' }}>
              ⚠️ An LLM step failed; details omitted by the API.
            </div>
          )}
          
          {a.validation_notes.length > 0 && (
            <details style={{ marginTop: '1rem' }}>
              <summary>Validation Notes ({a.validation_notes.length})</summary>
              <ul style={{ marginTop: '0.75rem' }}>
                {a.validation_notes.map((x, i) => (
                  <li key={i} style={{ fontSize: '0.875rem' }}>{x}</li>
                ))}
              </ul>
            </details>
          )}
        </Card>
      </Section>

      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span style={{ fontSize: '1.25rem' }}>📊</span>
          <div>
            <strong>Detailed Breakdown Available</strong>
            <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
              See the "Skills & Evidence" tab for per-skill breakdown with evidence details.
            </p>
          </div>
        </div>
      </Card>
    </>
  );
}

export function Roadmap({ r }: { r: AnalysisResponse }) {
  const m = r.roadmap;
  if (!m) return <Unavailable what="Roadmap" why="No roadmap in this run." />;
  return (
    <>
      <Card title="Learning Roadmap Summary" subtitle={`Narrative source: ${m.narrative_source}`}>
        <p style={{ margin: 0, lineHeight: 1.8 }}>{m.summary}</p>
      </Card>

      <div style={{ 
        padding: '1rem', 
        background: 'var(--info-bg)', 
        border: '1px solid var(--info-border)',
        borderRadius: 'var(--radius-md)',
        marginBottom: '1.5rem',
        display: 'flex',
        alignItems: 'flex-start',
        gap: '0.75rem'
      }}>
        <span style={{ fontSize: '1.25rem', flexShrink: 0 }}>ℹ️</span>
        <div style={{ fontSize: '0.875rem', lineHeight: 1.7 }}>
          <strong>Note:</strong> Focus items follow the Knowledge Base order and are not ranked by priority. 
          The Knowledge Base provides no courses, resources, prerequisites, or proficiency targets.
        </div>
      </div>

      {m.items.length === 0 ? (
        <Card>
          <div style={{ textAlign: 'center', padding: '2rem' }}>
            <div style={{ fontSize: '2.5rem', marginBottom: '0.75rem' }}>🎉</div>
            <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--ok)' }}>All Skills Covered!</h3>
            <p style={{ margin: 0, color: 'var(--fg-muted)' }}>No outstanding learning items identified.</p>
          </div>
        </Card>
      ) : (
        <Section title={`Learning Steps (${m.items.length} items)`}>
          <div style={{ display: 'grid', gap: '1rem' }}>
            {m.items.map((i, idx) => (
              <Card key={i.skill_id}>
                <div style={{ display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
                  <div style={{ 
                    width: '2.5rem', 
                    height: '2.5rem', 
                    borderRadius: '50%', 
                    background: 'linear-gradient(135deg, var(--primary) 0%, var(--accent) 100%)',
                    color: 'white',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 700,
                    fontSize: '0.9rem',
                    flexShrink: 0
                  }}>
                    {idx + 1}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem', flexWrap: 'wrap' }}>
                      <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 600 }}>{i.canonical_name}</h3>
                      <code style={{ background: 'var(--bg-subtle)', padding: '0.125rem 0.375rem', borderRadius: 'var(--radius-sm)', fontSize: '0.75rem' }}>{i.skill_id}</code>
                      <Tag cat={i.gap_status} />
                    </div>
                    
                    <div style={{ marginBottom: '0.75rem', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        <span style={{ fontSize: '1rem' }}>🎯</span>
                        <strong style={{ fontSize: '0.875rem' }}>Action Required</strong>
                      </div>
                      <p style={{ margin: 0, fontSize: '0.875rem', color: 'var(--fg-muted)' }}>
                        {i.learning_action === "add_linked_evidence" 
                          ? "Add linked evidence to demonstrate this skill" 
                          : "Develop and strengthen this skill"}
                      </p>
                    </div>
                    
                    <div style={{ fontSize: '0.875rem' }}>
                      <strong style={{ color: 'var(--fg-muted)' }}>Knowledge Base Basis:</strong>
                      <p style={{ margin: '0.25rem 0 0 0', color: 'var(--fg)', lineHeight: 1.7 }}>
                        {i.knowledge_base_basis || "Evidence unavailable"}
                      </p>
                    </div>
                  </div>
                </div>
              </Card>
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
      
      <Card title="Knowledge Base References" subtitle="Sources for roadmap items">
        {r.roadmap?.items.length ? (
          <div style={{ display: 'grid', gap: '0.75rem' }}>
            {r.roadmap.items.map(i => (
              <div key={i.skill_id} style={{ padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
                <div style={{ fontWeight: 600, marginBottom: '0.25rem' }}>{i.canonical_name}</div>
                <div style={{ fontSize: '0.875rem', color: 'var(--fg-muted)', lineHeight: 1.7 }}>
                  {i.knowledge_base_basis || "Evidence unavailable"}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ margin: 0, color: 'var(--fg-muted)', textAlign: 'center', padding: '1rem' }}>Evidence unavailable</p>
        )}
      </Card>
      
      <Card title="Referenced Record IDs" subtitle="From verification checks">
        {ids.size ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            {[...ids].map(id => (
              <code key={id} style={{ 
                padding: '0.25rem 0.5rem', 
                background: 'var(--bg-subtle)', 
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8125rem'
              }}>
                {id}
              </code>
            ))}
          </div>
        ) : (
          <p style={{ margin: 0, color: 'var(--fg-muted)', textAlign: 'center', padding: '1rem' }}>Evidence unavailable</p>
        )}
      </Card>
    </>
  );
}

export function Details({ r }: { r: AnalysisResponse }) {
  const v = r.verification, w = r.recommendations[0]?.score_breakdown.weights_used;
  return (
    <>
      <StatusBanner status={r.final_status} revisions={r.revision_count} />
      
      <Card title="Analysis Overview" subtitle="Run configuration and metadata">
        <div style={{ display: 'grid', gap: '0.75rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
            <span style={{ fontWeight: 500 }}>Verified</span>
            <span style={{ fontWeight: 600, color: r.verified ? 'var(--ok)' : 'var(--bad)' }}>
              {r.verified ? '✓ Yes' : '✗ No'}
            </span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
            <span style={{ fontWeight: 500 }}>Target Career</span>
            <span>{r.target_career_id ?? "Auto-selected"}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
            <span style={{ fontWeight: 500 }}>Skill Gap Narrative Source</span>
            <span>{r.skill_gap?.narrative_source ?? "N/A"}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
            <span style={{ fontWeight: 500 }}>Roadmap Narrative Source</span>
            <span>{r.roadmap?.narrative_source ?? "N/A"}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.75rem', background: 'var(--bg-subtle)', borderRadius: 'var(--radius-md)' }}>
            <span style={{ fontWeight: 500 }}>Revisions Used</span>
            <span style={{ fontWeight: 600 }}>{r.revision_count}</span>
          </div>
        </div>
      </Card>
      
      <Unavailable what="Analysis ID / history / timestamps / model version" why="Not returned by the API; persistence and logging belong to Step 16." />
      
      {w && (
        <Card title="Scoring Weights" subtitle="Deterministic fit calculation weights">
          <pre style={{ margin: 0 }}>{JSON.stringify(w, null, 2)}</pre>
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
                    <td style={{ fontWeight: 500 }}>{c.check}</td>
                    <td>
                      <span style={{ 
                        padding: '0.25rem 0.5rem', 
                        borderRadius: 'var(--radius-sm)',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        background: c.status === 'PASS' ? 'var(--ok-bg)' : c.status === 'FAIL' ? 'var(--bad-bg)' : 'var(--warn-bg)',
                        color: c.status === 'PASS' ? 'var(--ok)' : c.status === 'FAIL' ? 'var(--bad)' : 'var(--warn)',
                        border: `1px solid ${c.status === 'PASS' ? 'var(--ok-border)' : c.status === 'FAIL' ? 'var(--bad-border)' : 'var(--warn-border)'}`
                      }}>
                        {c.status}
                      </span>
                    </td>
                    <td style={{ fontSize: '0.875rem', lineHeight: 1.6 }}>{c.reason}</td>
                    <td style={{ fontSize: '0.8125rem' }}>
                      {c.source_ids.length > 5 ? `${c.source_ids.length} IDs` : c.source_ids.join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          
          {v.unsupported_claims.length > 0 && (
            <div style={{ marginTop: '1.5rem' }}>
              <h4 style={{ margin: '0 0 0.75rem 0', color: 'var(--bad)' }}>⚠️ Unsupported Claims</h4>
              <div style={{ display: 'grid', gap: '0.5rem' }}>
                {v.unsupported_claims.map((c, i) => (
                  <div key={i} style={{ padding: '0.75rem', background: 'var(--bad-bg)', border: '1px solid var(--bad-border)', borderRadius: 'var(--radius-md)' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.25rem', color: 'var(--bad)' }}>
                      [{c.component}]
                    </div>
                    <div style={{ fontSize: '0.875rem', lineHeight: 1.7 }}>{c.claim}</div>
                  </div>
                ))}
              </div>
            </div>
          )}
          
          {v.required_revision.length > 0 && (
            <div style={{ marginTop: '1.5rem' }}>
              <h4 style={{ margin: '0 0 0.75rem 0', color: 'var(--warn)' }}>🔄 Required Revisions</h4>
              <ul style={{ margin: 0 }}>
                {v.required_revision.map((x, i) => (
                  <li key={i} style={{ fontSize: '0.875rem', lineHeight: 1.7 }}>{x}</li>
                ))}
              </ul>
            </div>
          )}
          
          {v.llm_error && (
            <div style={{ marginTop: '1rem', padding: '0.75rem', background: 'var(--warn-bg)', borderRadius: 'var(--radius-md)', fontSize: '0.875rem', color: 'var(--warn)' }}>
              ⚠️ A semantic-review LLM step failed; details omitted by the API.
            </div>
          )}
        </Card>
      )}
    </>
  );
}