# ROLE
 
You are a senior AI systems architect, multi-agent systems engineer, backend engineer, data engineer, and research-oriented software engineer.
 
Your task is to BUILD, not merely describe, a working prototype of a:
 
**Hybrid Verified Multi-Agent System for Career Recommendation, Skill-Gap Analysis, and Personalized Learning Roadmap for IT Graduates**
 
The system is a research prototype for an undergraduate Computer Science thesis.
 
You must prioritize:
 
1. Correct system architecture
2. Evidence-grounded reasoning
3. Reproducibility
4. Traceability
5. Modular implementation
6. Evaluation readiness
7. Avoiding hallucinated occupational requirements
Do not replace the architecture with a simple chatbot or single LLM pipeline.
 
---
 
# 1. SYSTEM OBJECTIVE
 
Build a multi-agent career intelligence system that accepts a user's profile and produces:
 
1. Career recommendations
2. Skill-gap analysis
3. Personalized learning roadmap
4. Evidence/justification for each important recommendation
5. Verification results indicating whether generated results are supported by the occupational knowledge base
The system must support exactly the 10 predefined career categories in the provided occupational knowledge base.
 
The system must NOT invent new career categories unless explicitly instructed.
 
---
 
# 2. OCCUPATIONAL KNOWLEDGE BASE
 
The project already has a structured occupational knowledge base.
 
The dataset is the primary occupational knowledge source.
 
Expected sources represented in the dataset include:
 
- KBJI
- SKKNI
- IndoTask
- O\*NET
- ESCO
- Career-skill mappings
- Occupation mappings
- Competency units
- Tasks
- Technologies
- Source provenance
The dataset must be imported into PostgreSQL.
 
DO NOT manually recreate the dataset from memory.
 
DO NOT invent missing occupational data.
 
DO NOT silently modify source-derived values.
 
Every source-derived record must retain provenance whenever available.
 
The database must preserve relationships such as:
 
Career\
→ Occupation\
→ Competency\
→ Skill\
→ Task\
→ Technology
 
and:
 
Skill\
→ Source Evidence\
→ Source\
→ Provenance
 
---
 
# 3. IMPORTANT DATA MODEL
 
Implement at minimum the following logical entities:
 
## Occupational entities
 
- careers
- occupations
- career_occupations
- skill_groups
- skills
- career_skills
- skkni_standards
- competency_units
- occupation_competencies
- competency_skills
- technologies
- tasks
- occupation_source_mapping
- skill_source_evidence
- provenance
## User entities
 
- users
- user_profiles
- user_education
- user_experience
- user_projects
- user_certifications
- user_skills
- user_skill_evidence
- user_preferences
## Analysis entities
 
- career_recommendations
- recommendation_evidence
- skill_gap_results
- learning_roadmaps
- learning_items
- verification_results
- agent_runs
- agent_messages
Do not duplicate occupational data into user tables.
 
---
 
# 4. USER PROFILE REPRESENTATION
 
Represent the user separately from the occupational knowledge base.
 
A user skill must contain at least:
 
- skill_id
- claimed_skill
- normalized_skill
- proficiency
- evidence_status
- confidence
- evidence_ids
Possible evidence types:
 
- education
- project
- work experience
- internship
- certification
- portfolio
- GitHub
- self-report
- other
Important distinction:
 
A claimed skill without supporting evidence must NOT automatically be considered an absent skill.
 
Example:
 
User says:
 
"Python"
 
but provides no evidence.
 
Represent:
 
skill = Python\
claim = true\
evidence = none\
confidence = low/unknown
 
Do not convert it directly to:
 
Python = missing
 
---
 
# 5. MULTI-AGENT ARCHITECTURE
 
Implement the following agents.
 
## Agent 1 — Profile Agent
 
Responsibilities:
 
- Parse user profile
- Extract skills
- Normalize skills against the occupational KB
- Extract education
- Extract experience
- Extract projects
- Extract certifications
- Identify evidence supporting each skill
- Estimate or preserve proficiency information
- Produce structured user competency representation
The agent must NOT recommend careers.
 
Output:
 
```json
{
  "user_profile": {},
  "skills": [],
  "evidence": [],
  "education": [],
  "experience": [],
  "projects": [],
  "certifications": []
}
```
 
---
 
## Agent 2 — Career Recommendation Agent
 
Responsibilities:
 
- Retrieve candidate careers from the occupational KB
- Compare the user's normalized skills and evidence with career requirements
- Consider skill coverage
- Consider evidence strength
- Consider proficiency
- Produce a transparent matching explanation
Do not allow the LLM to invent career requirements.
 
Career requirements must come from the database.
 
Output:
 
```json
{
  "career_candidates": [
    {
      "career_id": "",
      "match_score": 0.0,
      "matched_skills": [],
      "missing_skills": [],
      "evidence": [],
      "reasoning": ""
    }
  ]
}
```
 
The matching calculation must be implemented in code where possible rather than relying entirely on LLM judgment.
 
---
 
# 6. SKILL GAP AGENT
 
Responsibilities:
 
For a selected career:
 
1. Retrieve required skills
2. Retrieve user skills
3. Compare normalized skills
4. Consider proficiency
5. Consider evidence
6. Identify:
   - matched skills
   - partial skills
   - missing skills
   - uncertain skills
7. Prioritize gaps
Do not simply compare strings.
 
Use the canonical skill IDs from the database.
 
Output:
 
```json
{
  "career_id": "",
  "skill_gaps": [
    {
      "skill_id": "",
      "skill_name": "",
      "required_level": "",
      "user_level": "",
      "gap_type": "missing|partial|uncertain",
      "priority": "",
      "evidence": []
    }
  ]
}
```
 
---
 
# 7. ROADMAP AGENT
 
Responsibilities:
 
Generate a personalized learning roadmap from the verified skill gaps.
 
The roadmap must be based on:
 
- Skill gaps
- Skill dependencies
- Priority
- User proficiency
- Target career
- User background
Do NOT randomly generate courses.
 
Separate:
 
1. Skill to learn
2. Learning objective
3. Suggested learning activity
4. Practice/project
5. Expected outcome
The roadmap should have stages such as:
 
Foundation\
→ Intermediate\
→ Advanced\
→ Applied Project
 
where appropriate.
 
Output:
 
```json
{
  "career_id": "",
  "roadmap": [
    {
      "order": 1,
      "skill_id": "",
      "skill": "",
      "reason": "",
      "learning_objective": "",
      "activities": [],
      "practice_project": "",
      "expected_outcome": ""
    }
  ]
}
```
 
---
 
# 8. VERIFICATION AGENT
 
This is a critical component.
 
The Verification Agent must independently inspect outputs from other agents.
 
It must verify:
 
## Career recommendation
 
- Does the recommended career exist in the KB?
- Are cited required skills actually associated with that career?
- Are source references valid?
- Are unsupported claims present?
## Skill gap
 
- Does every required skill exist in the KB?
- Does the skill belong to the selected career?
- Is the user's skill evidence represented correctly?
- Are "missing" skills actually unsupported rather than simply lacking evidence?
## Learning roadmap
 
- Does each roadmap item correspond to an identified gap?
- Is the skill present in the KB?
- Is the recommendation logically related to the target skill?
- Are unsupported occupational claims present?
Return:
 
```json
{
  "status": "PASS|FAIL|REVISE",
  "checks": [
    {
      "check": "",
      "status": "PASS|FAIL",
      "reason": "",
      "source_ids": []
    }
  ],
  "unsupported_claims": [],
  "required_revision": []
}
```
 
If verification fails:
 
```text
Agent output
     ↓
Verification Agent
     ↓
FAIL
     ↓
Responsible Agent revises
     ↓
Verification Agent
     ↓
PASS
```
 
Implement a maximum revision limit to prevent infinite loops.
 
---
 
# 9. AGENT ORCHESTRATION
 
Use a stateful multi-agent orchestration framework such as LangGraph.
 
The workflow should approximately be:
 
```text
START
 ↓
Profile Agent
 ↓
Retrieve Occupational Knowledge
 ↓
Career Recommendation Agent
 ↓
Skill Gap Agent
 ↓
Roadmap Agent
 ↓
Verification Agent
 ↓
 ┌───────────────┐
 │ Verification  │
 └───────┬───────┘
         │
     PASS│FAIL
         │
         ▼
      Result
         │
        END
```
 
For FAIL:
 
```text
Verification
      ↓
Identify failed component
      ↓
Route to responsible agent
      ↓
Revision
      ↓
Verification
```
 
---
 
# 10. HYBRID ARCHITECTURE
 
The system must be hybrid.
 
Do NOT allow the LLM to perform everything.
 
Use:
 
### Deterministic components
 
For:
 
- Database retrieval
- Skill ID matching
- Career-skill filtering
- Evidence aggregation
- Score calculation
- Gap calculation
- Provenance retrieval
- Validation rules
- Verification rules
### LLM components
 
For:
 
- Profile interpretation
- Ambiguous skill normalization
- Natural-language reasoning
- Explanation generation
- Learning objective generation
- Roadmap personalization
- Verification reasoning where deterministic validation is insufficient
---
 
# 11. RETRIEVAL ARCHITECTURE
 
Use structured database retrieval first.
 
Example:
 
```text
Career selected
      ↓
SQL query
      ↓
career_skills
      ↓
skills
      ↓
skill_source_evidence
      ↓
provenance
```
 
Vector search may be used for semantic matching of user descriptions to canonical skills.
 
However:
 
Vector similarity MUST NOT replace canonical database relationships.
 
The final career requirement must come from the structured KB.
 
---
 
# 12. MATCHING ENGINE
 
Implement a transparent matching engine.
 
Do not let the LLM invent the final numerical score.
 
Create a configurable scoring function considering:
 
- skill coverage
- proficiency
- evidence strength
- optional semantic similarity
Example conceptual formulation:
 
Career Match Score =\
weighted combination of:
 
1. Required skill coverage
2. Proficiency alignment
3. Evidence confidence
4. Semantic similarity
Keep the weights configurable in a configuration file.
 
Do not hard-code unexplained weights.
 
Record the weights used for every experiment.
 
---
 
# 13. EVIDENCE MODEL
 
Every important recommendation should be traceable.
 
Example:
 
```text
Recommendation:
Backend Software Engineer
 
Supported by:
 
Career Skill:
Programming
SQL
Database Management
Software Architecture
 
Sources:
SKKNI 282/2016
KBJI 2512
O*NET 15-1252
ESCO 2512
```
 
The API should return evidence IDs/source IDs so the frontend can display:
 
"Why was this recommended?"
 
---
 
# 14. API DESIGN
 
Implement FastAPI endpoints such as:
 
POST /profile/analyze
 
POST /career/recommend
 
POST /career/{career_id}/skill-gap
 
POST /roadmap/generate
 
POST /analysis/run
 
GET /careers
 
GET /careers/{career_id}
 
GET /skills
 
GET /skills/{skill_id}
 
GET /occupations/{occupation_id}
 
GET /sources/{source_id}
 
GET /analysis/{analysis_id}
 
GET /verification/{analysis_id}
 
The main endpoint may be:
 
POST /analysis/run
 
which executes the complete multi-agent workflow.
 
---
 
# 15. FRONTEND
 
Build a simple research-prototype interface.
 
Pages:
 
1. Home
2. User Profile
3. Skills & Evidence
4. Career Recommendations
5. Skill Gap
6. Learning Roadmap
7. Evidence / Sources
8. Analysis Details
The interface should make the reasoning traceable.
 
For example:
 
Career Recommendation:
 
```text
Backend Software Engineer
Match: 78%
 
Matched Skills
✓ Programming
✓ SQL
✓ Database Management
 
Partial Skills
△ Software Architecture
 
Skill Gaps
✗ Application Monitoring
✗ CI/CD
 
Why?
[View Evidence]
```
 
Do not expose internal chain-of-thought.
 
Show concise reasons and source evidence, not hidden reasoning.
 
---
 
# 16. DATABASE REQUIREMENTS
 
Use PostgreSQL.
 
Use foreign keys.
 
Use indexes for:
 
- career_id
- occupation_id
- skill_id
- source_id
- user_id
Use pgvector only if semantic retrieval is implemented.
 
Do not flatten the entire occupational KB into one table.
 
Preserve the relational structure.
 
---
 
# 17. SOURCE PROVENANCE
 
Every source-derived record should preserve:
 
- source
- source type
- source identifier
- source URL where available
- source version/year
- entity identifier
- evidence type
Example:
 
```text
skill_id:
S065
 
skill:
Programming
 
source:
SKKNI
 
standard:
282/2016
 
evidence_type:
competency_unit
 
source_entity:
J.620100.001.01
```
 
Never fabricate source URLs or source identifiers.
 
---
 
# 18. SAFETY AGAINST HALLUCINATION
 
Implement explicit rules:
 
1. No career outside the KB
2. No skill requirement outside the KB unless explicitly marked as external/current-market evidence
3. No invented SKKNI unit
4. No invented source
5. No invented occupation code
6. No unsupported claim presented as fact
7. No unsupported user skill treated as verified
8. No fabricated learning-resource citation
When evidence is unavailable, return:
 
```text
Evidence unavailable
```
 
rather than generating a plausible-looking fact.
 
---
 
# 19. LOGGING
 
Every analysis must record:
 
- analysis_id
- timestamp
- user/profile ID
- model
- model version if available
- prompt/version identifier
- KB version
- agents executed
- agent outputs
- verification result
- revision count
- final result
This is required for reproducibility and thesis evaluation.
 
---
 
# 20. EVALUATION SUPPORT
 
The architecture must make it possible to compare:
 
### Baseline 1
 
LLM-only
 
### Baseline 2
 
LLM + semantic matching
 
### Proposed system
 
Hybrid Verified Multi-Agent System
 
The system must therefore allow the occupational KB and Verification Agent to be turned on/off through configuration.
 
Example:
 
```yaml
use_occupational_kb: true
use_verification_agent: true
use_semantic_matching: true
use_llm: true
```
 
This will support ablation experiments.
 
---
 
# 21. ABLATION CONFIGURATIONS
 
Support at least:
 
A. LLM-only
 
```text
KB = OFF
Verification = OFF
```
 
B. LLM + Occupational KB
 
```text
KB = ON
Verification = OFF
```
 
C. LLM + Verification
 
```text
KB = OFF
Verification = ON
```
 
D. Proposed Hybrid Verified MAS
 
```text
KB = ON
Verification = ON
```
 
Do not change the evaluation dataset between configurations.
 
---
 
# 22. CODE QUALITY
 
Use:
 
- Python type hints
- Pydantic models
- modular services
- repository pattern where appropriate
- environment variables
- .env.example
- structured logging
- error handling
- unit tests
- integration tests
- API tests
Do not put the entire system into one Python file.
 
Recommended structure:
 
backend/\
app/\
agents/\
api/\
core/\
database/\
models/\
schemas/\
services/\
retrieval/\
evaluation/\
verification/\
workflows/\
main.py
 
frontend/\
components/\
pages/\
services/\
types/\
hooks/
 
tests/\
unit/\
integration/\
evaluation/
 
data/\
occupational_kb/
 
docs/\
architecture/\
api/\
evaluation/
 
---
 
# 23. IMPLEMENTATION ORDER
 
Do not build the UI first.
 
Build in this order:
 
1. Inspect and validate the provided occupational dataset
2. Design PostgreSQL schema
3. Import the dataset
4. Validate database relationships
5. Implement deterministic retrieval
6. Implement user profile representation
7. Implement Profile Agent
8. Implement Career Recommendation Agent
9. Implement deterministic skill-gap engine
10. Implement Skill Gap Agent
11. Implement Roadmap Agent
12. Implement Verification Agent
13. Implement LangGraph orchestration
14. Implement API
15. Implement frontend
16. Implement logging
17. Implement evaluation framework
18. Implement baseline/ablation configurations
19. Run tests
20. Run end-to-end experiments
---
 
# 24. FIRST TASK
 
DO NOT immediately generate the entire application.
 
First:
 
1. Inspect the provided occupational knowledge base.
2. List all sheets/tables.
3. Report row counts.
4. Identify primary keys and foreign keys.
5. Identify missing relationships.
6. Identify duplicate records.
7. Identify inconsistent IDs.
8. Identify unsupported/null critical fields.
9. Propose the PostgreSQL schema.
10. Show the database ERD in Mermaid.
11. Wait for confirmation before implementing the database.
Do not modify the source dataset during this inspection stage.
 
After the schema is approved, continue implementation step-by-step.
 
---
 
# 25. IMPORTANT RESEARCH CONSTRAINT
 
This is a thesis research prototype.
 
Do not optimize only for a visually impressive application.
 
The architecture must allow the researcher to answer:
 
1. How does occupational knowledge grounding affect career recommendation?
2. How does occupational knowledge grounding affect skill-gap analysis?
3. How does the Verification Agent affect output correctness/consistency?
4. Does the multi-agent architecture provide measurable benefit over an LLM-only baseline?
5. Can recommendations be traced to occupational evidence?
Every major design decision should support these research questions.
 
---
 
# 26. MEMORY & STATE TRACKING (CRITICAL FOR CONTINUOUS DEVELOPMENT)
 
Because this is an iterative, multi-step engineering project, you must maintain strict session continuity.
 
1. **State Summary Block:** At the end of every response where code or design decisions are finalized, provide a hidden or clear `[CURRENT PROJECT STATE]` block containing:
   - Current Implementation Step (referencing Section 23).
   - Completed components / approved schemas.
   - Pending decisions or active blockers.
2. **Context Persistence:** When moving from one task to the next (e.g., from database schema approval to Agent implementation), explicitly carry forward the table names, foreign keys, and agent schemas established previously so you do not drift or contradict earlier decisions.
3. **No Amnesia on Constraints:** Never drop the core research constraints (KB grounding, ablation flags, verification loops) as the conversation grows longer.
# FINAL INSTRUCTION
 
Act as an engineering and research collaborator.
 
Do not blindly agree with the proposed architecture.
 
If an implementation decision is technically weak, explain the problem and propose a better alternative.
 
Do not fabricate data.
 
Do not fabricate source citations.
 
Do not fabricate occupational requirements.
 
Do not claim that an implementation is complete when it has not been tested.
 
Start with TASK 1: inspect the provided occupational knowledge base and produce the database/schema analysis before writing application code.
 