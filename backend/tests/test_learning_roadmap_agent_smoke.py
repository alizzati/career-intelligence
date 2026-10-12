"""Smoke test joining the existing Step 10 agent to the roadmap agent and live KB."""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text

from app.agents.learning_roadmap_agent import LearningRoadmapAgent
from app.agents.skill_gap_agent import SkillGapAgent
from app.core.db import engine
from app.services import retrieval_service as rs
from app.services import user_service as us


class SummaryLLM:
    def complete_json(self, system, user, max_tokens=2000):
        assert "focus_items" in user
        return {
            "summary": (
                "This focus list follows the existing skill-gap result and occupational "
                "knowledge-base evidence."
            )
        }


def main():
    user_id = None
    try:
        user = us.create_user(
            f"learning_roadmap_smoke_{uuid.uuid4().hex[:10]}@example.com",
            "Learning Roadmap Smoke Test",
        )
        user_id = user.user_id
        career = rs.get_all_careers()[0]

        # Step 10 produces the authoritative Step 9 classification consumed below.
        skill_gap = SkillGapAgent(llm_client=None).run(user_id, career.career_id)
        roadmap = LearningRoadmapAgent(llm_client=SummaryLLM()).run(skill_gap)

        expected_ids = {
            item.skill_id
            for item in skill_gap.skill_gap.matched_claimed_only + skill_gap.skill_gap.missing
        }
        assert roadmap.skill_gap is skill_gap.skill_gap
        assert {item.skill_id for item in roadmap.items} == expected_ids
        assert all(item.knowledge_base_basis for item in roadmap.items)
        assert roadmap.narrative_source == "llm" and roadmap.llm_error is None
        assert not any(item.gap_status == "matched_evidenced" for item in roadmap.items)
        print(
            f"PASS: Step 10 -> roadmap for {career.career_id}; "
            f"{len(roadmap.items)} grounded focus item(s), source={roadmap.narrative_source}"
        )
    finally:
        if user_id is not None:
            with engine.begin() as conn:
                conn.execute(text("DELETE FROM users WHERE user_id = :uid"), {"uid": user_id})
            print(f"Cleaned up smoke-test user {user_id}.")


if __name__ == "__main__":
    main()
