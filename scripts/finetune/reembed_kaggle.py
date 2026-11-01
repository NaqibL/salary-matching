"""Kaggle GPU notebook — re-embed job texts with bge-base-sgmarket-v2.

Paste each section into a separate Kaggle cell, or run as a script.
Requires: sentence-transformers, pandas, pyarrow (all available on Kaggle by default).

Input:  job_texts.parquet  (job_uuid, job_text)
Output: job_embeddings_v2.parquet  (job_uuid, embedding)

Upload job_texts.parquet as a Kaggle dataset before running.
"""

# ── Cell 1: install ──────────────────────────────────────────────────────────
# !pip install -q sentence-transformers

# ── Cell 2: imports ──────────────────────────────────────────────────────────
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

# ── Cell 3: load data ────────────────────────────────────────────────────────
df = pd.read_parquet("/kaggle/input/<your-dataset>/job_texts.parquet")
print(f"Loaded {len(df):,} jobs")
print(df.head(2))

# ── Cell 4: embed ────────────────────────────────────────────────────────────
model = SentenceTransformer("NaqibL/bge-base-sgmarket-v2")

texts = df["job_text"].tolist()

# batch_size=128 is safe on a T4 (16GB VRAM); drop to 64 if OOM
embeddings = model.encode(
    texts,
    batch_size=128,
    normalize_embeddings=True,
    show_progress_bar=True,
)

print(f"Embeddings shape: {embeddings.shape}")  # should be (N, 768)

# ── Cell 5: save ─────────────────────────────────────────────────────────────
# /kaggle/working/ is Kaggle's output directory — download from the output panel on the right
OUTPUT_PATH = "/kaggle/working/job_embeddings_v2.parquet"

out = pd.DataFrame({
    "job_uuid": df["job_uuid"].values,
    # Store as list of floats — import script will convert to pgvector string
    "embedding": [row.tolist() for row in embeddings],
})
out.to_parquet(OUTPUT_PATH, index=False)
print(f"Saved to {OUTPUT_PATH}  ({len(out):,} rows)")

# Sanity check: one embedding
sample = out.iloc[0]
print(f"Sample uuid: {sample['job_uuid']}")
print(f"Sample embedding[:5]: {sample['embedding'][:5]}")
print(f"Norm (should be ~1.0): {np.linalg.norm(sample['embedding']):.4f}")
