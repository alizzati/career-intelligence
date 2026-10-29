import type { ReactNode } from "react";
import { ApiRequestError } from "./services/api";
import type { FinalStatus, GapStatus } from "./types/api";

// Labels are text, never colour-only. Four frozen categories stay distinct.
export const CATEGORY: Record<GapStatus | "unmatched", { text: string; cls: string }> = {
  matched_evidenced: { text: "✓ Matched – evidenced", cls: "ok" },
  matched_claimed_only: { text: "△ Matched – claimed only (no linked evidence)", cls: "warn" },
  missing: { text: "✗ Missing (required, not in profile)", cls: "bad" },
  unmatched: { text: "? Unmatched user claim (not a missing requirement)", cls: "muted" },
};
export const Tag = ({ cat }: { cat: keyof typeof CATEGORY }) =>
  <span className={`tag ${CATEGORY[cat].cls}`}>{CATEGORY[cat].text}</span>;

export const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

export const Unavailable = ({ what, why }: { what: string; why: string }) => (
  <div className="card" role="note">
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
      <div style={{ 
        width: '2rem', 
        height: '2rem', 
        borderRadius: '50%', 
        background: 'var(--bg-subtle)', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center',
        flexShrink: 0,
        fontSize: '1rem'
      }}>ℹ️</div>
      <div>
        <strong style={{ color: 'var(--fg)', display: 'block', marginBottom: '0.25rem' }}>{what}: unavailable</strong>
        <p style={{ margin: 0, color: 'var(--fg-muted)', fontSize: '0.875rem' }}>{why}</p>
      </div>
    </div>
  </div>
);

export function ErrorAlert({ error }: { error: unknown }) {
  const e = error instanceof ApiRequestError ? error : null;
  const title = e?.kind === "network"
    ? "Network Error"
    : e?.code === "llm_quota_exceeded"
      ? "AI Service Temporarily Unavailable"
      : e?.code === "llm_invalid_response"
        ? "AI Response Could Not Be Processed"
        : e
          ? `Request Rejected (HTTP ${e.status}${e.code ? `, ${e.code}` : ""})`
          : "Unexpected Error";
  const stage = e?.stage === "profile_analysis"
    ? "during CV profile extraction"
    : e?.stage === "career_recommendation"
      ? "during career recommendation"
      : e?.stage === "skill_gap_analysis"
        ? "during skill-gap analysis"
        : e?.stage === "learning_roadmap"
          ? "during roadmap generation"
          : e?.stage === "verification"
            ? "during verification"
            : e?.stage;
  return (
    <div className="banner bad" role="alert">
      <strong>⚠️ {title}</strong>
      <div>{e?.message ?? "Something went wrong. Please try again."}{stage ? ` Stage: ${stage}.` : ""}</div>
    </div>
  );
}

const STATUS: Record<FinalStatus, { cls: string; text: string; icon: string }> = {
  VERIFIED: { cls: "ok", text: "VERIFIED: Every verification check passed", icon: "✓" },
  VERIFICATION_FAILED: { cls: "bad", text: "VERIFICATION FAILED: Results below are NOT verified", icon: "⚠" },
  REVISION_LIMIT_REACHED: { cls: "bad", text: "REVISION LIMIT REACHED: Results below are NOT verified", icon: "⚠" },
};
export const StatusBanner = ({ status, revisions }: { status: FinalStatus; revisions: number }) => (
  <div className={`banner ${STATUS[status].cls}`} role="status">
    <strong>{STATUS[status].icon} {STATUS[status].text}</strong>
    <div className="text-sm">Revisions used: {revisions}</div>
  </div>
);

export const Section = ({ title, children }: { title: string; children: ReactNode }) =>
  <section aria-label={title}>
    <h2>{title}</h2>
    {children}
  </section>;

export const Card = ({ title, subtitle, children }: { title?: string; subtitle?: string; children: ReactNode }) => (
  <div className="card">
    {(title || subtitle) && (
      <div className="card-header">
        {title && <h3>{title}</h3>}
        {subtitle && <p>{subtitle}</p>}
      </div>
    )}
    <div className="card-body">
      {children}
    </div>
  </div>
);

export const EmptyState = ({ title, description, action }: { title: string; description: string; action?: ReactNode }) => (
  <div className="card" style={{ textAlign: 'center', padding: '3rem 2rem' }}>
    <div style={{ fontSize: '2.5rem', marginBottom: '1rem' }}>📋</div>
    <h3 style={{ margin: '0 0 0.5rem 0', color: 'var(--fg)', fontSize: '1.25rem' }}>{title}</h3>
    <p style={{ margin: '0 0 1.5rem 0', color: 'var(--fg-muted)', maxWidth: '400px', marginLeft: 'auto', marginRight: 'auto' }}>{description}</p>
    {action}
  </div>
);