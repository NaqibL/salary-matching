"""Role-family + seniority classification via TypeSafe Jev (OpenRouter decisions API).

Replaces the KMeans role clusters and logistic-regression tier model
(``mcf.matching.classifiers``) with a single LLM-free decision call per job.
Jev returns a choice (role family) and a score (seniority) with confidences;
it produces no free text, so the OpenRouter cleaner stays for skills/rewrite.

Usage
-----
    from mcf.lib.embeddings.jev_classifier import make_jev_classifier_from_env

    jev = make_jev_classifier_from_env()
    if jev:
        results = jev.classify_many([(title, description, position_levels), ...])

Environment variables
---------------------
OPENROUTER_API_KEY        Required (same key as the cleaner).
JEV_CLASSIFIER_ENABLED    Set to "0" to disable even when the key is present.
JEV_MODEL                 Optional, default typesafe/jev-1.14.
LLM_CLEAN_WORKERS         Reused as the default thread-pool size.

Cost: $0.042 per million input tokens, ~1,700 tokens per job (the 24 role
criteria ride along) → about $0.00007 per job. See tickets/SGSAL-022.md.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Iterable, Sequence

import httpx

JEV_URL = "https://openrouter.ai/api/alpha/decisions"
DEFAULT_JEV_MODEL = "typesafe/jev-1.14"

OTHER_ROLE_KEY = "other"

# Ordered: index + 1 is the stable integer id written to jobs.role_cluster so
# the existing matches filters keep working. Never reorder; append only.
ROLE_FAMILIES: list[tuple[str, str, str]] = [
    # (key, display name, criteria description shown to Jev)
    ("software_engineering", "Software Engineering",
     "Software developers, web/mobile/backend engineers, QA/test engineers, solution architects."),
    ("data_ai_analytics", "Data, AI & Analytics",
     "Data engineers, data scientists, ML/AI engineers, data/BI analysts, analytics."),
    ("it_infra_support_security", "IT Infrastructure, Support & Security",
     "IT support, helpdesk, sysadmin, network, cloud/DevOps infrastructure, cybersecurity, IT project managers."),
    ("sales_business_dev", "Sales & Business Development",
     "Sales executives, account managers, business development, pre-sales, relationship managers."),
    ("marketing_comms", "Marketing & Communications",
     "Marketing, digital marketing, brand, PR, communications, content, social media."),
    ("finance_accounting", "Finance & Accounting",
     "Accountants, accounts payable/receivable, audit, tax, financial reporting, finance managers, treasury."),
    ("banking_financial_services", "Banking & Financial Services",
     "Bank operations, wealth/private banking, insurance, trading, investment, credit, KYC/AML analysts."),
    ("legal_compliance_cosec", "Legal, Compliance & Corporate Secretarial",
     "Lawyers, legal counsel, compliance officers, regulatory, corporate secretarial."),
    ("human_resources", "Human Resources",
     "HR generalists, recruiters, talent acquisition, payroll, learning & development, HR business partners."),
    ("admin_office_support", "Admin & Office Support",
     "Admin assistants, secretaries, receptionists, office managers, executive assistants, data entry."),
    ("customer_service", "Customer Service",
     "Customer service officers, call centre agents, service desk (non-IT), client support, concierge."),
    ("operations_strategy_pm", "Operations, Strategy & Project Management",
     "Business operations, strategy, consulting, programme/project management (non-construction, non-IT), general management."),
    ("procurement_supply_chain_logistics", "Procurement, Supply Chain & Logistics",
     "Procurement, purchasing, supply chain planning, logistics coordination, freight, shipping."),
    ("warehouse_drivers_delivery", "Warehouse, Drivers & Delivery",
     "Warehouse assistants, storekeepers, forklift, packers, drivers, delivery riders, dispatch."),
    ("engineering_manufacturing", "Engineering & Manufacturing",
     "Mechanical/electrical/process/chemical engineers, production, manufacturing, quality engineers, R&D engineering (non-software)."),
    ("trades_technicians", "Trades & Technicians",
     "Electricians, plumbers, aircon/M&E technicians, mechanics, maintenance technicians, facilities technicians."),
    ("construction_architecture_property", "Construction, Architecture & Property",
     "Civil/structural engineers, site supervisors, quantity surveyors, architects, BIM, property/facilities/estate management."),
    ("healthcare_allied", "Healthcare & Allied Health",
     "Nurses, doctors, pharmacists, therapists, allied health, clinic/dental assistants, patient care."),
    ("education_social_services", "Education & Social Services",
     "Teachers, tutors, early childhood educators, trainers, social workers, counsellors, youth/community workers."),
    ("fnb_hospitality", "F&B & Hospitality",
     "Chefs, cooks, kitchen crew, baristas, servers, restaurant/hotel operations, housekeeping."),
    ("retail_beauty", "Retail & Beauty",
     "Retail sales assistants, store managers, cashiers, visual merchandising, beauticians, hair, spa, wellness."),
    ("cleaning_security_general_labour", "Cleaning, Security & General Labour",
     "Cleaners, facilities attendants, security officers, general workers, production operators without a trade."),
    ("creative_design", "Creative & Design",
     "Graphic/UX/UI designers, video, photography, interior design, animation, copywriters, media production."),
    ("science_research_lab", "Science, Research & Lab",
     "Lab technicians, research scientists, research assistants, biomedical/chemistry R&D (non-engineering)."),
]

ROLE_FAMILY_CRITERIA: dict[str, str] = {key: desc for key, _, desc in ROLE_FAMILIES}
ROLE_FAMILY_DISPLAY: dict[str, str] = {key: name for key, name, _ in ROLE_FAMILIES}
ROLE_FAMILY_DISPLAY[OTHER_ROLE_KEY] = "Other"
ROLE_FAMILY_ID: dict[str, int] = {key: i + 1 for i, (key, _, _) in enumerate(ROLE_FAMILIES)}
ROLE_FAMILY_ID[OTHER_ROLE_KEY] = 0


def role_family_rows() -> list[tuple[int, str, str, str]]:
    """(id, key, display_name, description) rows for the role_families table."""
    rows = [(ROLE_FAMILY_ID[k], k, n, d) for k, n, d in ROLE_FAMILIES]
    rows.append((0, OTHER_ROLE_KEY, "Other", "Low-confidence or unclassifiable postings."))
    return sorted(rows)


SENIORITY_LEVELS: list[str] = [
    "Entry: internship, fresh graduate, 0-2 years, non-executive or junior individual contributor",
    "Mid: 2-5 years experience, executive-level individual contributor, no people management",
    "Senior: 5+ years, senior/principal individual contributor, assistant manager, team lead who mostly does hands-on work",
    "Management: manages people or a function; manager, head of department, director, VP, C-suite",
]
TIER_FROM_IDX: list[str] = ["T1_Entry", "T2_Junior", "T3_Senior", "T4_Management"]

_ROLE_INSTRUCTIONS = (
    "Which role family best describes the job this posting is hiring for? "
    "Judge by the actual day-to-day work, not the industry of the employer."
)
_SENIORITY_INSTRUCTIONS = (
    "What seniority level is this role? Use stated years of experience, title words "
    "(junior/senior/manager/head), whether it manages people, and the employer-provided "
    "position levels if present (e.g. 'Professional' and 'Executive' usually mean Mid, "
    "'Senior Executive' means Senior, 'Manager' or above means Management)."
)


@dataclass(frozen=True)
class JevResult:
    role_key: str          # one of ROLE_FAMILY_CRITERIA keys, or "other"
    tier: str              # T1_Entry .. T4_Management
    role_conf: float
    tier_conf: float
    cost_usd: float = 0.0


def build_payload(
    title: str | None,
    description: str | None,
    position_levels: Sequence[str] | None = None,
    model: str = DEFAULT_JEV_MODEL,
) -> dict:
    state: dict = {
        "job_title": title or "Unknown",
        "job_description": (description or "")[:6000],
    }
    if position_levels:
        state["employer_position_levels"] = list(position_levels)
    return {
        "model": model,
        "state": state,
        "questions": {
            "role_family": {
                "type": "choice",
                "instructions": _ROLE_INSTRUCTIONS,
                "criteria": ROLE_FAMILY_CRITERIA,
            },
            "seniority": {
                "type": "score",
                "instructions": _SENIORITY_INSTRUCTIONS,
                "criteria": SENIORITY_LEVELS,
            },
        },
    }


def parse_response(data: dict, min_role_conf: float = 0.5) -> JevResult | None:
    """Turn a decisions API response into a JevResult; None if malformed."""
    try:
        answers = data["answers"]
        role = answers["role_family"]
        sen = answers["seniority"]
        role_key = str(role.get("choice", "")).strip()
        role_conf = float(role.get("confidence") or 0.0)
        tier_conf = float(sen.get("confidence") or 0.0)
        idx = int(round(float(sen["score"])))
    except (KeyError, TypeError, ValueError):
        return None
    if role_key not in ROLE_FAMILY_CRITERIA or role_conf < min_role_conf:
        role_key = OTHER_ROLE_KEY
    tier = TIER_FROM_IDX[max(0, min(len(TIER_FROM_IDX) - 1, idx))]
    cost = float((data.get("usage") or {}).get("cost") or 0.0)
    return JevResult(role_key=role_key, tier=tier, role_conf=role_conf, tier_conf=tier_conf, cost_usd=cost)


class JevClassifier:
    """Thread-safe client; one HTTP call per job, graceful None on failure."""

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_JEV_MODEL,
        timeout: float = 60.0,
        min_role_conf: float = 0.5,
        retries: int = 2,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self.model = model
        self._timeout = timeout
        self._min_role_conf = min_role_conf
        self._retries = retries
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def classify(
        self,
        title: str | None,
        description: str | None,
        position_levels: Sequence[str] | None = None,
    ) -> JevResult | None:
        if not (title or description):
            return None
        payload = build_payload(title, description, position_levels, model=self.model)
        headers = {"Authorization": f"Bearer {self._api_key}"}
        last_err: str = ""
        for attempt in range(self._retries + 1):
            try:
                resp = self._client.post(JEV_URL, json=payload, headers=headers)
                if resp.status_code == 200:
                    result = parse_response(resp.json(), self._min_role_conf)
                    if result is not None:
                        return result
                    # 200 with no usable answers: seen 2026-11-07 during a Jev
                    # degradation (every call for ~10 min). Retry like a 5xx and
                    # surface the body, otherwise the failure is silent.
                    last_err = f"HTTP 200 unparseable: {resp.text[:200]}"
                else:
                    last_err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    if 400 <= resp.status_code < 500 and resp.status_code != 429:
                        break  # not retryable
            except Exception as exc:  # noqa: BLE001
                last_err = repr(exc)
            if attempt < self._retries:
                time.sleep(1.5 * (attempt + 1))
        print(f"Warning: Jev classification failed ({last_err}); leaving job unclassified.")
        return None

    def classify_many(
        self,
        items: Iterable[tuple[str | None, str | None, Sequence[str] | None]],
        workers: int | None = None,
    ) -> list[JevResult | None]:
        """Classify many (title, description, position_levels) tuples in order."""
        items = list(items)
        if not items:
            return []
        if workers is None:
            workers = _default_workers()
        if workers <= 1 or len(items) == 1:
            return [self.classify(*it) for it in items]
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(lambda it: self.classify(*it), items))

    def close(self) -> None:
        self._client.close()


def _default_workers() -> int:
    raw = os.getenv("LLM_CLEAN_WORKERS", "").strip()
    try:
        return max(1, int(raw)) if raw else 8
    except ValueError:
        return 8


def make_jev_classifier_from_env() -> JevClassifier | None:
    """Build a JevClassifier from env; None when no key or explicitly disabled."""
    api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return None
    if os.getenv("JEV_CLASSIFIER_ENABLED", "1").strip().lower() in ("0", "false", "no"):
        return None
    model = os.getenv("JEV_MODEL", DEFAULT_JEV_MODEL).strip() or DEFAULT_JEV_MODEL
    return JevClassifier(api_key=api_key, model=model)
