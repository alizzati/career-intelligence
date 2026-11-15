"""
User Service — agent-facing interface for the user domain, mirroring
retrieval_service.py's role for the KB. The Profile Agent (Step 7) is the
primary consumer of get_user_full_profile(); other agents should not need
to touch user tables directly beyond that.
"""
from app.core.db import engine
from app.repositories import user_repository as repo
from app.schemas.user import (
    UserOut, UserProfileOut, EducationOut, ExperienceOut, ProjectOut,
    CertificationOut, UserSkillOut, UserSkillEvidenceOut, UserPreferencesOut,
    UserFullProfileOut, AcceptedEvidenceOut, EffectiveSkillOut, EvidenceCandidateOut,
)


def create_user(email: str, full_name: str) -> UserOut:
    with engine.begin() as conn:
        return UserOut(**repo.create_user(conn, email, full_name))


def set_profile(user_id: int, headline: str | None = None,
                 summary: str | None = None, target_domain: str | None = None) -> None:
    with engine.begin() as conn:
        repo.upsert_profile(conn, user_id, headline, summary, target_domain)


def add_education(user_id: int, institution: str, degree: str | None = None,
                   field_of_study: str | None = None, start_date=None, end_date=None,
                   description: str | None = None) -> EducationOut:
    with engine.begin() as conn:
        row = repo.create_education(conn, user_id, institution, degree, field_of_study,
                                     start_date, end_date, description)
    return EducationOut(**row)


def add_experience(user_id: int, company: str, role_title: str, employment_type: str | None = None,
                    start_date=None, end_date=None, description: str | None = None) -> ExperienceOut:
    with engine.begin() as conn:
        row = repo.create_experience(conn, user_id, company, role_title, employment_type,
                                      start_date, end_date, description)
    return ExperienceOut(**row)


def add_project(user_id: int, title: str, description: str | None = None,
                 url: str | None = None, role: str | None = None) -> ProjectOut:
    with engine.begin() as conn:
        row = repo.create_project(conn, user_id, title, description, url, role)
    return ProjectOut(**row)


def add_certification(user_id: int, name: str, issuer: str | None = None, issue_date=None,
                       expiry_date=None, credential_url: str | None = None) -> CertificationOut:
    with engine.begin() as conn:
        row = repo.create_certification(conn, user_id, name, issuer, issue_date, expiry_date, credential_url)
    return CertificationOut(**row)


def add_user_skill(user_id: int, claimed_skill: str, skill_id: str | None = None,
                    normalized_skill: str | None = None, proficiency: str | None = None) -> UserSkillOut:
    """
    Adds a claimed skill with NO evidence by default (evidence_status='none').
    This is deliberate: a claim is recorded as a claim, not silently
    promoted to 'verified' nor demoted to 'missing' (Section 4).
    """
    with engine.begin() as conn:
        row = repo.create_user_skill(conn, user_id, claimed_skill, skill_id, normalized_skill, proficiency)
    return UserSkillOut(**row, evidence=[])


def add_skill_evidence(user_skill_id: int, evidence_type: str, source_table: str | None = None,
                        source_id: int | None = None, description: str | None = None,
                        url: str | None = None, mark_linked: bool = True) -> UserSkillEvidenceOut:
    with engine.begin() as conn:
        row = repo.add_skill_evidence(conn, user_skill_id, evidence_type, source_table,
                                       source_id, description, url, mark_linked=mark_linked)
    return UserSkillEvidenceOut(**row)


# ---- Evidence acceptance (Stage 3.4.1) -----------------------------------------
def create_evidence_candidate(*, candidate_key: str, user_id: int, cv_id: str,
                              source_type: str, source_table: str,
                              source_id: int | None, skill_id: str | None,
                              claimed_skill: str | None, evidence_text: str | None,
                              evidence_span_hash: str | None,
                              structural_status: str = "pending",
                              structural_reason: str | None = None) -> dict:
    with engine.begin() as conn:
        return repo.create_evidence_candidate(
            conn, candidate_key=candidate_key, user_id=user_id, cv_id=cv_id,
            source_type=source_type, source_table=source_table, source_id=source_id,
            skill_id=skill_id, claimed_skill=claimed_skill, evidence_text=evidence_text,
            evidence_span_hash=evidence_span_hash, structural_status=structural_status,
            structural_reason=structural_reason,
        )


def update_evidence_candidate(candidate_id: int, **fields) -> dict | None:
    with engine.begin() as conn:
        return repo.update_evidence_candidate(conn, candidate_id, **fields)


def fetch_evidence_candidates(user_id: int, acceptance_status: str | None = None) -> list[dict]:
    with engine.connect() as conn:
        return repo.fetch_evidence_candidates(conn, user_id, acceptance_status)


def fetch_accepted_evidence(user_id: int) -> list[dict]:
    with engine.connect() as conn:
        return repo.fetch_accepted_evidence(conn, user_id)


def get_user_full_profile(user_id: int) -> UserFullProfileOut | None:
    with engine.connect() as conn:
        user_row = repo.fetch_user(conn, user_id)
        if user_row is None:
            return None
        profile_row = repo.fetch_profile(conn, user_id)
        education = [EducationOut(**r) for r in repo.fetch_education(conn, user_id)]
        experience = [ExperienceOut(**r) for r in repo.fetch_experience(conn, user_id)]
        projects = [ProjectOut(**r) for r in repo.fetch_projects(conn, user_id)]
        certifications = [CertificationOut(**r) for r in repo.fetch_certifications(conn, user_id)]

        accepted_by_skill: dict[str, list[AcceptedEvidenceOut]] = {}
        for row in repo.fetch_accepted_evidence(conn, user_id):
            accepted_by_skill.setdefault(row["skill_id"], []).append(AcceptedEvidenceOut(**row))
        evidence_candidates = [
            EvidenceCandidateOut(**row)
            for row in repo.fetch_evidence_candidate_decisions(conn, user_id)
        ]

        skills: list[UserSkillOut] = []
        for srow in repo.fetch_user_skills(conn, user_id):
            evidence = [UserSkillEvidenceOut(**e) for e in repo.fetch_skill_evidence(conn, srow["user_skill_id"])]
            accepted = accepted_by_skill.get(srow["skill_id"], []) if srow["skill_id"] else []
            skill_data = dict(srow)
            # Effective status comes ONLY from accepted evidence, never from
            # the legacy user_skills.evidence_status column (D-01/D-04).
            skill_data["evidence_status"] = "linked" if accepted else "none"
            skills.append(UserSkillOut(
                **skill_data, evidence=evidence, accepted_evidence=accepted,
                evidence_source="claim_and_evidence" if accepted else "claim",
            ))

        effective_skills: list[EffectiveSkillOut] = []
        claimed_skill_ids: set[str] = set()
        for skill in skills:
            if skill.skill_id is None:
                continue
            claimed_skill_ids.add(skill.skill_id)
            effective_skills.append(EffectiveSkillOut(
                skill_id=skill.skill_id,
                normalized_skill=skill.normalized_skill,
                claimed_skill=skill.claimed_skill,
                proficiency=skill.proficiency,
                user_skill_id=skill.user_skill_id,
                evidence_status=skill.evidence_status,
                source="claim_and_evidence" if skill.accepted_evidence else "claim",
                accepted_evidence=skill.accepted_evidence,
            ))
        # Evidence-derived skills: accepted evidence without an explicit claim.
        for skill_id, accepted in accepted_by_skill.items():
            if skill_id in claimed_skill_ids:
                continue
            effective_skills.append(EffectiveSkillOut(
                skill_id=skill_id,
                normalized_skill=accepted[0].canonical_name,
                claimed_skill=None,
                proficiency=None,
                user_skill_id=None,
                evidence_status="linked",
                source="evidence",
                accepted_evidence=accepted,
            ))

        prefs_row = repo.fetch_preferences(conn, user_id)

    return UserFullProfileOut(
        user=UserOut(**user_row),
        profile=UserProfileOut(**profile_row) if profile_row else None,
        education=education, experience=experience, projects=projects,
        certifications=certifications, skills=skills, effective_skills=effective_skills,
        evidence_candidates=evidence_candidates,
        preferences=UserPreferencesOut(**prefs_row) if prefs_row else None,
    )


def get_user_by_email(email: str):
    with engine.connect() as conn:
        user_row = repo.fetch_user_by_email(conn, email)
        if user_row is None:
            return None
        return UserOut(**user_row)
