from __future__ import annotations

import os
import json
import argparse
import math
from typing import Dict, List, Tuple, Any

import pandas as pd
import matplotlib.pyplot as plt

from index_store_cached import IndexStoreCached
from metadata_store import build_metadata_store_from_gcs
from evaluator import Evaluator
from tokenizer import tokenize


# -----------------------------
# Metrics
# -----------------------------
def precision_at_k(ranked: List[int], rel: set[int], k: int) -> float:
    if k <= 0:
        return 0.0
    topk = ranked[:k]
    hits = sum(1 for d in topk if d in rel)
    return hits / float(k)

def f1_at_30(ranked: List[int], rel: set[int]) -> float:
    k = 30
    if not rel:
        return 0.0
    topk = ranked[:k]
    hits = sum(1 for d in topk if d in rel)
    p = hits / float(k)
    r = hits / float(len(rel))
    if p == 0.0 or r == 0.0:
        return 0.0
    return 2.0 * p * r / (p + r)

def harmonic_mean(a: float, b: float) -> float:
    if a == 0.0 or b == 0.0:
        return 0.0
    return 2.0 * a * b / (a + b)


# -----------------------------
# Loading qrels
# -----------------------------
def load_qrels(path: str) -> Dict[str, List[int]]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    out: Dict[str, List[int]] = {}
    for q, rels in data.items():
        out[q] = [int(x) for x in rels]
    return out


# -----------------------------
# Evaluation
# -----------------------------
def eval_version(ev: Evaluator, qrels: Dict[str, List[int]], name: str) -> Tuple[pd.DataFrame, Dict[str, float]]:
    rows: List[Dict[str, Any]] = []

    for i, (query, rel_list) in enumerate(qrels.items(), start=1):
        rel = set(rel_list)

        res = ev.search(query)  # [(doc_id, title), ...]
        ranked_ids = [int(doc_id) for doc_id, _ in res]

        p5 = precision_at_k(ranked_ids, rel, 5)
        p10 = precision_at_k(ranked_ids, rel, 10)
        f1_30 = f1_at_30(ranked_ids, rel)
        hm = harmonic_mean(p5, f1_30)

        rows.append({
            "version": name,
            "qid": i,
            "query": query,
            "p@5": p5,
            "p@10": p10,
            "f1@30": f1_30,
            "hm(p@5,f1@30)": hm,
            "n_rel": len(rel),
            "n_returned": len(ranked_ids),
        })

        print(f"[{name}] Q{i:02d}  P@5={p5:.3f}  P@10={p10:.3f}  F1@30={f1_30:.3f}  HM={hm:.3f}  | {query}")

    df = pd.DataFrame(rows)

    summary = {
        "version": name,
        "avg_p@5": float(df["p@5"].mean()),
        "avg_p@10": float(df["p@10"].mean()),
        "avg_f1@30": float(df["f1@30"].mean()),
        "avg_hm(p@5,f1@30)": float(df["hm(p@5,f1@30)"].mean()),
    }

    print(f"\n== Averages for {name} ==")
    print(f"avg P@5   = {summary['avg_p@5']:.4f}")
    print(f"avg P@10  = {summary['avg_p@10']:.4f}")
    print(f"avg F1@30 = {summary['avg_f1@30']:.4f}")
    print(f"avg HM    = {summary['avg_hm(p@5,f1@30)']:.4f}\n")

    return df, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--qrels", default="queries_train.json", help="queries_train.json (query -> relevant doc ids)")
    ap.add_argument("--bucket", default=os.getenv("BUCKET_NAME", ""), help="GCS bucket name (or env BUCKET_NAME)")
    ap.add_argument("--postings_prefix", default=os.getenv("POSTINGS_PREFIX", ""), help="GCS postings prefix (or env POSTINGS_PREFIX)")
    ap.add_argument("--metadata_prefix", default=os.getenv("METADATA_PREFIX", ""), help="GCS metadata prefix (or env METADATA_PREFIX)")
    ap.add_argument("--cache_dir", default=os.getenv("CACHE_DIR", os.path.expanduser("~/cache")), help="Cache dir (default: ~/cache or env CACHE_DIR)")
    ap.add_argument("--max_results", type=int, default=100)
    ap.add_argument("--max_workers", type=int, default=5)
    ap.add_argument("--parallel_bm25", action="store_true", help="Use parallel BM25 inside a query (should not change ranking)")
    ap.add_argument("--alpha_pr", type=float, default=0.15, help="alpha for PageRank version")
    args = ap.parse_args()

    if not args.bucket or not args.postings_prefix or not args.metadata_prefix:
        raise SystemExit("Missing --bucket/--postings_prefix/--metadata_prefix (or env vars BUCKET_NAME/POSTINGS_PREFIX/METADATA_PREFIX).")

    qrels = load_qrels(args.qrels)

    # Build stores ONCE (shared between versions)
    idx_store = IndexStoreCached(
        bucket_name=args.bucket,
        postings_prefix=args.postings_prefix,
        cache_dir=os.path.join(args.cache_dir, "postings_cache"),
        index_name="index",
        project_id=None,
        force_download=False,
    )

    meta_store = build_metadata_store_from_gcs(
        bucket_name=args.bucket,
        metadata_prefix=args.metadata_prefix,
        cache_dir=os.path.join(args.cache_dir, "meta_cache"),
        project_id=None,
        force_download=False,
    )

    # Two "major versions" for quality:
    # 1) BM25 only (no PageRank)
    # 2) BM25 + PageRank
    versions = [
        ("BM25 only (no PageRank)", 0.0),
        (f"BM25 + PageRank (alpha={args.alpha_pr:g})", args.alpha_pr),
    ]

    all_per_query = []
    all_summaries = []

    for name, alpha in versions:
        ev = Evaluator(
            index_store=idx_store,
            meta_store=meta_store,
            tokenizer=tokenize,
            alpha_pagerank=alpha,
            max_results=args.max_results,
            max_workers=args.max_workers,
            parallel_bm25=bool(args.parallel_bm25),
        )

        df_per, summ = eval_version(ev, qrels, name)
        all_per_query.append(df_per)
        all_summaries.append(summ)

    per_df = pd.concat(all_per_query, ignore_index=True)
    sum_df = pd.DataFrame(all_summaries)

    per_df.to_csv("per_query_quality.csv", index=False, encoding="utf-8")
    sum_df.to_csv("summary_quality.csv", index=False, encoding="utf-8")

    # -----------------------------
    # Graph: official quality score
    # "average across test queries of harmonic mean of P@5 and F1@30"
    # -----------------------------
    plt.figure(figsize=(8, 5))
    plt.bar(sum_df["version"], sum_df["avg_hm(p@5,f1@30)"])
    plt.ylabel("Quality score (avg HM of P@5 and F1@30)")
    plt.title("Results quality by major engine version")
    plt.xticks(rotation=15, ha="right")
    plt.grid(axis="y", linestyle="--", alpha=0.3)
    plt.tight_layout()
    plt.savefig("quality_versions.png", dpi=220)
    plt.close()

    print("Saved:")
    print(" - per_query_quality.csv")
    print(" - summary_quality.csv")
    print(" - quality_versions.png")


if __name__ == "__main__":
    main()
