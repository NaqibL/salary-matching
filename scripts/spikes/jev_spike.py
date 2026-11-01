"""THROWAWAY SPIKE — compare Jev (TypeSafe via OpenRouter) labels against the
current KMeans/LR classifiers, the MCF-provided position level, and the Gemini
labels used for fine-tuning.

Reads only local data (no DB needed):
  data/finetune/jobs_sample.jsonl          title + description
  data/finetune/labels.jsonl               Gemini seniority/function labels
  data/job_embeddings_v2.parquet           embeddings -> current classifier output
  scripts/cluster_analysis_output/jobs_df.parquet   MCF position_level

Usage (from repo root):
  uv run python <scratchpad>/jev_spike.py --n 50 [--seed 1]
"""
from __future__ import annotations

import argparse, asyncio, json, os, random, sys, time
sys.stdout.reconfigure(encoding="utf-8")
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
from dotenv import load_dotenv

ROOT = Path(r"C:\Users\Luqman\Desktop\projects\salary-matching")
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
JEV_MODEL = "typesafe/jev-1.14"

ROLE_FAMILIES = {
    "software_engineering": "Software developers, web/mobile/backend engineers, QA/test engineers, solution architects.",
    "data_ai_analytics": "Data engineers, data scientists, ML/AI engineers, data/BI analysts, analytics.",
    "it_infra_support_security": "IT support, helpdesk, sysadmin, network, cloud/DevOps infrastructure, cybersecurity, IT project managers.",
    "sales_business_dev": "Sales executives, account managers, business development, pre-sales, relationship managers.",
    "marketing_comms": "Marketing, digital marketing, brand, PR, communications, content, social media.",
    "finance_accounting": "Accountants, accounts payable/receivable, audit, tax, financial reporting, finance managers, treasury.",
    "banking_financial_services": "Bank operations, wealth/private banking, insurance, trading, investment, credit, KYC/AML analysts.",
    "legal_compliance_cosec": "Lawyers, legal counsel, compliance officers, regulatory, corporate secretarial.",
    "human_resources": "HR generalists, recruiters, talent acquisition, payroll, learning & development, HR business partners.",
    "admin_office_support": "Admin assistants, secretaries, receptionists, office managers, executive assistants, data entry.",
    "customer_service": "Customer service officers, call centre agents, service desk (non-IT), client support, concierge.",
    "operations_strategy_pm": "Business operations, strategy, consulting, programme/project management (non-construction, non-IT), general management.",
    "procurement_supply_chain_logistics": "Procurement, purchasing, supply chain planning, logistics coordination, freight, shipping.",
    "warehouse_drivers_delivery": "Warehouse assistants, storekeepers, forklift, packers, drivers, delivery riders, dispatch.",
    "engineering_manufacturing": "Mechanical/electrical/process/chemical engineers, production, manufacturing, quality engineers, R&D engineering (non-software).",
    "trades_technicians": "Electricians, plumbers, aircon/M&E technicians, mechanics, maintenance technicians, facilities technicians.",
    "construction_architecture_property": "Civil/structural engineers, site supervisors, quantity surveyors, architects, BIM, property/facilities/estate management.",
    "healthcare_allied": "Nurses, doctors, pharmacists, therapists, allied health, clinic/dental assistants, patient care.",
    "education_social_services": "Teachers, tutors, early childhood educators, trainers, social workers, counsellors, youth/community workers.",
    "fnb_hospitality": "Chefs, cooks, kitchen crew, baristas, servers, restaurant/hotel operations, housekeeping.",
    "retail_beauty": "Retail sales assistants, store managers, cashiers, visual merchandising, beauticians, hair, spa, wellness.",
    "cleaning_security_general_labour": "Cleaners, facilities attendants, security officers, general workers, production operators without a trade.",
    "creative_design": "Graphic/UX/UI designers, video, photography, interior design, animation, copywriters, media production.",
    "science_research_lab": "Lab technicians, research scientists, research assistants, biomedical/chemistry R&D (non-engineering).",
}

SENIORITY_LEVELS = [
    "Entry: internship, fresh graduate, 0-2 years, non-executive or junior individual contributor",
    "Mid: 2-5 years experience, executive-level individual contributor, no people management",
    "Senior: 5+ years, senior/principal individual contributor, assistant manager, team lead who mostly does hands-on work",
    "Management: manages people or a function; manager, head of department, director, VP, C-suite",
]
TIER_FROM_IDX = ["T1_Entry", "T2_Junior", "T3_Senior", "T4_Management"]


def load_sample(n: int, seed: int) -> pd.DataFrame:
    emb = pd.read_parquet(ROOT / "data/job_embeddings_v2.parquet")
    jobs_df = pd.read_parquet(ROOT / "scripts/cluster_analysis_output/jobs_df.parquet",
                              columns=["job_uuid", "position_level"])
    labels = pd.read_json(ROOT / "data/finetune/labels.jsonl", lines=True)
    labels = labels.drop_duplicates("job_uuid")
    common = set(emb.job_uuid) & set(jobs_df.job_uuid) & set(labels.job_uuid)
    rng = random.Random(seed)
    # stream the big jsonl once, keep only candidates
    wanted = set(rng.sample(sorted(common), min(n * 3, len(common))))
    rows = []
    with open(ROOT / "data/finetune/jobs_sample.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            if d["job_uuid"] in wanted and d.get("description"):
                rows.append(d)
                if len(rows) >= n:
                    break
    df = pd.DataFrame(rows)
    df = df.merge(emb, on="job_uuid").merge(jobs_df, on="job_uuid").merge(labels, on="job_uuid")
    return df


def current_classifier(df: pd.DataFrame) -> pd.DataFrame:
    from mcf.matching.classifiers import classify_jobs, role_name
    X = np.vstack(df.embedding.values).astype(np.float32)
    res = classify_jobs(X)
    df["cur_role"] = [role_name(c) for c, _ in res]
    df["cur_tier"] = [t for _, t in res]
    return df


async def ask_jev(client: httpx.AsyncClient, title: str, desc: str, sem: asyncio.Semaphore) -> dict:
    payload = {
        "model": JEV_MODEL,
        "state": {"job_title": title, "job_description": desc[:6000]},
        "questions": {
            "role_family": {
                "type": "choice",
                "instructions": "Which role family best describes the job this posting is hiring for? Judge by the actual day-to-day work, not the industry of the employer.",
                "criteria": ROLE_FAMILIES,
            },
            "seniority": {
                "type": "score",
                "instructions": "What seniority level is this role? Use stated years of experience, title words (junior/senior/manager/head), and whether it manages people.",
                "criteria": SENIORITY_LEVELS,
            },
        },
    }
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"}
    async with sem:
        for attempt in range(3):
            try:
                t0 = time.perf_counter()
                r = await client.post(JEV_URL, json=payload, headers=headers, timeout=60)
                dt = time.perf_counter() - t0
                if r.status_code == 200:
                    j = r.json()
                    j["_latency"] = dt
                    return j
                err = r.text[:300]
            except Exception as e:  # noqa: BLE001
                err = repr(e)
            await asyncio.sleep(1.5 * (attempt + 1))
    return {"_error": err}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    df = load_sample(a.n, a.seed)
    print(f"sample: {len(df)} jobs")
    df = current_classifier(df)

    sem = asyncio.Semaphore(a.workers)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[
            ask_jev(client, r.title, r.description, sem) for r in df.itertuples()
        ])

    cost = 0.0; in_tok = 0; lat = []
    jev_role, jev_role_conf, jev_tier, jev_tier_conf = [], [], [], []
    errors = 0
    for res in results:
        if "_error" in res:
            errors += 1
            jev_role.append("ERR"); jev_role_conf.append(0); jev_tier.append("ERR"); jev_tier_conf.append(0)
            continue
        u = res.get("usage", {})
        cost += float(u.get("cost") or 0); in_tok += int(u.get("input_tokens") or 0)
        lat.append(res["_latency"])
        ans = res["answers"]
        rf, sn = ans["role_family"], ans["seniority"]
        jev_role.append(rf["choice"]); jev_role_conf.append(round(rf.get("confidence", 0), 2))
        idx = int(round(sn["score"]))
        jev_tier.append(TIER_FROM_IDX[max(0, min(3, idx))]); jev_tier_conf.append(round(sn.get("confidence", 0), 2))
    df["jev_role"] = jev_role; df["jev_role_conf"] = jev_role_conf
    df["jev_tier"] = jev_tier; df["jev_tier_conf"] = jev_tier_conf

    pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 42); pd.set_option("display.max_rows", 200)
    cols = ["title", "cur_role", "jev_role", "jev_role_conf", "position_level", "cur_tier", "jev_tier", "jev_tier_conf", "seniority"]
    out = df[cols].rename(columns={"seniority": "gemini_sen", "position_level": "mcf_level"})
    print(out.to_string())

    print("\n=== summary ===")
    print(f"jobs: {len(df)}  errors: {errors}")
    print(f"tier agreement Jev vs current LR: {(df.jev_tier == df.cur_tier).mean():.0%}")
    print(f"input tokens: {in_tok}  total cost: ${cost:.5f}  per job: ${cost/max(1,len(df)-errors):.6f}")
    if lat:
        print(f"latency p50: {np.median(lat):.2f}s  p95: {np.percentile(lat,95):.2f}s")
    print(f"low-confidence role (<0.5): {(df.jev_role_conf < 0.5).sum()}")
    if a.out:
        out.to_csv(a.out, index=False)
        print("saved", a.out)


if __name__ == "__main__":
    asyncio.run(main())
