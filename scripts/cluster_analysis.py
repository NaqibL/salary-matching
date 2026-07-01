"""Cluster analysis for active jobs embedded with bge-base-sgmarket-v2 (768-dim).

Usage:
    uv run python scripts/cluster_analysis.py
    uv run python scripts/cluster_analysis.py --plot-only   # reuse cached data

Outputs go to scripts/cluster_analysis_output/:
    umap_by_tier.html, umap_by_category.html, umap_by_salary.html,
    umap_hdbscan.html, umap_by_cluster.html, kmeans_sweep.html,
    cluster_profiles.html, cluster_profiles.csv,
    salary_distributions.html, salary_viability.csv, summary.json

The salary_* outputs answer: "are clusters good enough to compute reliable
salary percentiles?" — used to evaluate the 'best-value jobs' feature.
"""

from __future__ import annotations

import json
import os
import pickle
import sys
import warnings
from collections import Counter
from pathlib import Path

import hdbscan
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import psycopg2
import psycopg2.extras
import umap
from dotenv import load_dotenv
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score
from sklearn.model_selection import cross_val_score
from sklearn.neighbors import KNeighborsClassifier

warnings.filterwarnings("ignore")
load_dotenv()

OUTPUT_DIR = Path(__file__).parent / "cluster_analysis_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

EMBEDDING_DIMS = 768
MODEL_NAME = "NaqibL/bge-base-sgmarket-v2"

SENIORITY_LEVELS = ["Intern", "Entry", "Junior", "Mid", "Senior", "Lead", "Manager", "Director"]
SENIORITY_COLORS = {
    "Intern":    "#90CAF9",
    "Entry":     "#2196F3",
    "Junior":    "#4CAF50",
    "Mid":       "#8BC34A",
    "Senior":    "#FF9800",
    "Lead":      "#FF5722",
    "Manager":   "#F44336",
    "Director":  "#9C27B0",
    "Unknown":   "#CCCCCC",
}
# v1 baselines (BAAI/bge-base-en-v1.5) — beat these to confirm v2 improves clustering
V1_SILHOUETTE   = 0.054
V1_KNN_CV       = 0.620
V1_MEAN_PURITY  = 0.164

# Salary viability thresholds — cluster level
SALARY_MIN_COVERAGE = 0.30
SALARY_MIN_JOBS     = 50
SALARY_MAX_CV       = 0.60

# Salary viability thresholds — stratified (cluster × seniority) level
# Groups are smaller so we relax min_jobs; CV target is tighter since seniority variance is removed
STRAT_MIN_COVERAGE  = 0.30
STRAT_MIN_JOBS      = 20
STRAT_MAX_CV        = 0.50


# ──────────────────────────────────────────────────────────────────────────────
# 1. DATA FETCH
# ──────────────────────────────────────────────────────────────────────────────

def fetch_jobs(active_only: bool = False, sample: int = 50_000) -> tuple[np.ndarray, pd.DataFrame]:
    """Return (X, df) — random sample of embedded jobs (sample=0 fetches all)."""
    print("Connecting to Supabase...")
    conn = psycopg2.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=0,
        keepalives=1,
        keepalives_idle=60,
        keepalives_interval=10,
        keepalives_count=5,
        options="-c statement_timeout=0 -c idle_in_transaction_session_timeout=0",
    )
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SET statement_timeout = 0")
    cur.execute("SET idle_in_transaction_session_timeout = 0")

    active_filter = "AND j.is_active = TRUE" if active_only else ""

    if sample > 0 and not active_only:
        # pg_class catalog estimate — instant, no table scan
        cur.execute("SELECT reltuples::bigint AS estimate FROM pg_class WHERE relname = 'job_embeddings'")
        total_estimate = cur.fetchone()["estimate"] or 200_000
        fraction = min(sample / total_estimate * 1.2, 1.0)  # 20% buffer for variance
        sample_filter = f"AND RANDOM() < {fraction:.6f}"
        print(f"Fetching ~{sample:,} jobs (est. total={total_estimate:,}, fraction={fraction:.3f})…")
    elif active_only:
        # Active jobs are a small subset — fetch all, no sampling needed
        sample_filter = ""
        print("Fetching all active jobs + embeddings (no sampling for active-only mode)…")
    else:
        sample_filter = ""
        print("Fetching all jobs + embeddings…")

    cur.execute(f"""
        SELECT
            j.job_uuid,
            j.title,
            j.company_name,
            j.salary_min,
            j.salary_max,
            j.skills_json,
            j.llm_fields_json,
            COALESCE(
                NULLIF(TRIM(BOTH '"' FROM (j.categories_json::jsonb->0)::text), ''),
                'Unknown'
            ) AS category,
            COALESCE(
                NULLIF(TRIM(BOTH '"' FROM (j.position_levels_json::jsonb->0)::text), ''),
                'Unknown'
            ) AS position_level,
            e.embedding::text AS embedding_text
        FROM jobs j
        JOIN job_embeddings e ON e.job_uuid = j.job_uuid
        WHERE e.embedding IS NOT NULL
          {active_filter}
          {sample_filter}
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    print(f"Fetched {len(rows):,} rows")

    embeddings, records = [], []
    for r in rows:
        try:
            emb = json.loads(r["embedding_text"])
            if len(emb) != EMBEDDING_DIMS:
                continue
        except (json.JSONDecodeError, TypeError):
            continue

        try:
            skills = json.loads(r["skills_json"] or "[]")
        except (json.JSONDecodeError, TypeError):
            skills = []

        try:
            llm = json.loads(r["llm_fields_json"] or "{}")
            seniority = llm.get("inferred_seniority") or "Unknown"
            if seniority not in SENIORITY_LEVELS:
                seniority = "Unknown"
        except (json.JSONDecodeError, TypeError):
            seniority = "Unknown"

        embeddings.append(emb)
        sal_min = r["salary_min"] if r["salary_min"] and r["salary_min"] >= 100 else None
        sal_max = r["salary_max"] if r["salary_max"] and r["salary_max"] >= 100 else None
        records.append({
            "job_uuid":       r["job_uuid"],
            "title":          r["title"] or "",
            "company_name":   r["company_name"] or "",
            "salary_min":     sal_min,
            "salary_max":     sal_max,
            "skills":         skills,
            "category":       r["category"],
            "position_level": r["position_level"],
            "seniority":      seniority,
        })

    X = np.array(embeddings, dtype=np.float32)
    df = pd.DataFrame(records)
    df.to_parquet(OUTPUT_DIR / "jobs_df.parquet", index=False)
    print(f"Matrix shape: {X.shape}")
    return X, df


# ──────────────────────────────────────────────────────────────────────────────
# 2. UMAP (cached)
# ──────────────────────────────────────────────────────────────────────────────

def compute_umap(X: np.ndarray) -> np.ndarray:
    cache = OUTPUT_DIR / "umap_coords.npy"
    if cache.exists():
        print("Loading cached UMAP coords...")
        return np.load(cache)

    print(f"Fitting UMAP on {len(X):,} x {X.shape[1]} matrix (cosine, ~5–10 min)…")
    rng = np.random.default_rng(42)
    sample_idx = rng.choice(len(X), size=min(15_000, len(X)), replace=False)
    reducer = umap.UMAP(
        n_components=2, n_neighbors=30, min_dist=0.05,
        metric="cosine", random_state=42, low_memory=False,
    )
    reducer.fit(X[sample_idx])
    print("Transforming full dataset...")
    xy = reducer.transform(X)
    np.save(cache, xy)
    print(f"UMAP done. Cached -> {cache}")
    return xy


# ──────────────────────────────────────────────────────────────────────────────
# 3. K-MEANS SWEEP
# ──────────────────────────────────────────────────────────────────────────────

def kmeans_sweep(X: np.ndarray) -> dict[int, float]:
    print("\nK-Means silhouette sweep k=8…40…")
    rng = np.random.default_rng(42)
    sil_idx = rng.choice(len(X), size=min(10_000, len(X)), replace=False)
    X_sil = X[sil_idx]

    scores: dict[int, float] = {}
    for k in range(8, 41):
        km = MiniBatchKMeans(n_clusters=k, random_state=42, n_init=5, batch_size=4096)
        km.fit(X)
        labels_sil = km.labels_[sil_idx]
        score = silhouette_score(X_sil, labels_sil, metric="cosine")
        scores[k] = score
        print(f"  k={k:2d}  silhouette={score:.4f}")

    best_k = max(scores, key=scores.get)
    print(f"\nBest k={best_k}  silhouette={scores[best_k]:.4f}  (v1 baseline: {V1_SILHOUETTE})")
    return scores


def fit_best_kmeans(X: np.ndarray, best_k: int) -> np.ndarray:
    print(f"\nFitting final K-Means k={best_k}...")
    km_cache = OUTPUT_DIR / "km_labels.npy"
    if km_cache.exists() and len(np.load(km_cache)) != len(X):
        km_cache.unlink()
    km = MiniBatchKMeans(n_clusters=best_k, random_state=42, n_init=10, batch_size=4096)
    km.fit(X)
    labels = km.labels_
    np.save(km_cache, labels)
    np.save(OUTPUT_DIR / "km_centroids.npy", km.cluster_centers_)
    return labels


# ──────────────────────────────────────────────────────────────────────────────
# 4. HDBSCAN
# ──────────────────────────────────────────────────────────────────────────────

def run_hdbscan(xy: np.ndarray) -> np.ndarray:
    print("\nRunning HDBSCAN on UMAP coords...")
    clusterer = hdbscan.HDBSCAN(min_cluster_size=150, min_samples=10, metric="euclidean")
    labels = clusterer.fit_predict(xy)
    n_clusters = int((labels >= 0).any() and labels.max() + 1)
    pct_noise = (labels == -1).mean() * 100
    print(f"HDBSCAN: {n_clusters} clusters, {pct_noise:.1f}% noise")
    return labels


# ──────────────────────────────────────────────────────────────────────────────
# 5. KNN TIER CV
# ──────────────────────────────────────────────────────────────────────────────

def knn_tier_cv(X: np.ndarray, df: pd.DataFrame) -> tuple[float, float]:
    df = df.copy()
    labeled = df[df["seniority"] != "Unknown"]
    X_lab = X[labeled.index]
    y_lab = labeled["seniority"].to_numpy()

    print(f"\nKNN tier CV on {len(X_lab):,} labeled jobs...")
    print(pd.Series(y_lab).value_counts().to_string())

    knn = KNeighborsClassifier(n_neighbors=5, metric="cosine", algorithm="brute", n_jobs=1)
    cv = cross_val_score(knn, X_lab, y_lab, cv=5, scoring="balanced_accuracy", n_jobs=1)
    mean, std = float(cv.mean()), float(cv.std())
    print(f"\nKNN CV balanced_accuracy: {mean:.3f} ± {std:.3f}  (v1 baseline: {V1_KNN_CV})")
    return mean, std


# ──────────────────────────────────────────────────────────────────────────────
# 6. VISUALISATIONS
# ──────────────────────────────────────────────────────────────────────────────

SCATTER_SAMPLE = 30_000  # cap for visual UMAP plots — Scattergl handles this fine in browser


def _save(fig: go.Figure, name: str) -> None:
    path = OUTPUT_DIR / name
    fig.write_html(str(path), include_plotlyjs="cdn")
    print(f"Saved -> {path}")


def _umap_sample(xy: np.ndarray, df: pd.DataFrame, extra: dict | None = None, rng_seed: int = 42):
    """Stratified-random sample of UMAP coords + df rows capped at SCATTER_SAMPLE."""
    n = len(xy)
    if n <= SCATTER_SAMPLE:
        idx = np.arange(n)
    else:
        rng = np.random.default_rng(rng_seed)
        idx = rng.choice(n, size=SCATTER_SAMPLE, replace=False)
    result = {"xy": xy[idx], "df": df.iloc[idx].reset_index(drop=True)}
    if extra:
        result.update({k: v[idx] for k, v in extra.items()})
    return result


def _scatter_layout(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title=title, xaxis_title="UMAP-1", yaxis_title="UMAP-2",
        plot_bgcolor="rgba(245,245,245,1)", paper_bgcolor="white",
        hoverlabel=dict(bgcolor="white", font_size=12),
        legend=dict(itemsizing="constant"),
    )
    return fig


def plot_by_tier(xy: np.ndarray, df: pd.DataFrame) -> None:
    s = _umap_sample(xy, df)
    sdf, sxy = s["df"], s["xy"]
    fig = go.Figure()
    for tier, color in SENIORITY_COLORS.items():
        mask = np.array(sdf["seniority"]) == tier
        if not mask.any():
            continue
        fig.add_trace(go.Scattergl(
            x=sxy[mask, 0], y=sxy[mask, 1], mode="markers", name=tier,
            marker=dict(size=3, color=color, opacity=0.5),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>" + tier + "<extra></extra>",
            customdata=np.stack([np.array(sdf["title"])[mask], np.array(sdf["company_name"])[mask]], axis=1),
        ))
    n_shown = len(sxy)
    _scatter_layout(fig, f"UMAP — inferred seniority  ({len(df):,} jobs, {n_shown:,} shown)")
    _save(fig, "umap_by_tier.html")


def plot_by_category(xy: np.ndarray, df: pd.DataFrame) -> None:
    top12 = df["category"].value_counts().head(12).index.tolist()
    cats = df["category"].where(df["category"].isin(top12), other="Other").values
    s = _umap_sample(xy, df, extra={"cats": cats})
    sdf, sxy, scats = s["df"], s["xy"], s["cats"]
    palette = px.colors.qualitative.Dark24
    unique_cats = ["Other"] + top12
    color_map = {c: palette[i % len(palette)] for i, c in enumerate(unique_cats)}
    fig = go.Figure()
    for cat in unique_cats:
        mask = scats == cat
        if not mask.any():
            continue
        fig.add_trace(go.Scattergl(
            x=sxy[mask, 0], y=sxy[mask, 1], mode="markers", name=cat,
            marker=dict(size=3, color=color_map[cat], opacity=0.5),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>" + cat + "<extra></extra>",
            customdata=np.stack([np.array(sdf["title"])[mask], np.array(sdf["company_name"])[mask]], axis=1),
        ))
    _scatter_layout(fig, f"UMAP — top category  ({len(df):,} jobs, {len(sxy):,} shown)")
    _save(fig, "umap_by_category.html")


def plot_by_salary(xy: np.ndarray, df: pd.DataFrame) -> None:
    has_sal = (~df["salary_min"].isna()).values
    sal_vals = df["salary_min"].fillna(0).values
    s = _umap_sample(xy, df, extra={"has_sal": has_sal, "sal": sal_vals})
    sdf, sxy = s["df"], s["xy"]
    shas, ssal = s["has_sal"], s["sal"]

    fig = go.Figure()
    # Grey for no-salary
    if (~shas).any():
        fig.add_trace(go.Scattergl(
            x=sxy[~shas, 0], y=sxy[~shas, 1], mode="markers", name="No salary",
            marker=dict(size=3, color="#CCCCCC", opacity=0.4),
            hovertemplate="<b>%{customdata[0]}</b><br>No salary<extra></extra>",
            customdata=np.array(sdf["title"])[~shas].reshape(-1, 1),
        ))
    # Coloured by salary
    if shas.any():
        fig.add_trace(go.Scattergl(
            x=sxy[shas, 0], y=sxy[shas, 1], mode="markers", name="Has salary",
            marker=dict(
                size=3, opacity=0.6,
                color=ssal[shas],
                colorscale="Plasma",
                showscale=True,
                colorbar=dict(title="SGD min"),
            ),
            hovertemplate="<b>%{customdata[0]}</b><br>SGD %{customdata[1]:,.0f}<extra></extra>",
            customdata=np.stack([np.array(sdf["title"])[shas], ssal[shas]], axis=1),
        ))
    _scatter_layout(fig, f"UMAP — salary_min  ({has_sal.sum():,} with salary, {len(sxy):,} shown)")
    _save(fig, "umap_by_salary.html")


def plot_hdbscan(xy: np.ndarray, df: pd.DataFrame, hdb_labels: np.ndarray) -> None:
    labels_str = np.where(hdb_labels == -1, "Noise", "C" + hdb_labels.astype(str))
    s = _umap_sample(xy, df, extra={"labels": labels_str})
    sdf, sxy, slabels = s["df"], s["xy"], s["labels"]
    n_clusters = int(hdb_labels.max() + 1) if hdb_labels.max() >= 0 else 0
    palette = ["#CCCCCC"] + px.colors.qualitative.Dark24 + px.colors.qualitative.Light24
    unique_labels = ["Noise"] + [f"C{i}" for i in range(n_clusters)]
    color_map = {lbl: palette[i % len(palette)] for i, lbl in enumerate(unique_labels)}
    fig = go.Figure()
    for lbl in unique_labels:
        mask = slabels == lbl
        if not mask.any():
            continue
        fig.add_trace(go.Scattergl(
            x=sxy[mask, 0], y=sxy[mask, 1], mode="markers", name=lbl,
            marker=dict(size=3, color=color_map[lbl], opacity=0.5),
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<br>" + lbl + "<extra></extra>",
            customdata=np.stack([np.array(sdf["title"])[mask], np.array(sdf["category"])[mask]], axis=1),
        ))
    _scatter_layout(fig, f"UMAP — HDBSCAN ({n_clusters} clusters, {(hdb_labels==-1).mean()*100:.1f}% noise, {len(sxy):,} shown)")
    fig.update_layout(legend=dict(font_size=10))
    _save(fig, "umap_hdbscan.html")


def plot_umap_by_cluster(xy: np.ndarray, df: pd.DataFrame, km_labels: np.ndarray, profiles: pd.DataFrame) -> None:
    label_map = dict(zip(profiles["cluster"], profiles["top_titles"].str.split(" | ").str[0]))
    cluster_name = [label_map.get(c, f"Cluster {c}") for c in km_labels]

    # Compute centroids in UMAP space
    centroids = []
    for c in sorted(profiles["cluster"].unique()):
        mask = km_labels == c
        centroids.append({
            "cluster": c,
            "cx": xy[mask, 0].mean(),
            "cy": xy[mask, 1].mean(),
            "label": label_map.get(c, f"Cluster {c}"),
            "n_jobs": mask.sum(),
        })
    cent_df = pd.DataFrame(centroids)

    palette = px.colors.qualitative.Dark24 + px.colors.qualitative.Light24
    unique_clusters = sorted(profiles["cluster"].unique())
    color_map = {c: palette[i % len(palette)] for i, c in enumerate(unique_clusters)}
    point_colors = [color_map[c] for c in km_labels]

    plot_df = pd.DataFrame({
        "x": xy[:, 0], "y": xy[:, 1],
        "cluster": km_labels,
        "cluster_name": cluster_name,
        "title": df["title"].values,
        "category": df["category"].values,
    })

    fig = go.Figure()

    # One scatter trace per cluster so legend works
    for c in unique_clusters:
        mask = km_labels == c
        name = label_map.get(c, f"Cluster {c}")
        fig.add_trace(go.Scattergl(
            x=xy[mask, 0], y=xy[mask, 1],
            mode="markers",
            name=name,
            marker=dict(size=3, color=color_map[c], opacity=0.5),
            hovertemplate=(
                "<b>%{customdata[0]}</b><br>"
                "Category: %{customdata[1]}<br>"
                "Cluster: " + name + "<extra></extra>"
            ),
            customdata=np.stack([
                df["title"].values[mask],
                df["category"].values[mask],
            ], axis=1),
            legendgroup=str(c),
        ))

    # Centroid annotations
    fig.add_trace(go.Scatter(
        x=cent_df["cx"], y=cent_df["cy"],
        mode="text",
        text=cent_df["label"],
        textfont=dict(size=10, color="black"),
        hovertemplate="<b>%{text}</b><br>n=%{customdata} jobs<extra></extra>",
        customdata=cent_df["n_jobs"],
        showlegend=False,
    ))

    fig.update_layout(
        title=dict(text=f"UMAP — KMeans clusters (k={len(unique_clusters)}, labeled by top job title)", font_size=16),
        xaxis_title="UMAP-1", yaxis_title="UMAP-2",
        height=750,
        legend=dict(title="Cluster", font_size=9, itemsizing="constant",
                    tracegroupgap=2, x=1.01),
        plot_bgcolor="rgba(245,245,245,1)",
        paper_bgcolor="white",
        hoverlabel=dict(bgcolor="white", font_size=12),
    )
    _save(fig, "umap_by_cluster.html")


def plot_kmeans_sweep(scores: dict[int, float]) -> None:
    best_k = max(scores, key=scores.get)
    sweep_df = pd.DataFrame({"k": list(scores.keys()), "silhouette": list(scores.values())})
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=sweep_df["k"], y=sweep_df["silhouette"],
                             mode="lines+markers", name="Silhouette",
                             marker=dict(size=6), line=dict(width=2)))
    fig.add_hline(y=V1_SILHOUETTE, line_dash="dash", line_color="grey",
                  annotation_text=f"v1 baseline ({V1_SILHOUETTE})", annotation_position="top left")
    fig.add_vline(x=best_k, line_dash="dash", line_color="red",
                  annotation_text=f"Best k={best_k}", annotation_position="top right")
    fig.update_layout(title=f"K-Means silhouette sweep — {MODEL_NAME}",
                      xaxis_title="k", yaxis_title="Silhouette (cosine)")
    _save(fig, "kmeans_sweep.html")


# ──────────────────────────────────────────────────────────────────────────────
# 7. CLUSTER PROFILES
# ──────────────────────────────────────────────────────────────────────────────

def build_cluster_profiles(df: pd.DataFrame, km_labels: np.ndarray) -> pd.DataFrame:
    df = df.copy()
    df["cluster"] = km_labels
    rows = []
    for c in sorted(df["cluster"].unique()):
        sub = df[df["cluster"] == c]
        top_titles = [t for t, _ in Counter(sub["title"]).most_common(5)]
        all_skills: list[str] = []
        for skills in sub["skills"]:
            all_skills.extend(skills)
        top_skills = [s for s, _ in Counter(all_skills).most_common(5)]
        tier_dist = sub["seniority"].value_counts(normalize=True).round(3).to_dict()

        sal = sub["salary_max"].dropna()
        n_with_salary = len(sal)
        pct_with_salary = n_with_salary / len(sub) if len(sub) else 0
        if n_with_salary >= 2:
            sal_median = sal.median()
            sal_p25    = sal.quantile(0.25)
            sal_p75    = sal.quantile(0.75)
            sal_iqr    = sal_p75 - sal_p25
            sal_cv     = sal.std() / sal.mean() if sal.mean() > 0 else None
        else:
            sal_median = sal_p25 = sal_p75 = sal_iqr = sal_cv = None

        viable = (
            pct_with_salary >= SALARY_MIN_COVERAGE
            and n_with_salary >= SALARY_MIN_JOBS
            and (sal_cv is None or sal_cv <= SALARY_MAX_CV)
        )

        rows.append({
            "cluster":           c,
            "n_jobs":            len(sub),
            "top_category":      sub["category"].value_counts().idxmax() if len(sub) else "",
            "top_titles":        " | ".join(top_titles),
            "top_skills":        " | ".join(top_skills),
            "median_salary_min": sub["salary_min"].median() if sub["salary_min"].notna().any() else None,
            "pct_with_salary":   round(pct_with_salary, 3),
            "n_with_salary":     n_with_salary,
            "salary_max_p25":    round(sal_p25, 0) if sal_p25 is not None else None,
            "salary_max_median": round(sal_median, 0) if sal_median is not None else None,
            "salary_max_p75":    round(sal_p75, 0) if sal_p75 is not None else None,
            "salary_max_iqr":    round(sal_iqr, 0) if sal_iqr is not None else None,
            "salary_max_cv":     round(sal_cv, 3) if sal_cv is not None else None,
            "salary_viable":     viable,
            **{f"tier_{k}": v for k, v in tier_dist.items()},
        })
    profiles = pd.DataFrame(rows).sort_values("n_jobs", ascending=False)
    path = OUTPUT_DIR / "cluster_profiles.csv"
    profiles.to_csv(path, index=False)

    viability = profiles[[
        "cluster", "n_jobs", "top_titles", "top_category",
        "pct_with_salary", "n_with_salary",
        "salary_max_p25", "salary_max_median", "salary_max_p75",
        "salary_max_iqr", "salary_max_cv", "salary_viable",
    ]].copy()
    viability.to_csv(OUTPUT_DIR / "salary_viability.csv", index=False)

    n_viable = viability["salary_viable"].sum()
    print(f"Saved -> {path}")
    print(f"Salary viability: {n_viable}/{len(viability)} clusters viable for percentile benchmarking")
    return profiles


def plot_cluster_profiles(profiles: pd.DataFrame) -> None:
    TIER_ORDER = SENIORITY_LEVELS + ["Unknown"]
    TIER_COLORS_LIST = [SENIORITY_COLORS[t] for t in TIER_ORDER]

    # ensure all tier columns exist
    for t in TIER_ORDER:
        col = f"tier_{t}"
        if col not in profiles.columns:
            profiles[col] = 0.0

    # label each cluster: "Category (n=X)"
    profiles = profiles.copy()
    profiles["label"] = profiles.apply(
        lambda r: f"{r['top_category']} (n={r['n_jobs']:,})", axis=1
    )
    profiles["top_title"] = profiles["top_titles"].str.split(" | ").str[0]
    profiles = profiles.sort_values("median_salary_min", ascending=True)

    fig = make_subplots(
        rows=1, cols=2,
        column_widths=[0.55, 0.45],
        subplot_titles=("Tier mix per cluster (% of jobs)", "Median salary vs cluster size"),
        horizontal_spacing=0.12,
    )

    # — Left: stacked horizontal bar, one bar per cluster —
    for tier, color in zip(TIER_ORDER, TIER_COLORS_LIST):
        col = f"tier_{tier}"
        vals = profiles[col].fillna(0) * 100
        hover = [
            f"<b>{row['top_category']}</b><br>"
            f"n={row['n_jobs']:,} jobs<br>"
            f"Median salary: SGD {row['median_salary_min']:,.0f}<br>"
            f"<br><b>Top titles:</b><br>{'<br>'.join(row['top_titles'].split(' | '))}<br>"
            f"<br><b>Top skills:</b><br>{'<br>'.join(row['top_skills'].split(' | '))}"
            for _, row in profiles.iterrows()
        ]
        fig.add_trace(
            go.Bar(
                name=tier, x=vals, y=profiles["label"],
                orientation="h",
                marker_color=color,
                hovertemplate="%{customdata}<extra>" + tier + "</extra>",
                customdata=hover,
                legendgroup=tier,
            ),
            row=1, col=1,
        )

    # — Right: bubble chart salary vs n_jobs —
    categories = profiles["top_category"].tolist()
    palette = px.colors.qualitative.Dark24
    cat_color = {c: palette[i % len(palette)] for i, c in enumerate(sorted(set(categories)))}

    bubble_hover = [
        f"<b>{row['top_category']}</b><br>"
        f"Median salary: SGD {row['median_salary_min']:,.0f}<br>"
        f"n={row['n_jobs']:,} jobs<br>"
        f"<br><b>Top titles:</b><br>{'<br>'.join(row['top_titles'].split(' | '))}<br>"
        f"<br><b>Top skills:</b><br>{'<br>'.join(row['top_skills'].split(' | '))}"
        for _, row in profiles.iterrows()
    ]
    fig.add_trace(
        go.Scatter(
            x=profiles["median_salary_min"],
            y=profiles["n_jobs"],
            mode="markers+text",
            text=profiles["top_title"],
            textposition="top center",
            textfont=dict(size=9),
            marker=dict(
                size=profiles["n_jobs"] / profiles["n_jobs"].max() * 60 + 12,
                color=[cat_color[c] for c in categories],
                line=dict(width=1, color="white"),
                opacity=0.85,
            ),
            hovertemplate="%{customdata}<extra></extra>",
            customdata=bubble_hover,
            showlegend=False,
        ),
        row=1, col=2,
    )

    fig.update_layout(
        title=dict(text="Cluster profiles — bge-base-sgmarket-v2 embeddings", font_size=16),
        barmode="stack",
        height=600,
        legend=dict(title="Tier", orientation="v", x=1.01, y=0.5),
        xaxis=dict(title="% of cluster", ticksuffix="%", range=[0, 100]),
        xaxis2=dict(title="Median salary min (SGD)", tickprefix="$"),
        yaxis2=dict(title="Number of jobs"),
        hoverlabel=dict(bgcolor="white", font_size=12),
        plot_bgcolor="rgba(245,245,245,1)",
        paper_bgcolor="white",
    )

    _save(fig, "cluster_profiles.html")


# ──────────────────────────────────────────────────────────────────────────────
# 7b. SALARY DISTRIBUTION PER CLUSTER
# ──────────────────────────────────────────────────────────────────────────────

def plot_salary_distributions(df: pd.DataFrame, km_labels: np.ndarray, profiles: pd.DataFrame) -> None:
    """Box plot of salary_max per cluster, ordered by median. Highlights viable clusters."""
    df = df.copy()
    df["cluster"] = km_labels

    label_map = dict(zip(profiles["cluster"], profiles["top_titles"].str.split(" | ").str[0]))
    viable_set = set(profiles.loc[profiles["salary_viable"], "cluster"])

    rows = []
    for c in sorted(df["cluster"].unique()):
        sub = df[(df["cluster"] == c) & df["salary_max"].notna()]
        if len(sub) < 5:
            continue
        name = label_map.get(c, f"C{c}")
        viable = c in viable_set
        for v in sub["salary_max"]:
            rows.append({"cluster": c, "label": name, "salary_max": v, "viable": viable})

    plot_df = pd.DataFrame(rows)
    if plot_df.empty:
        print("No salary data for distribution plot — skipping")
        return

    order = (
        plot_df.groupby("label")["salary_max"].median()
        .sort_values().index.tolist()
    )
    plot_df["viable_label"] = plot_df["viable"].map({True: "Viable", False: "Too sparse / noisy"})

    fig = px.box(
        plot_df, x="salary_max", y="label",
        color="viable_label",
        color_discrete_map={"Viable": "#4CAF50", "Too sparse / noisy": "#CCCCCC"},
        category_orders={"label": order},
        points=False,
        title=(
            f"Salary max distribution per cluster — viable = "
            f"≥{int(SALARY_MIN_COVERAGE*100)}% coverage, "
            f"≥{SALARY_MIN_JOBS} jobs, CV≤{SALARY_MAX_CV}"
        ),
        labels={"salary_max": "Salary max (SGD/mo)", "label": "Cluster (top title)", "viable_label": ""},
    )
    fig.update_layout(
        height=max(400, len(order) * 22),
        xaxis_tickprefix="$",
        plot_bgcolor="rgba(245,245,245,1)",
        paper_bgcolor="white",
        hoverlabel=dict(bgcolor="white"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
    )
    _save(fig, "salary_distributions.html")


# ──────────────────────────────────────────────────────────────────────────────
# 7c. STRATIFIED (CLUSTER × SENIORITY) PROFILES
# ──────────────────────────────────────────────────────────────────────────────

def build_stratified_profiles(df: pd.DataFrame, km_labels: np.ndarray, profiles: pd.DataFrame) -> pd.DataFrame:
    """Compute salary stats per (cluster, seniority) pair."""
    df = df.copy()
    df["cluster"] = km_labels
    label_map = dict(zip(profiles["cluster"], profiles["top_titles"].str.split(" | ").str[0]))

    rows = []
    for c in sorted(df["cluster"].unique()):
        sub_c = df[df["cluster"] == c]
        cluster_label = label_map.get(c, f"C{c}")
        for seniority in SENIORITY_LEVELS + ["Unknown"]:
            sub = sub_c[sub_c["seniority"] == seniority]
            if len(sub) == 0:
                continue
            sal = sub["salary_max"].dropna()
            n_with_salary = len(sal)
            pct_with_salary = n_with_salary / len(sub) if len(sub) else 0
            if n_with_salary >= 2:
                sal_median = sal.median()
                sal_p25    = sal.quantile(0.25)
                sal_p75    = sal.quantile(0.75)
                sal_iqr    = sal_p75 - sal_p25
                sal_cv     = sal.std() / sal.mean() if sal.mean() > 0 else None
            else:
                sal_median = sal_p25 = sal_p75 = sal_iqr = sal_cv = None

            viable = (
                pct_with_salary >= STRAT_MIN_COVERAGE
                and n_with_salary >= STRAT_MIN_JOBS
                and (sal_cv is None or sal_cv <= STRAT_MAX_CV)
            )
            rows.append({
                "cluster":           c,
                "cluster_label":     cluster_label,
                "seniority":         seniority,
                "n_jobs":            len(sub),
                "pct_with_salary":   round(pct_with_salary, 3),
                "n_with_salary":     n_with_salary,
                "salary_max_p25":    round(sal_p25, 0) if sal_p25 is not None else None,
                "salary_max_median": round(sal_median, 0) if sal_median is not None else None,
                "salary_max_p75":    round(sal_p75, 0) if sal_p75 is not None else None,
                "salary_max_iqr":    round(sal_iqr, 0) if sal_iqr is not None else None,
                "salary_max_cv":     round(sal_cv, 3) if sal_cv is not None else None,
                "salary_viable":     viable,
            })

    strat = pd.DataFrame(rows)
    path = OUTPUT_DIR / "salary_stratified_viability.csv"
    strat.to_csv(path, index=False)
    n_viable = int(strat["salary_viable"].sum())
    n_total  = len(strat)
    print(f"Saved -> {path}")
    print(f"Stratified viability: {n_viable}/{n_total} (cluster × seniority) pairs viable")
    return strat


def plot_salary_distributions_stratified(df: pd.DataFrame, km_labels: np.ndarray, strat: pd.DataFrame) -> None:
    """Box plot per viable (cluster, seniority) pair, colored by seniority."""
    df = df.copy()
    df["cluster"] = km_labels

    viable_pairs = set(zip(strat.loc[strat["salary_viable"], "cluster"],
                           strat.loc[strat["salary_viable"], "seniority"]))
    label_map = dict(zip(strat["cluster"], strat["cluster_label"]))

    rows = []
    for (c, seniority) in viable_pairs:
        sub = df[(df["cluster"] == c) & (df["seniority"] == seniority) & df["salary_max"].notna()]
        if len(sub) < 5:
            continue
        cluster_label = label_map.get(c, f"C{c}")
        label = f"{cluster_label} [{seniority}]"
        for v in sub["salary_max"]:
            rows.append({"label": label, "seniority": seniority, "salary_max": v})

    plot_df = pd.DataFrame(rows)
    if plot_df.empty:
        print("No viable stratified pairs — skipping stratified distribution plot")
        return

    order = (
        plot_df.groupby("label")["salary_max"].median()
        .sort_values().index.tolist()
    )

    fig = px.box(
        plot_df, x="salary_max", y="label",
        color="seniority",
        color_discrete_map=SENIORITY_COLORS,
        category_orders={"label": order},
        points=False,
        title=(
            f"Salary max — viable stratified pairs  "
            f"(≥{STRAT_MIN_JOBS} jobs, CV≤{STRAT_MAX_CV})"
        ),
        labels={"salary_max": "Salary max (SGD/mo)", "label": "Cluster [Seniority]", "seniority": "Seniority"},
    )
    fig.update_layout(
        height=max(400, len(order) * 22),
        xaxis_tickprefix="$",
        plot_bgcolor="rgba(245,245,245,1)",
        paper_bgcolor="white",
        hoverlabel=dict(bgcolor="white"),
        legend=dict(orientation="h", yanchor="bottom", y=1.01),
    )
    _save(fig, "salary_distributions_stratified.html")


# ──────────────────────────────────────────────────────────────────────────────
# 8. SUMMARY JSON
# ──────────────────────────────────────────────────────────────────────────────

def save_summary(
    n_jobs: int,
    scores: dict[int, float],
    knn_mean: float,
    knn_std: float,
    hdb_labels: np.ndarray,
    profiles: pd.DataFrame,
    strat: pd.DataFrame | None = None,
) -> None:
    best_k = max(scores, key=scores.get)
    n_hdb_clusters = int(hdb_labels.max() + 1) if hdb_labels.max() >= 0 else 0
    n_viable = int(profiles["salary_viable"].sum()) if "salary_viable" in profiles.columns else None
    summary = {
        "n_jobs":          n_jobs,
        "embedding_model": MODEL_NAME,
        "embedding_dim":   EMBEDDING_DIMS,
        "kmeans": {
            "best_k":          best_k,
            "best_silhouette": round(scores[best_k], 4),
            "v1_baseline":     V1_SILHOUETTE,
            "delta":           round(scores[best_k] - V1_SILHOUETTE, 4),
        },
        "knn_tier_cv": {
            "mean_balanced_accuracy": round(knn_mean, 4),
            "std":                    round(knn_std, 4),
            "v1_baseline":            V1_KNN_CV,
            "delta":                  round(knn_mean - V1_KNN_CV, 4),
            "threshold":              0.65,
            "passes_threshold":       knn_mean >= 0.65,
        },
        "hdbscan": {
            "n_clusters": n_hdb_clusters,
            "pct_noise":  round((hdb_labels == -1).mean() * 100, 2),
        },
        "salary_viability": {
            "n_clusters_total":  len(profiles),
            "n_clusters_viable": n_viable,
            "thresholds": {
                "min_coverage": SALARY_MIN_COVERAGE,
                "min_jobs":     SALARY_MIN_JOBS,
                "max_cv":       SALARY_MAX_CV,
            },
        },
        "salary_viability_stratified": {
            "n_pairs_total":   len(strat) if strat is not None else None,
            "n_pairs_viable":  int(strat["salary_viable"].sum()) if strat is not None else None,
            "thresholds": {
                "min_coverage": STRAT_MIN_COVERAGE,
                "min_jobs":     STRAT_MIN_JOBS,
                "max_cv":       STRAT_MAX_CV,
            },
        },
    }
    path = OUTPUT_DIR / "summary.json"
    path.write_text(json.dumps(summary, indent=2))
    print(f"\nSaved -> {path}")
    print(json.dumps(summary, indent=2))


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--plot-only",   action="store_true")
    parser.add_argument("--active-only", action="store_true")
    parser.add_argument("--sample",      type=int, default=50_000,
                        help="Random sample size (0 = fetch all, default 50000)")
    args = parser.parse_args()
    plot_only   = args.plot_only
    active_only = args.active_only
    sample      = args.sample

    if plot_only:
        print("Plot-only mode: loading cached data...")
        xy = np.load(OUTPUT_DIR / "umap_coords.npy")
        km_labels = np.load(OUTPUT_DIR / "km_labels.npy")
        df = pd.read_parquet(OUTPUT_DIR / "jobs_df.parquet")
        profiles = pd.read_csv(OUTPUT_DIR / "cluster_profiles.csv")
        print(f"Loaded {len(df):,} jobs, {len(profiles)} clusters")
        print("\nGenerating plots...")
        plot_by_tier(xy, df)
        plot_by_category(xy, df)
        plot_by_salary(xy, df)
        strat = build_stratified_profiles(df, km_labels, profiles)
        plot_cluster_profiles(profiles)
        plot_umap_by_cluster(xy, df, km_labels, profiles)
        plot_salary_distributions(df, km_labels, profiles)
        plot_salary_distributions_stratified(df, km_labels, strat)
        print(f"\nAll outputs -> {OUTPUT_DIR.resolve()}")
        return

    # 1. Fetch
    X, df = fetch_jobs(active_only=active_only, sample=sample)

    # 2. UMAP — bust cache if row count changed
    umap_cache = OUTPUT_DIR / "umap_coords.npy"
    if umap_cache.exists() and len(np.load(umap_cache)) != len(X):
        print(f"Row count changed ({len(np.load(umap_cache)):,} → {len(X):,}) — deleting stale UMAP cache")
        umap_cache.unlink()

    xy = compute_umap(X)
    df["umap_x"] = xy[:, 0]
    df["umap_y"] = xy[:, 1]

    # 3. K-Means sweep
    scores = kmeans_sweep(X)
    best_k = max(scores, key=scores.get)

    # 4. Fit final K-Means
    km_labels = fit_best_kmeans(X, best_k)
    df["cluster"] = km_labels

    # 5. HDBSCAN
    hdb_labels = run_hdbscan(xy)
    df["hdbscan"] = hdb_labels

    # 6. KNN tier CV
    knn_mean, knn_std = knn_tier_cv(X, df)

    # 7. Visualisations
    print("\nGenerating plots...")
    plot_by_tier(xy, df)
    plot_by_category(xy, df)
    plot_by_salary(xy, df)
    plot_hdbscan(xy, df, hdb_labels)
    plot_kmeans_sweep(scores)

    # 8. Cluster profiles
    profiles = build_cluster_profiles(df, km_labels)
    strat    = build_stratified_profiles(df, km_labels, profiles)
    plot_cluster_profiles(profiles)
    plot_umap_by_cluster(xy, df, km_labels, profiles)
    plot_salary_distributions(df, km_labels, profiles)
    plot_salary_distributions_stratified(df, km_labels, strat)

    # 9. Summary
    save_summary(len(df), scores, knn_mean, knn_std, hdb_labels, profiles, strat)

    print(f"\nAll outputs -> {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
