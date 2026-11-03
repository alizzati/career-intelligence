import type { ReactNode } from "react";
import { ApiRequestError } from "./services/api";
import type { FinalStatus, GapStatus } from "./types/api";

/* ------------------------------------------------------------------ */
/* Icons (inline, dependency-free)                                     */
/* ------------------------------------------------------------------ */

export type IconName =
  | "home"
  | "user"
  | "target"
  | "layers"
  | "chart"
  | "map"
  | "database"
  | "shield"
  | "menu"
  | "close"
  | "info"
  | "check"
  | "alert"
  | "sparkles"
  | "activity"
  | "upload"
  | "refresh"
  | "file"
  | "clock"
  | "trending";

const ICON_PATHS: Record<IconName, ReactNode> = {
  home: (
    <>
      <path d="M3 10.5 12 3l9 7.5" />
      <path d="M5 9.5V21h14V9.5" />
      <path d="M9 21v-6h6v6" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20c0-3.5 3.1-6 7-6s7 2.5 7 6" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="1" />
    </>
  ),
  layers: (
    <>
      <path d="m12 3 9 5-9 5-9-5 9-5Z" />
      <path d="m3 12 9 5 9-5" />
      <path d="m3 16 9 5 9-5" />
    </>
  ),
  chart: (
    <>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20H2" />
    </>
  ),
  map: (
    <>
      <path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3V6Z" />
      <path d="M9 3v15" />
      <path d="M15 6v15" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v7c0 1.7 3.6 3 8 3s8-1.3 8-3V5" />
      <path d="M4 12v7c0 1.7 3.6 3 8 3s8-1.3 8-3v-7" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3 20 6v6c0 5-3.4 8.2-8 9-4.6-.8-8-4-8-9V6l8-3Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  menu: (
    <>
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
    </>
  ),
  close: (
    <>
      <path d="m6 6 12 12" />
      <path d="M18 6 6 18" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5" />
      <path d="M12 8h.01" />
    </>
  ),
  check: <path d="m5 13 4 4 10-10" />,
  alert: (
    <>
      <path d="M12 3 2.5 20h19L12 3Z" />
      <path d="M12 9v5" />
      <path d="M12 17h.01" />
    </>
  ),
  sparkles: (
    <>
      <path d="m12 3 1.8 4.7L18.5 9.5l-4.7 1.8L12 16l-1.8-4.7L5.5 9.5l4.7-1.8L12 3Z" />
      <path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" />
    </>
  ),
  activity: <path d="M3 12h4l2.5-7 4 14 2.5-7H21" />,
  upload: (
    <>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 11a8 8 0 1 0-2.3 6.3" />
      <path d="M20 4v7h-7" />
    </>
  ),
  file: (
    <>
      <path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9l-6-6Z" />
      <path d="M14 3v6h6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  trending: (
    <>
      <path d="m3 17 6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </>
  ),
};

export const Icon = ({ name, className = "" }: { name: IconName; className?: string }) => (
  <svg
    className={`icon ${className}`.trim()}
    viewBox="0 0 24 24"
    aria-hidden="true"
    focusable="false"
  >
    {ICON_PATHS[name]}
  </svg>
);

/* ------------------------------------------------------------------ */
/* Domain badges and formatting                                        */
/* ------------------------------------------------------------------ */

// Labels are text, never colour-only. Four frozen categories stay distinct.
export const CATEGORY: Record<GapStatus | "unmatched", { text: string; cls: string }> = {
  matched_evidenced: { text: "✓ Matched – evidenced", cls: "ok" },
  matched_claimed_only: { text: "△ Matched – claimed only (no linked evidence)", cls: "warn" },
  missing: { text: "✗ Missing (required, not in profile)", cls: "bad" },
  unmatched: { text: "? Unmatched user claim (not a missing requirement)", cls: "muted" },
};

export const Tag = ({ cat }: { cat: keyof typeof CATEGORY }) => (
  <span className={`tag ${CATEGORY[cat].cls}`}>{CATEGORY[cat].text}</span>
);

export const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

/* ------------------------------------------------------------------ */
/* Shared building blocks                                              */
/* ------------------------------------------------------------------ */

export const Unavailable = ({ what, why }: { what: string; why: string }) => (
  <div className="notice" role="note">
    <span className="notice-icon">
      <Icon name="info" />
    </span>
    <div>
      <strong>{what}: unavailable</strong>
      <p>{why}</p>
    </div>
  </div>
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
    <div className="alert alert-danger" role="alert">
      <Icon name="alert" className="alert-icon" />
      <div className="alert-body">
        <strong className="alert-title">{title}</strong>
        <div className="alert-text">
          {e?.message ?? "Something went wrong. Please try again."}
          {stage ? ` Stage: ${stage}.` : ""}
        </div>
      </div>
    </div>
  );
}

const STATUS: Record<FinalStatus, { tone: "ok" | "bad"; text: string; icon: IconName }> = {
  VERIFIED: {
    tone: "ok",
    text: "VERIFIED: Every verification check passed",
    icon: "check",
  },
  VERIFICATION_FAILED: {
    tone: "bad",
    text: "VERIFICATION FAILED: Results below are NOT verified",
    icon: "alert",
  },
  REVISION_LIMIT_REACHED: {
    tone: "bad",
    text: "REVISION LIMIT REACHED: Results below are NOT verified",
    icon: "alert",
  },
};

export const StatusBanner = ({ status, revisions }: { status: FinalStatus; revisions: number }) => (
  <div className={`alert alert-${STATUS[status].tone}`} role="status">
    <Icon name={STATUS[status].icon} className="alert-icon" />
    <div className="alert-body">
      <strong className="alert-title">{STATUS[status].text}</strong>
      <div className="alert-text">Revisions used: {revisions}</div>
    </div>
  </div>
);

export const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="section" aria-label={title}>
    <div className="section-heading">
      <h2>{title}</h2>
    </div>
    {children}
  </section>
);

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

export type Tone = "indigo" | "emerald" | "amber" | "rose" | "slate" | "cyan";

export const StatCard = ({
  label,
  value,
  hint,
  tone = "slate",
  icon,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
  tone?: Tone;
  icon?: IconName;
}) => (
  <div className={`stat-card tone-${tone}`}>
    <div className="stat-top">
      <span className="stat-label">{label}</span>
      {icon && (
        <span className="stat-icon">
          <Icon name={icon} />
        </span>
      )}
    </div>
    <div className="stat-value">{value}</div>
    {hint && <div className="stat-hint">{hint}</div>}
  </div>
);

export const ProgressRing = ({
  value,
  label = "Score",
  size = 76,
}: {
  value: number;
  label?: string;
  size?: number;
}) => {
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  const stroke = 7;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const tone = clamped >= 0.7 ? "emerald" : clamped >= 0.5 ? "amber" : "rose";
  return (
    <div
      className={`ring ring-${tone}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={`${label}: ${pct(clamped)}`}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle
          className="ring-track"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          fill="none"
        />
        <circle
          className="ring-value"
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          fill="none"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped)}
          strokeLinecap="round"
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      <span className="ring-label">{pct(clamped)}</span>
    </div>
  );
};

export const MetaRow = ({ label, value }: { label: string; value: ReactNode }) => (
  <div className="meta-row">
    <span className="meta-label">{label}</span>
    <span className="meta-value">{value}</span>
  </div>
);

export const EmptyState = ({ title, description, action }: { title: string; description: string; action?: ReactNode }) => (
  <div className="empty-state">
    <div className="empty-icon">
      <Icon name="file" />
    </div>
    <h3>{title}</h3>
    <p>{description}</p>
    {action && <div className="empty-action">{action}</div>}
  </div>
);
