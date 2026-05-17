"""
Similarity score distribution analysis.

Embeds synthetic resumes and job descriptions across diverse fields using the
same BGE model and pipeline as production, then reports pairwise cosine
similarity statistics to understand score compression.

Run:
    uv run python scripts/similarity_analysis.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from mcf.lib.embeddings.embedder import Embedder

# ---------------------------------------------------------------------------
# Synthetic data — 5 fields, 3 resumes + 3 jobs each
# ---------------------------------------------------------------------------

RESUMES: dict[str, list[str]] = {
    "Software Engineering": [
        """
        Senior Software Engineer with 7 years of experience building distributed backend systems.
        Proficient in Python, Go, and TypeScript. Deep experience with Kubernetes, PostgreSQL,
        Redis, and AWS. Led migration of monolith to microservices at fintech startup. Strong
        background in system design, API design, and code review. Contributed to open-source
        projects including FastAPI and SQLAlchemy. B.Sc. Computer Science, NUS.
        """,
        """
        Full-Stack Developer specialising in React and Node.js. 4 years building SaaS products.
        Experience with Next.js, GraphQL, Prisma, and Vercel. Comfortable with Docker and CI/CD
        pipelines. Previously at e-commerce startup where I owned the checkout and payments flow.
        Diploma in Information Technology, Temasek Polytechnic.
        """,
        """
        Junior developer fresh out of bootcamp. Built several portfolio projects in JavaScript
        and Python. Familiar with Git, REST APIs, and basic SQL. Completed a 3-month internship
        doing QA automation with Selenium. Eager to join a team and grow quickly.
        """,
    ],
    "Nursing": [
        """
        Registered Nurse with 10 years of ICU experience. Certified in Advanced Cardiac Life
        Support (ACLS) and Paediatric Advanced Life Support (PALS). Expert in ventilator
        management, central line care, and haemodynamic monitoring. Experienced charge nurse
        who has mentored over 20 junior nurses. B.Sc. Nursing, National University of Singapore.
        """,
        """
        Staff Nurse, 3 years in surgical ward. Competent in post-op care, wound management,
        pain assessment, and patient education. Familiar with electronic health records (EHR)
        and medication administration. BCLS certified. Diploma in Nursing, Nanyang Polytechnic.
        """,
        """
        Community health nurse with 5 years working in home care and chronic disease management.
        Manage caseload of diabetic and hypertensive patients. Conduct health screenings and
        patient education sessions. Coordinate with GPs and allied health professionals.
        """,
    ],
    "Marketing": [
        """
        Digital Marketing Manager, 6 years experience. Expertise in SEO, SEM, Meta Ads, and
        Google Analytics 4. Led campaigns generating $2M ARR for B2B SaaS clients. Proficient
        in HubSpot, Salesforce, and Tableau. Content strategy and copywriting background.
        B.A. Communications, SMU.
        """,
        """
        Social media specialist with 2 years managing brand accounts on TikTok, Instagram, and
        LinkedIn. Grown organic following from 5k to 80k for lifestyle brand. Skilled in
        short-form video production, community management, and influencer outreach. Diploma in
        Mass Communications.
        """,
        """
        Brand manager at FMCG company, 4 years. Experience running ATL and BTL campaigns,
        managing agency relationships, and conducting consumer research. Launched 3 new product
        lines with $500k marketing budgets. Worked closely with supply chain on packaging design.
        """,
    ],
    "Finance": [
        """
        CFA Charterholder with 8 years in equity research. Coverage of technology and
        semiconductor sectors across APAC. Experienced in DCF, comparable company analysis,
        and earnings modelling. Published research notes distributed to 200+ institutional
        clients. Previously at Goldman Sachs and UBS. B.Sc. Finance, NTU.
        """,
        """
        Financial analyst, 3 years in FP&A at manufacturing conglomerate. Responsible for
        monthly management accounts, budget consolidation, and variance analysis. Advanced
        Excel and Power BI. Exposure to ERP systems (SAP). ACCA qualified.
        """,
        """
        Recent finance graduate with internship experience in corporate banking. Familiar with
        credit analysis, financial statement review, and loan documentation. Proficient in Excel
        and Bloomberg Terminal basics. Passed CFA Level 1.
        """,
    ],
    "Teaching": [
        """
        Secondary school mathematics teacher with 9 years of experience. Specialise in A-Level
        and O-Level Additional Mathematics. Department head for 3 years, coordinating curriculum
        and professional development. Developed differentiated worksheets adopted school-wide.
        B.Ed. (Hons) Mathematics, NIE.
        """,
        """
        Primary school English teacher, 5 years. Focus on reading comprehension and creative
        writing. Run after-school reading club. Trained in Thinking Classroom methodology.
        PGDE (Primary), NIE. Keen interest in EdTech and classroom gamification.
        """,
        """
        Private tutor for PSLE Science and Mathematics, 4 years. Manage a roster of 15 students.
        Developed proprietary structured notes and timed practice system. Strong track record
        with students improving 2+ grade bands. B.Sc. Life Sciences.
        """,
    ],
}

JOBS: dict[str, list[str]] = {
    "Software Engineering": [
        """
        Job Title: Senior Backend Engineer
        Required Skills: Python, PostgreSQL, Redis, Kubernetes, AWS, REST APIs, system design
        Seniority: Senior (5+ years)
        Role Type: Permanent
        Description: Join our platform team building the data infrastructure powering 10M users.
        You will own the design and delivery of high-throughput microservices, mentor junior
        engineers, and drive architectural decisions. Strong Python and distributed systems
        experience required. Experience with event-driven architecture (Kafka) a plus.
        """,
        """
        Job Title: Frontend Developer
        Required Skills: React, TypeScript, Next.js, CSS, REST APIs, Git
        Seniority: Mid (2–4 years)
        Role Type: Permanent
        Description: We are looking for a frontend developer to join our product team. You will
        build and maintain consumer-facing web features, collaborate closely with design, and
        contribute to our component library. Experience with state management (Zustand/Redux)
        and performance optimisation preferred.
        """,
        """
        Job Title: Junior Software Engineer
        Required Skills: JavaScript, Python, SQL, Git, REST APIs
        Seniority: Junior (0–2 years)
        Role Type: Permanent
        Description: Entry-level role for a motivated developer to join our growing engineering
        team. You will build features under senior guidance, write unit tests, and participate
        in code reviews. We value curiosity and a growth mindset over raw experience.
        """,
    ],
    "Nursing": [
        """
        Job Title: ICU Staff Nurse
        Required Skills: ICU nursing, ventilator management, ACLS, PALS, haemodynamic monitoring
        Seniority: Senior (5+ years)
        Role Type: Permanent
        Description: Tertiary hospital seeking experienced ICU nurse to join our 20-bed cardiac
        ICU. You will provide critical care for complex cardiac and post-surgical patients, lead
        bedside procedures, and precept new hires. ACLS and PALS certification required.
        """,
        """
        Job Title: Staff Nurse (Surgical Ward)
        Required Skills: post-operative care, wound management, EHR, medication administration
        Seniority: Mid (2–5 years)
        Role Type: Permanent
        Description: General hospital hiring staff nurse for busy surgical ward. Responsibilities
        include post-op patient monitoring, wound care, discharge planning, and patient education.
        EHR proficiency and BCLS certification required.
        """,
        """
        Job Title: Community Nurse
        Required Skills: home care, chronic disease management, patient education, care coordination
        Seniority: Mid (3+ years)
        Role Type: Permanent
        Description: Community health provider seeking nurse for home-visit caseload. You will
        manage patients with diabetes, hypertension, and COPD; conduct health assessments; and
        liaise with GPs and social workers to deliver holistic care.
        """,
    ],
    "Marketing": [
        """
        Job Title: Digital Marketing Manager
        Required Skills: SEO, SEM, Google Analytics, Meta Ads, HubSpot, content strategy
        Seniority: Senior (5+ years)
        Role Type: Permanent
        Description: SaaS company seeking a data-driven digital marketing manager to own
        acquisition strategy. You will manage paid and organic channels, build campaign
        reporting dashboards, and work with the product team on conversion optimisation.
        """,
        """
        Job Title: Social Media Executive
        Required Skills: Instagram, TikTok, content creation, community management, copywriting
        Seniority: Junior (1–3 years)
        Role Type: Permanent
        Description: Lifestyle brand looking for a creative social media executive. Responsibilities
        include creating short-form video content, scheduling posts, engaging with followers, and
        coordinating with influencers. Passion for trends and brand storytelling essential.
        """,
        """
        Job Title: Brand Manager
        Required Skills: brand strategy, ATL/BTL campaigns, consumer research, agency management
        Seniority: Mid (3–6 years)
        Role Type: Permanent
        Description: FMCG company hiring a brand manager to lead a portfolio of household products.
        You will develop annual brand plans, manage media agencies, conduct shopper research, and
        work cross-functionally with trade marketing and supply chain.
        """,
    ],
    "Finance": [
        """
        Job Title: Equity Research Analyst
        Required Skills: financial modelling, DCF, comparable analysis, Bloomberg, CFA
        Seniority: Senior (6+ years)
        Role Type: Permanent
        Description: Investment bank seeking senior equity research analyst for TMT coverage.
        You will produce initiating coverage and update reports, build detailed financial models,
        host investor calls, and collaborate with sales and trading. CFA designation required.
        """,
        """
        Job Title: FP&A Analyst
        Required Skills: financial planning, budgeting, variance analysis, Excel, Power BI, SAP
        Seniority: Mid (2–4 years)
        Role Type: Permanent
        Description: Multinational manufacturer seeking FP&A analyst to support regional
        finance team. Responsibilities include monthly close, budget vs actuals reporting,
        business partnering with operations, and building management dashboards in Power BI.
        """,
        """
        Job Title: Credit Analyst (Graduate)
        Required Skills: credit analysis, financial statements, Excel, Bloomberg
        Seniority: Junior (0–2 years)
        Role Type: Permanent
        Description: Bank hiring graduate credit analyst for its corporate banking team. You will
        assist RMs with credit assessments, prepare credit proposals, and monitor existing
        facilities. Strong Excel and analytical skills required. CFA Level 1 a bonus.
        """,
    ],
    "Teaching": [
        """
        Job Title: Secondary Mathematics Teacher
        Required Skills: O-Level / A-Level Mathematics, curriculum planning, differentiated instruction
        Seniority: Senior (7+ years)
        Role Type: Permanent
        Description: Government secondary school hiring experienced mathematics teacher. You will
        teach A-Level Further Mathematics, lead the math department, and mentor beginning teachers.
        NIE-trained candidates preferred. Experience with e-pedagogy and SLS a plus.
        """,
        """
        Job Title: Primary English Teacher
        Required Skills: PSLE English, reading instruction, classroom management, EdTech
        Seniority: Mid (3–6 years)
        Role Type: Permanent
        Description: Primary school seeking English teacher with a passion for literacy. You will
        teach P4–P6 English, develop reading programmes, and leverage EdTech tools to personalise
        learning. PGDE-trained with experience in differentiated instruction preferred.
        """,
        """
        Job Title: Private Tutor / Tuition Teacher
        Required Skills: PSLE Science, PSLE Mathematics, student assessment, structured teaching
        Seniority: Junior (1–3 years)
        Role Type: Part-time
        Description: Tuition centre seeking part-time tutor for PSLE Science and Mathematics.
        You will conduct small-group sessions, create practice materials, and track student
        progress. Strong subject knowledge and ability to explain concepts simply are key.
        """,
    ],
}

FIELDS = list(RESUMES.keys())


def cosine_sim(a: list[float], b: list[float]) -> float:
    va, vb = np.array(a), np.array(b)
    return float(np.dot(va, vb) / (np.linalg.norm(va) * np.linalg.norm(vb) + 1e-10))


def section(title: str) -> None:
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)


def main() -> None:
    print("Loading BGE model...")
    embedder = Embedder()
    print("Model loaded.\n")

    # Embed everything
    print("Embedding resumes and jobs...")
    resume_embs: dict[str, list[list[float]]] = {}
    job_embs: dict[str, list[list[float]]] = {}

    for field in FIELDS:
        resume_embs[field] = [embedder.embed_resume(r.strip()) for r in RESUMES[field]]
        job_embs[field] = [embedder.embed_text(j.strip()) for j in JOBS[field]]

    print("Done.\n")

    # -----------------------------------------------------------------------
    # 1. Same-field similarities (resume i ↔ job i, i.e. aligned pairs)
    # -----------------------------------------------------------------------
    section("SAME-FIELD MATCHED PAIRS (resume[i] vs job[i] in same field)")
    same_field_scores: list[float] = []

    for field in FIELDS:
        print(f"\n  {field}:")
        for i, (r_emb, j_emb) in enumerate(zip(resume_embs[field], job_embs[field])):
            sim = cosine_sim(r_emb, j_emb)
            same_field_scores.append(sim)
            print(f"    Resume {i+1} vs Job {i+1}: {sim:.4f}")

    print(f"\n  -> Range: {min(same_field_scores):.4f} - {max(same_field_scores):.4f}")
    print(f"  -> Mean:  {np.mean(same_field_scores):.4f}  Std: {np.std(same_field_scores):.4f}")

    # -----------------------------------------------------------------------
    # 2. Cross-field similarities (every resume against every job in OTHER fields)
    # -----------------------------------------------------------------------
    section("CROSS-FIELD MISMATCHED PAIRS (resume from field A vs job from field B)")
    cross_field_scores: list[float] = []

    for r_field in FIELDS:
        for j_field in FIELDS:
            if r_field == j_field:
                continue
            for r_emb in resume_embs[r_field]:
                for j_emb in job_embs[j_field]:
                    cross_field_scores.append(cosine_sim(r_emb, j_emb))

    print(f"\n  Total cross-field pairs: {len(cross_field_scores)}")
    print(f"  Range: {min(cross_field_scores):.4f} – {max(cross_field_scores):.4f}")
    print(f"  Mean:  {np.mean(cross_field_scores):.4f}  Std: {np.std(cross_field_scores):.4f}")
    percentiles = np.percentile(cross_field_scores, [25, 50, 75, 90, 95])
    print(f"  Percentiles — p25: {percentiles[0]:.4f}  p50: {percentiles[1]:.4f}  "
          f"p75: {percentiles[2]:.4f}  p90: {percentiles[3]:.4f}  p95: {percentiles[4]:.4f}")

    # -----------------------------------------------------------------------
    # 3. Full pairwise matrix — all resumes vs all jobs
    # -----------------------------------------------------------------------
    section("FULL PAIRWISE MATRIX (all resumes × all jobs)")

    all_resume_labels: list[str] = []
    all_resume_embs: list[list[float]] = []
    all_job_labels: list[str] = []
    all_job_embs: list[list[float]] = []

    for field in FIELDS:
        for i, emb in enumerate(resume_embs[field]):
            all_resume_labels.append(f"{field[:4]}R{i+1}")
            all_resume_embs.append(emb)
        for i, emb in enumerate(job_embs[field]):
            all_job_labels.append(f"{field[:4]}J{i+1}")
            all_job_embs.append(emb)

    all_scores: list[float] = []
    for r_emb in all_resume_embs:
        for j_emb in all_job_embs:
            all_scores.append(cosine_sim(r_emb, j_emb))

    print(f"\n  Total pairs: {len(all_scores)}")
    print(f"  Global range: {min(all_scores):.4f} – {max(all_scores):.4f}")
    print(f"  Global mean:  {np.mean(all_scores):.4f}  Std: {np.std(all_scores):.4f}")

    pcts = np.percentile(all_scores, [5, 10, 25, 50, 75, 90, 95])
    print(f"  p5={pcts[0]:.4f}  p10={pcts[1]:.4f}  p25={pcts[2]:.4f}  "
          f"p50={pcts[3]:.4f}  p75={pcts[4]:.4f}  p90={pcts[5]:.4f}  p95={pcts[6]:.4f}")

    # -----------------------------------------------------------------------
    # 4. Per-field summary: how well does same-field rank above cross-field?
    # -----------------------------------------------------------------------
    section("PER-FIELD DISCRIMINATION: same-field score vs cross-field noise floor")

    for r_field in FIELDS:
        same_scores = [cosine_sim(r, j) for r, j in zip(resume_embs[r_field], job_embs[r_field])]
        noise_scores: list[float] = []
        for j_field in FIELDS:
            if j_field == r_field:
                continue
            for r_emb in resume_embs[r_field]:
                for j_emb in job_embs[j_field]:
                    noise_scores.append(cosine_sim(r_emb, j_emb))

        gap = np.mean(same_scores) - np.mean(noise_scores)
        print(f"\n  {r_field}:")
        print(f"    Same-field mean: {np.mean(same_scores):.4f}   "
              f"Cross-field mean: {np.mean(noise_scores):.4f}   Gap: {gap:+.4f}")
        print(f"    Same-field range: {min(same_scores):.4f}–{max(same_scores):.4f}   "
              f"Cross-field range: {min(noise_scores):.4f}–{max(noise_scores):.4f}")


if __name__ == "__main__":
    main()
