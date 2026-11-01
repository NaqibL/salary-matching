"""Case study debug: Shopee BI Analyst — inspect global and company match behaviour."""
import os, json, sys
from dotenv import load_dotenv
load_dotenv()

from mcf.lib.storage.postgres_store import PostgresStore
from mcf.lib.embeddings.embedder import Embedder
from mcf.lib.embeddings.job_description_extractor import extract_high_signal_description

TITLE = "Business Intelligence Analyst (AI & Data Analytics)"
COMPANY = "Shopee"
DESCRIPTION = """The Business Intelligence and Data Analytics team is the engine behind our data-driven business iterations. We are looking for a forward-thinking Junior BI Analyst to support our AI transformation by helping to bridge the gap between traditional analytics and next-generation intelligence.

Data analysis: Conduct in-depth analysis to identify trends, patterns, and opportunities for the Shopee cross-border business organisation
AI-augmented support: Support senior leads in implementing AI initiatives that drive internal productivity and predictive business modelling
Efficiency via AI agents: Utilise and build internal AI agents to automate repetitive data tasks and streamline team workflows
Smart reporting: Evolve traditional BI dashboards into intelligent dashboards by incorporating predictive features and automated insight summaries

Requirements: Bachelor or Master degree in quantitative field. Min 1 year experience in Business Intelligence, Data Analytics, or Data Engineering. Proficiency in SQL and Python. Experience with BI tools such as Tableau, Power BI, or Google Looker Studio. Understanding of fundamental machine learning concepts. Hands-on experience with LLMs and prompt engineering."""

store = PostgresStore(os.environ["DATABASE_URL"])
embedder = Embedder()

desc_text, _ = extract_high_signal_description(DESCRIPTION, TITLE)
job_text = f"Job Title: {TITLE}\nDescription: {desc_text}"
vector = embedder.embed_text(job_text)

out = []

out.append("=== GLOBAL TOP-20 SIMILAR JOBS ===")
ranked = store.get_all_embedded_job_ids_ranked(vector, limit=500)
top_slice = ranked[:100]
uuid_to_score = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in top_slice}
jobs = store.get_jobs_with_salary_by_uuids(list(uuid_to_score.keys()))
jobs_sorted = sorted(jobs, key=lambda j: uuid_to_score.get(j["job_uuid"], 0), reverse=True)
for j in jobs_sorted[:20]:
    score = uuid_to_score.get(j["job_uuid"], 0)
    sal = f"{j.get('salary_min')}-{j.get('salary_max')}" if j.get("salary_min") else "no salary"
    active = "active" if j.get("is_active") else "expired"
    out.append(f"  {score:.4f}  {(j['title'] or '')[:60]:<60}  {(j.get('company_name') or '')[:25]:<25}  {active}  {sal}")

out.append("")
out.append("=== COMPANY MATCHES (Shopee) ===")
company_ranked = store.get_company_jobs_ranked(vector, COMPANY, limit=20)
if company_ranked:
    c_uuids = [uuid for uuid, _, _ in company_ranked]
    c_scores = {uuid: round(1.0 - dist, 4) for uuid, dist, _ in company_ranked}
    c_jobs = store.get_jobs_with_salary_by_uuids(c_uuids)
    c_jobs_sorted = sorted(c_jobs, key=lambda j: c_scores.get(j["job_uuid"], 0), reverse=True)
    for j in c_jobs_sorted:
        score = c_scores.get(j["job_uuid"], 0)
        sal = f"{j.get('salary_min')}-{j.get('salary_max')}" if j.get("salary_min") else "no salary"
        active = "active" if j.get("is_active") else "expired"
        out.append(f"  {score:.4f}  {(j['title'] or '')[:60]:<60}  {active}  {sal}")
else:
    out.append("  No company matches found")

out.append("")
out.append(f"Total global ranked: {len(ranked)}")
out.append(f"Total company ranked: {len(company_ranked) if company_ranked else 0}")

store.close()

result = "\n".join(out)
print(result)

output_path = "scripts/finetune/eval/casestudy_results.txt"
with open(output_path, "w", encoding="utf-8") as f:
    f.write(result)
print(f"\nSaved to {output_path}")
