"""Cluster analysis for the 46,940 re-embedded jobs (BGE-base-en-v1.5, 768-dim).

Usage:
    uv run python scripts/cluster_analysis.py

Outputs go to scripts/cluster_analysis_output/:
    umap_by_tier.html, umap_by_category.html, umap_by_salary.html,
    umap_hdbscan.html, umap_by_cluster.html, kmeans_sweep.html,
    cluster_profiles.html, cluster_profiles.csv, summary.json
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
TIER_COLORS = {
    "T1_Entry":      "#2196F3",
    "T2_Junior":     "#4CAF50",
    "T3_Senior":     "#FF9800",
    "T4_Management": "#F44336",
    "Unknown":       "#CCCCCC",
}
V1_SILHOUETTE   = 0.054
V1_KNN_CV       = 0.620
V1_MEAN_PURITY  = 0.164


# ──────────────────────────────────────────────────────────────────────────────
# 1. DATA FETCH
# ──────────────────────────────────────────────────────────────────────────────

def fetch_jobs() -> tuple[np.ndarray, pd.DataFrame]:
    """Return (X, df) for jobs embedded in the most recent 24-hour window."""
    print("Connecting to Supabase...")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Fetching jobs + embeddings (may take a few minutes)…")
    cur.execute("""
        SELECT
            j.job_uuid,
            j.title,
            j.company_name,
            j.salary_min,
            j.salary_max,
            j.skills_json,
            j.predicted_tier,
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
        WHERE j.is_active = TRUE
          AND e.embedding IS NOT NULL
          AND e.embedded_at >= (
                SELECT MAX(embedded_at) FROM job_embeddings
              ) - INTERVAL '24 hours'
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

        embeddings.append(emb)
        records.append({
            "job_uuid":       r["job_uuid"],
            "title":          r["title"] or "",
            "company_name":   r["company_name"] or "",
            "salary_min":     r["salary_min"],
            "salary_max":     r["salary_max"],
            "skills":         skills,
            "category":       r["category"],
            "position_level": r["position_level"],
            "predicted_tier": r["predicted_tier"] or "Unknown",
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
    km = MiniBatchKMeans(n_clusters=best_k, random_state=42, n_init=10, batch_size=4096)
    km.fit(X)
    labels = km.labels_
    np.save(OUTPUT_DIR / "km_labels.npy", labels)
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
    df["tier"] = df["position_level"].map(TIER_MAP)
    labeled = df[df["tier"].notna()]
    X_lab = X[labeled.index]
    y_lab = labeled["tier"].to_numpy()

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

def _save(fig: go.Figure, name: str) -> None:
    path = OUTPUT_DIR / name
    fig.write_html(str(path), include_plotlyjs="cdn")
    print(f"Saved -> {path}")


def plot_by_tier(xy: np.ndarray, df: pd.DataFrame) -> None:
    plot_df = pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1],
                            "tier": df["predicted_tier"].values,
                            "title": df["title"].values,
                            "company": df["company_name"].values})
    fig = px.scatter(
        plot_df, x="x", y="y", color="tier",
        color_discrete_map=TIER_COLORS,
        hover_data={"title": True, "company": True, "tier": True, "x": False, "y": False},
        opacity=0.5,
        title=f"UMAP — predicted tier  ({len(df):,} jobs)",
        labels={"x": "UMAP-1", "y": "UMAP-2", "tier": "Tier"},
    )
    fig.update_traces(marker_size=3)
    fig.update_layout(legend=dict(itemsizing="constant"))
    _save(fig, "umap_by_tier.html")


def plot_by_category(xy: np.ndarray, df: pd.DataFrame) -> None:
    top12 = df["category"].value_counts().head(12).index.tolist()
    cats = df["category"].where(df["category"].isin(top12), other="Other")
    plot_df = pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1],
                            "category": cats.values,
                            "title": df["title"].values,
                            "company": df["company_name"].values})
    fig = px.scatter(
        plot_df, x="x", y="y", color="category",
        color_discrete_sequence=px.colors.qualitative.Dark24,
        hover_data={"title": True, "company": True, "category": True, "x": False, "y": False},
        opacity=0.5,
        title=f"UMAP — top category  ({len(df):,} jobs)",
        labels={"x": "UMAP-1", "y": "UMAP-2"},
    )
    fig.update_traces(marker_size=3)
    fig.update_layout(legend=dict(itemsizing="constant"))
    _save(fig, "umap_by_category.html")


def plot_by_salary(xy: np.ndarray, df: pd.DataFrame) -> None:
    has_sal = ~(df["salary_min"].isna() | (df["salary_min"] == 0))
    plot_df = pd.DataFrame({
        "x": xy[:, 0], "y": xy[:, 1],
        "salary_min": df["salary_min"].where(has_sal).values,
        "title": df["title"].values,
        "company": df["company_name"].values,
    })
    fig = px.scatter(
        plot_df, x="x", y="y", color="salary_min",
        color_continuous_scale="Plasma",
        hover_data={"title": True, "company": True, "salary_min": True, "x": False, "y": False},
        opacity=0.6,
        title=f"UMAP — salary_min  ({has_sal.sum():,} with salary, grey = no salary)",
        labels={"x": "UMAP-1", "y": "UMAP-2", "salary_min": "Salary min (SGD)"},
    )
    fig.update_traces(marker_size=3)
    fig.update_layout(coloraxis_colorbar=dict(title="SGD min"))
    _save(fig, "umap_by_salary.html")


def plot_hdbscan(xy: np.ndarray, df: pd.DataFrame, hdb_labels: np.ndarray) -> None:
    labels_str = np.where(hdb_labels == -1, "Noise", "C" + hdb_labels.astype(str))
    plot_df = pd.DataFrame({"x": xy[:, 0], "y": xy[:, 1],
                            "cluster": labels_str,
                            "title": df["title"].values,
                            "company": df["company_name"].values,
                            "category": df["category"].values})
    n_clusters = int(hdb_labels.max() + 1) if hdb_labels.max() >= 0 else 0
    fig = px.scatter(
        plot_df, x="x", y="y", color="cluster",
        hover_data={"title": True, "company": True, "category": True, "cluster": True, "x": False, "y": False},
        opacity=0.5,
        title=f"UMAP — HDBSCAN ({n_clusters} clusters, {(hdb_labels==-1).mean()*100:.1f}% noise)",
        labels={"x": "UMAP-1", "y": "UMAP-2"},
        color_discrete_sequence=["#CCCCCC"] + px.colors.qualitative.Dark24 + px.colors.qualitative.Light24,
    )
    fig.update_traces(marker_size=3)
    fig.update_layout(legend=dict(itemsizing="constant", font_size=10))
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
        tier_dist = sub["predicted_tier"].value_counts(normalize=True).round(3).to_dict()
        rows.append({
            "cluster":       c,
            "n_jobs":        len(sub),
            "top_category":  sub["category"].value_counts().idxmax() if len(sub) else "",
            "top_titles":    " | ".join(top_titles),
            "top_skills":    " | ".join(top_skills),
            "median_salary_min": sub["salary_min"].median() if sub["salary_min"].notna().any() else None,
            "pct_with_salary": sub["salary_min"].notna().mean().round(3),
            **{f"tier_{k}": v for k, v in tier_dist.items()},
        })
    profiles = pd.DataFrame(rows).sort_values("n_jobs", ascending=False)
    path = OUTPUT_DIR / "cluster_profiles.csv"
    profiles.to_csv(path, index=False)
    print(f"Saved -> {path}")
    return profiles


def plot_cluster_profiles(profiles: pd.DataFrame) -> None:
    TIER_ORDER = ["T1_Entry", "T2_Junior", "T3_Senior", "T4_Management", "Unknown"]
    TIER_COLORS_LIST = ["#2196F3", "#4CAF50", "#FF9800", "#F44336", "#CCCCCC"]

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
        title=dict(text="Cluster profiles — BGE-base-en-v1.5 embeddings", font_size=16),
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
# 8. SUMMARY JSON
# ──────────────────────────────────────────────────────────────────────────────

def save_summary(
    n_jobs: int,
    scores: dict[int, float],
    knn_mean: float,
    knn_std: float,
    hdb_labels: np.ndarray,
) -> None:
    best_k = max(scores, key=scores.get)
    n_hdb_clusters = int(hdb_labels.max() + 1) if hdb_labels.max() >= 0 else 0
    summary = {
        "n_jobs":         n_jobs,
        "embedding_model": MODEL_NAME,
        "embedding_dim":  EMBEDDING_DIMS,
        "kmeans": {
            "best_k":           best_k,
            "best_silhouette":  round(scores[best_k], 4),
            "v1_baseline":      V1_SILHOUETTE,
            "delta":            round(scores[best_k] - V1_SILHOUETTE, 4),
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
            "n_clusters":  n_hdb_clusters,
            "pct_noise":   round((hdb_labels == -1).mean() * 100, 2),
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
    plot_only = "--plot-only" in sys.argv

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
        plot_cluster_profiles(profiles)
        plot_umap_by_cluster(xy, df, km_labels, profiles)
        print(f"\nAll outputs -> {OUTPUT_DIR.resolve()}")
        return

    # 1. Fetch
    X, df = fetch_jobs()

    # 2. UMAP
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
    plot_cluster_profiles(profiles)
    plot_umap_by_cluster(xy, df, km_labels, profiles)

    # 9. Summary
    save_summary(len(df), scores, knn_mean, knn_std, hdb_labels)

    print(f"\nAll outputs -> {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()
