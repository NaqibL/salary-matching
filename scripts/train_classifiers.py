"""Train new KMeans role-cluster + LR tier classifiers from current Supabase embeddings.

Outputs go to scripts/train_output/ — NOT to src/mcf/models/.
Review cluster_profiles_v2.csv and role_taxonomy_v2.json before promoting.

Usage:
    uv run python scripts/train_classifiers.py            # k-sweep, LLM naming
    uv run python scripts/train_classifiers.py --k 35    # fixed k, LLM naming
    uv run python scripts/train_classifiers.py --no-llm  # top-title heuristic naming

Environment:
    DATABASE_URL      Supabase connection string (required)
    ANTHROPIC_API_KEY Claude API key (required unless --no-llm)
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

import httpx
import numpy as np
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from sklearn.cluster import MiniBatchKMeans
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import LabelEncoder

warnings.filterwarnings("ignore")
load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "train_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EMBEDDING_DIMS = 768
MODEL_NAME = "BAAI/bge-base-en-v1.5"

TIER_MAP = {
    "Fresh/entry level":  "T1_Entry",
    "Non-executive":      "T1_Entry",
    "Junior Executive":   "T2_Junior",
    "Executive":          "T2_Junior",
    "Professional":       "T3_Senior",
    "Senior Executive":   "T3_Senior",
    "Manager":            "T4_Management",
    "Middle Management":  "T4_Management",
    "Senior Management":  "T4_Management",
    "C-Suite/VP":         "T4_Management",
}


# ──────────────────────────────────────────────────────────────────────────────
# 1. DATA FETCH
# ──────────────────────────────────────────────────────────────────────────────

def fetch_jobs() -> tuple[np.ndarray, list[dict]]:
    """Fetch all active embedded jobs from Supabase.

    Returns (X, records) where X is float32 (n, 768) and records is a list
    of dicts with job metadata needed for profiles and tier labelling.
    """
    print("Connecting to Supabase…")
    conn = psycopg2.connect(os.environ["DATABASE_URL"], options="-c statement_timeout=0")
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Fetching jobs + embeddings (may take a minute)…")
    cur.execute("""
        SELECT
            j.job_uuid,
            j.title,
            COALESCE(
                NULLIF(TRIM(BOTH '"' FROM (j.categories_json::jsonb->0)::text), ''),
                'Unknown'
            ) AS category,
            COALESCE(
                NULLIF(TRIM(BOTH '"' FROM (j.position_levels_json::jsonb->0)::text), ''),
                'Unknown'
            ) AS position_level,
            j.skills_json,
            e.embedding::text AS embedding_text
        FROM jobs j
        JOIN job_embeddings e ON e.job_uuid = j.job_uuid
        WHERE j.is_active = TRUE
          AND e.embedding IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    print(f"Fetched {len(rows):,} rows from Supabase")

    embeddings, records = [], []
    skipped = 0
    for r in rows:
        try:
            emb = json.loads(r["embedding_text"])
            if len(emb) != EMBEDDING_DIMS:
                skipped += 1
                continue
        except (json.JSONDecodeError, TypeError):
            skipped += 1
            continue

        try:
            skills = json.loads(r["skills_json"] or "[]")
            if not isinstance(skills, list):
                skills = []
        except (json.JSONDecodeError, TypeError):
            skills = []

        embeddings.append(emb)
        records.append({
            "job_uuid":       r["job_uuid"],
            "title":          (r["title"] or "").strip(),
            "category":       r["category"],
            "position_level": r["position_level"],
            "skills":         [s if isinstance(s, str) else s.get("skill", "") for s in skills],
        })

    if skipped:
        print(f"  Skipped {skipped:,} rows (wrong dims or parse error)")

    X = np.array(embeddings, dtype=np.float32)
    print(f"Embedding matrix: {X.shape[0]:,} jobs × {X.shape[1]} dims")
    return X, records


# ──────────────────────────────────────────────────────────────────────────────
# 2. K-MEANS — sweep or fixed k
# ──────────────────────────────────────────────────────────────────────────────

def kmeans_sweep(X: np.ndarray, k_min: int = 20, k_max: int = 45) -> int:
    """Silhouette sweep over k_min..k_max, return best k."""
    print(f"\nK-Means silhouette sweep k={k_min}…{k_max}…")
    rng = np.random.default_rng(42)
    sil_idx = rng.choice(len(X), size=min(10_000, len(X)), replace=False)
    X_sil = X[sil_idx]

    scores: dict[int, float] = {}
    for k in range(k_min, k_max + 1):
        km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=5, batch_size=4096)
        km.fit(X)
        labels_sil = km.labels_[sil_idx]
        score = silhouette_score(X_sil, labels_sil, metric="cosine")
        scores[k] = score
        print(f"  k={k:2d}  silhouette={score:.4f}")

    best_k = max(scores, key=scores.get)
    print(f"\nBest k={best_k}  silhouette={scores[best_k]:.4f}")

    sweep_path = OUTPUT_DIR / "kmeans_sweep_v2.json"
    sweep_path.write_text(json.dumps(scores, indent=2))
    print(f"Sweep scores saved -> {sweep_path}")
    return best_k


def fit_kmeans(X: np.ndarray, k: int) -> MiniBatchKMeans:
    print(f"\nFitting final KMeans k={k} (n_init=10)…")
    km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=10, batch_size=4096)
    km.fit(X)
    counts = Counter(km.labels_.tolist())
    sizes = sorted(counts.values(), reverse=True)
    print(f"  Cluster sizes: min={min(sizes)}, max={max(sizes)}, median={int(np.median(sizes))}")
    return km


# ──────────────────────────────────────────────────────────────────────────────
# 3. TIER CLASSIFIER (Logistic Regression)
# ──────────────────────────────────────────────────────────────────────────────

def fit_tier_classifier(X: np.ndarray, records: list[dict]) -> LogisticRegression:
    """Train LR to predict experience tier from embedding."""
    tiers = [TIER_MAP.get(r["position_level"]) for r in records]
    labeled_idx = [i for i, t in enumerate(tiers) if t is not None]
    X_lab = X[labeled_idx]
    y_lab = [tiers[i] for i in labeled_idx]

    dist = Counter(y_lab)
    print(f"\nTier label distribution ({len(labeled_idx):,} labeled / {len(records):,} total):")
    for tier in ["T1_Entry", "T2_Junior", "T3_Senior", "T4_Management"]:
        print(f"  {tier}: {dist.get(tier, 0):,}")

    le = LabelEncoder()
    y_enc = le.fit_transform(y_lab)

    print("Fitting LogisticRegression (max_iter=1000)…")
    lr = LogisticRegression(max_iter=1000, C=1.0, random_state=42)
    lr.fit(X_lab, y_enc)

    train_acc = lr.score(X_lab, y_enc)

    # Overwrite classes_ with string tier names so lr.predict() returns e.g. "T1_Entry"
    lr.classes_ = le.classes_

    print(f"  Training accuracy: {train_acc:.3f}  (not held-out — use as sanity check)")
    return lr


# ──────────────────────────────────────────────────────────────────────────────
# 4. CLUSTER PROFILES
# ──────────────────────────────────────────────────────────────────────────────

def build_profiles(records: list[dict], labels: np.ndarray) -> list[dict]:
    """Build per-cluster summary for taxonomy naming and CSV export."""
    from collections import defaultdict
    clusters: dict[int, list[dict]] = defaultdict(list)
    for rec, lbl in zip(records, labels):
        clusters[int(lbl)].append(rec)

    profiles = []
    for cid in sorted(clusters):
        jobs = clusters[cid]
        top_titles = [t for t, _ in Counter(r["title"] for r in jobs).most_common(10)]
        top_categories = [c for c, _ in Counter(r["category"] for r in jobs).most_common(3)]
        all_skills: list[str] = []
        for r in jobs:
            all_skills.extend(r["skills"])
        top_skills = [s for s, _ in Counter(all_skills).most_common(8) if s]
        tier_counts = Counter(TIER_MAP.get(r["position_level"]) for r in jobs)
        profiles.append({
            "cluster":        cid,
            "n_jobs":         len(jobs),
            "top_titles":     top_titles,
            "top_categories": top_categories,
            "top_skills":     top_skills,
            "tier_T1_Entry":       tier_counts.get("T1_Entry", 0),
            "tier_T2_Junior":      tier_counts.get("T2_Junior", 0),
            "tier_T3_Senior":      tier_counts.get("T3_Senior", 0),
            "tier_T4_Management":  tier_counts.get("T4_Management", 0),
        })

    profiles.sort(key=lambda p: p["n_jobs"], reverse=True)
    return profiles


def save_profiles_csv(profiles: list[dict], taxonomy: dict[int, str]) -> None:
    """Save a human-readable CSV for review."""
    import csv
    path = OUTPUT_DIR / "cluster_profiles_v2.csv"
    fieldnames = [
        "cluster", "name", "n_jobs",
        "top_titles", "top_categories", "top_skills",
        "tier_T1_Entry", "tier_T2_Junior", "tier_T3_Senior", "tier_T4_Management",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for p in profiles:
            writer.writerow({
                "cluster":       p["cluster"],
                "name":          taxonomy.get(p["cluster"], f"Cluster {p['cluster']}"),
                "n_jobs":        p["n_jobs"],
                "top_titles":    " | ".join(p["top_titles"][:5]),
                "top_categories": " | ".join(p["top_categories"]),
                "top_skills":    " | ".join(p["top_skills"][:5]),
                "tier_T1_Entry":      p["tier_T1_Entry"],
                "tier_T2_Junior":     p["tier_T2_Junior"],
                "tier_T3_Senior":     p["tier_T3_Senior"],
                "tier_T4_Management": p["tier_T4_Management"],
            })
    print(f"Cluster profiles saved -> {path}")


# ──────────────────────────────────────────────────────────────────────────────
# 5. TAXONOMY NAMING
# ──────────────────────────────────────────────────────────────────────────────

def _heuristic_name(profile: dict) -> str:
    """Fallback: derive name from most common title words."""
    titles = profile["top_titles"]
    if not titles:
        return f"Cluster {profile['cluster']}"
    words = Counter()
    stop = {"senior", "junior", "assistant", "associate", "manager", "officer",
            "executive", "specialist", "lead", "head", "staff", "general"}
    for t in titles[:5]:
        for w in t.lower().split():
            if w not in stop and len(w) > 2:
                words[w] += 1
    top = [w.title() for w, _ in words.most_common(3)]
    return " & ".join(top) if top else titles[0]


def name_clusters_llm(profiles: list[dict]) -> dict[int, str]:
    """Call Claude Haiku to assign a short role-category name to each cluster."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ANTHROPIC_API_KEY not set — falling back to heuristic naming")
        return {p["cluster"]: _heuristic_name(p) for p in profiles}

    # Build a compact JSON payload for all clusters in one API call
    cluster_data = [
        {
            "id":             p["cluster"],
            "n_jobs":         p["n_jobs"],
            "top_titles":     p["top_titles"][:8],
            "top_categories": p["top_categories"],
            "top_skills":     p["top_skills"][:6],
        }
        for p in profiles
    ]

    system_prompt = (
        "You are a job market analyst naming role categories for a Singapore jobs portal. "
        "Given a list of job clusters (each with top job titles, MCF categories, and skills), "
        "return a JSON object mapping each cluster id to a concise role category name "
        "(2–5 words, title case, specific enough to be useful as a filter label). "
        "Do not use generic words like 'Jobs' or 'Roles'. "
        "Respond with ONLY a JSON object like: {\"0\": \"Software Engineering\", \"1\": \"Sales & Business Development\", ...}"
    )

    user_prompt = (
        "Name each of these job clusters:\n\n"
        + json.dumps(cluster_data, indent=2)
    )

    print(f"\nCalling Claude Haiku to name {len(profiles)} clusters…")
    t0 = time.perf_counter()

    try:
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key":         api_key,
                "anthropic-version": "2023-06-01",
                "content-type":      "application/json",
            },
            json={
                "model":      "claude-haiku-4-5-20251001",
                "max_tokens": 1024,
                "system":     system_prompt,
                "messages":   [{"role": "user", "content": user_prompt}],
            },
            timeout=120.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        print(f"  LLM call failed ({e}) — falling back to heuristic naming")
        return {p["cluster"]: _heuristic_name(p) for p in profiles}

    elapsed = time.perf_counter() - t0
    print(f"  LLM responded in {elapsed:.1f}s")

    raw = resp.json()["content"][0]["text"].strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        named: dict[str, str] = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  Failed to parse LLM response ({e}) — falling back to heuristic naming")
        print(f"  Raw response:\n{raw[:500]}")
        return {p["cluster"]: _heuristic_name(p) for p in profiles}

    # Merge: LLM names + heuristic fallback for any missing clusters
    taxonomy: dict[int, str] = {}
    for p in profiles:
        llm_name = named.get(str(p["cluster"]))
        taxonomy[p["cluster"]] = llm_name if llm_name else _heuristic_name(p)

    missing = [p["cluster"] for p in profiles if str(p["cluster"]) not in named]
    if missing:
        print(f"  LLM missed clusters {missing} — used heuristic fallback for those")

    return taxonomy


def name_clusters_heuristic(profiles: list[dict]) -> dict[int, str]:
    return {p["cluster"]: _heuristic_name(p) for p in profiles}


# ──────────────────────────────────────────────────────────────────────────────
# 6. SAVE MODELS
# ──────────────────────────────────────────────────────────────────────────────

def save_models(km: MiniBatchKMeans, lr: LogisticRegression, taxonomy: dict[int, str]) -> None:
    km_path = OUTPUT_DIR / "kmeans_role_v2.pkl"
    lr_path = OUTPUT_DIR / "lr_tier_v2.pkl"
    tx_path = OUTPUT_DIR / "role_taxonomy_v2.json"

    with open(km_path, "wb") as f:
        pickle.dump(km, f)
    print(f"KMeans model saved   -> {km_path}")

    with open(lr_path, "wb") as f:
        pickle.dump(lr, f)
    print(f"LR tier model saved  -> {lr_path}")

    tx_path.write_text(json.dumps({str(k): v for k, v in sorted(taxonomy.items())}, indent=2, ensure_ascii=False))
    print(f"Taxonomy saved       -> {tx_path}")


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--k", type=int, default=None, help="Fix number of clusters (skip sweep)")
    parser.add_argument("--no-llm", action="store_true", help="Use heuristic cluster naming instead of Claude Haiku")
    args = parser.parse_args()

    t_start = time.perf_counter()

    # 1. Fetch data
    X, records = fetch_jobs()

    # 2. Find k
    if args.k:
        k = args.k
        print(f"\nUsing fixed k={k} (--k flag)")
    else:
        k = kmeans_sweep(X)

    # 3. Fit KMeans
    km = fit_kmeans(X, k)
    labels = km.labels_

    # 4. Fit tier LR
    lr = fit_tier_classifier(X, records)

    # 5. Build profiles
    profiles = build_profiles(records, labels)

    # 6. Name clusters
    if args.no_llm:
        print("\nUsing heuristic cluster naming (--no-llm flag)")
        taxonomy = name_clusters_heuristic(profiles)
    else:
        taxonomy = name_clusters_llm(profiles)

    # 7. Save models
    print()
    save_models(km, lr, taxonomy)

    # 8. Save CSV for review
    save_profiles_csv(profiles, taxonomy)

    # 9. Print summary table
    elapsed = time.perf_counter() - t_start
    print(f"\n{'─'*60}")
    print(f"  Training complete in {elapsed:.1f}s")
    print(f"  Jobs: {len(records):,}  |  Clusters: {k}  |  Model: {MODEL_NAME}")
    print(f"{'─'*60}")
    print(f"  {'ID':>3}  {'Name':<40}  {'Jobs':>6}")
    print(f"  {'─'*3}  {'─'*40}  {'─'*6}")
    for p in sorted(profiles, key=lambda p: p["cluster"]):
        name = taxonomy.get(p["cluster"], f"Cluster {p['cluster']}")
        print(f"  {p['cluster']:>3}  {name:<40}  {p['n_jobs']:>6,}")
    print(f"{'─'*60}")
    print(f"\nReview {OUTPUT_DIR / 'cluster_profiles_v2.csv'} before promoting to production.")
    print("When ready, run the promotion script (to be written after review).")


if __name__ == "__main__":
    main()
