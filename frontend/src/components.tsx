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
  <div className="card muted" role="note"><strong>{what}: unavailable.</strong> {why}</div>
);

export function ErrorAlert({ error }: { error: unknown }) {
  const e = error instanceof ApiRequestError ? error : null;
  const title = e?.kind === "network"
    ? "Network error"
    : e?.code === "llm_quota_exceeded"
      ? "AI service temporarily unavailable"
      : e?.code === "llm_invalid_response"
        ? "AI response could not be processed"
        : e
          ? `Request rejected (HTTP ${e.status}${e.code ? `, ${e.code}` : ""})`
          : "Unexpected error";
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
      <strong>{title}</strong>
      <div>{e?.message ?? "Something went wrong."}{stage ? ` Stage: ${stage}.` : ""}</div>
    </div>
  );
}

const STATUS: Record<FinalStatus, { cls: string; text: string }> = {
  VERIFIED: { cls: "ok", text: "VERIFIED: every verification check passed." },
  VERIFICATION_FAILED: { cls: "bad", text: "VERIFICATION FAILED: results below are NOT verified." },
  REVISION_LIMIT_REACHED: { cls: "bad", text: "REVISION LIMIT REACHED: results below are NOT verified." },
};
export const StatusBanner = ({ status, revisions }: { status: FinalStatus; revisions: number }) => (
  <div className={`banner ${STATUS[status].cls}`} role="status">
    <strong>{STATUS[status].text}</strong> Revisions used: {revisions}.
  </div>
);

export const Section = ({ title, children }: { title: string; children: ReactNode }) =>
  <section aria-label={title}><h2>{title}</h2>{children}</section>;
