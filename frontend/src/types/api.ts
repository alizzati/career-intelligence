// Mirrors backend/app/schemas/{api,career_fit,skill_gap,skill_gap_agent,learning_roadmap,verification}.py
export type FinalStatus = "VERIFIED" | "VERIFICATION_FAILED" | "REVISION_LIMIT_REACHED";
export type CheckStatus = "PASS" | "FAIL" | "REVISE";
export type GapStatus = "matched_evidenced" | "matched_claimed_only" | "missing";

export interface SkillRef { skill_id: string; canonical_name: string; evidence_class: string }
export interface ScoreBreakdown {
  total_weight: number; total_contribution: number; core_required_count: number;
  supporting_required_count: number; matched_linked_count: number; matched_claimed_only_count: number;
  missing_count: number; weights_used: Record<string, unknown>;
}
export interface CareerRecommendation {
  career_id: string; canonical_name: string; domain: string; fit_score: number;
  score_breakdown: ScoreBreakdown; matched_skills: SkillRef[]; claimed_only_skills: SkillRef[];
  missing_skills_preview: SkillRef[]; reasoning: string; reasoning_source: string;
}
export interface MatchedUserClaim { claimed_skill: string; proficiency: string | null; evidence_status: string; evidence_count: number }
export interface SkillGapItem {
  skill_id: string; canonical_name: string; status: GapStatus; evidence_class: string; kb_confidence: string;
  weight: number; contribution: number; matched_user_claim: MatchedUserClaim | null;
}
export interface UnmatchedUserClaim {
  user_skill_id: number; claimed_skill: string; proficiency: string | null;
  evidence_status: string; evidence_count: number; note: string;
}
export interface SkillGapResult {
  user_id: number; career_id: string; canonical_name: string; domain: string; fit_score: number;
  total_weight: number; total_contribution: number; score_breakdown: ScoreBreakdown;
  matched_evidenced: SkillGapItem[]; matched_claimed_only: SkillGapItem[]; missing: SkillGapItem[];
  unmatched_user_claims: UnmatchedUserClaim[];
}
export interface SkillObservation { skill_ids: string[]; text: string }
export interface UnmatchedClaimObservation { user_skill_ids: number[]; text: string }
export interface SkillGapNarrative {
  summary: string; strengths: SkillObservation[]; claimed_only_observations: SkillObservation[];
  missing_skill_observations: SkillObservation[]; unmatched_claim_observations: UnmatchedClaimObservation[];
  conclusion: string;
}
export interface SkillGapAnalysis {
  skill_gap: SkillGapResult; narrative: SkillGapNarrative;
  narrative_source: "llm" | "llm-partial" | "fallback-template"; llm_error: string | null; validation_notes: string[];
}
export interface RoadmapItem {
  skill_id: string; canonical_name: string; gap_status: "matched_claimed_only" | "missing";
  evidence_class: string; kb_confidence: string; knowledge_base_basis: string;
  learning_action: "develop_skill" | "add_linked_evidence";
}
export interface Roadmap {
  skill_gap: SkillGapResult; items: RoadmapItem[]; summary: string;
  narrative_source: "llm" | "fallback-template"; llm_error: string | null;
}
export interface VerificationCheck { check: string; status: CheckStatus; reason: string; source_ids: string[] }
export interface UnsupportedClaim { component: string; claim: string; source_ids: string[] }
export interface Verification {
  status: CheckStatus; checks: VerificationCheck[]; unsupported_claims: UnsupportedClaim[];
  required_revision: string[]; llm_error: string | null;
}
export interface AnalysisResponse {
  user_id: number; source: "cv_upload" | "existing_profile"; final_status: FinalStatus; verified: boolean;
  revision_count: number; target_career_id: string | null;
  document: { format: string; size_bytes: number; page_count: number | null; character_count: number } | null;
  redaction: { detected_types: string[]; replacement_count: number } | null;
  profile_extraction: { skills_persisted: number; evidence_persisted: number } | null;
  recommendations: CareerRecommendation[]; skill_gap: SkillGapAnalysis | null;
  roadmap: Roadmap | null; verification: Verification | null;
}
