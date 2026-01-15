# benchmark_local.py
from __future__ import annotations

import argparse
import csv
import json
import os
import time
import statistics
from dataclasses import dataclass
from typing import Dict, Any, List, Optional

import matplotlib.pyplot as plt

from index_store_cached import IndexStoreCached
from metadata_store import build_metadata_store_from_gcs
from evaluator import Evaluator
from tokenizer import tokenize


@dataclass
class RunSpec:
    name: str
    bucket_name: str
    postings_prefix: str
    metadata_prefix: str
    index_cache_dir: str
    metadata_cache_dir: str
    parallel_bm25: bool
    max_workers: int
    alpha_pagerank: float
    k1: float
    b: float
    max_results: int
    force_download: bool = False


def load_queries(path: str) -> List[str]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # queries_train.json is { "query": [relevant_doc_ids...] }
    return list(data.keys())


def percentile(values: List[float], p: float) -> float:
    if not values:
        return float("nan")
    s = sorted(values)
    k = (len(s) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return s[f]
    return s[f] + (s[c] - s[f]) * (k - f)


def run_benchmark(spec: RunSpec, queries: List[str], repeats: int, warmup: int) -> Dict[str, Any]:
    # Build stores
    idx_store = IndexStoreCached(
        bucket_name=spec.bucket_name,
        postings_prefix=spec.postings_prefix,
        cache_dir=spec.index_cache_dir,
        index_name="index",
        project_id=None,
        force_download=spec.force_download,
    )

    meta_store = build_metadata_store_from_gcs(
        bucket_name=spec.bucket_name,
        metadata_prefix=spec.metadata_prefix,
        cache_dir=spec.metadata_cache_dir,
        project_id=None,
        force_download=spec.force_download,
    )

    ev = Evaluator(
        index_store=idx_store,
        meta_store=meta_store,
        tokenizer=tokenize,
        k1=spec.k1,
        b=spec.b,
        alpha_pagerank=spec.alpha_pagerank,
        max_results=spec.max_results,
        max_workers=spec.max_workers,
        parallel_bm25=spec.parallel_bm25,
    )

    # Warmup (not counted)
    for i in range(min(warmup, len(queries))):
        _ = ev.search(queries[i])

    latencies_ms: List[float] = []
    per_query_rows: List[List[Any]] = []

    for q in queries:
        # Repeat for stability
        times = []
        last_count = 0
        for _ in range(repeats):
            t0 = time.perf_counter()
            res = ev.search(q)  # includes BM25 + PageRank blend + titles
            t1 = time.perf_counter()
            times.append((t1 - t0) * 1000.0)
            last_count = len(res)

        avg_ms = sum(times) / len(times)
        latencies_ms.append(avg_ms)
        per_query_rows.append([spec.name, q, f"{avg_ms:.2f}", last_count])

    summary = {
        "variant": spec.name,
        "n_queries": len(queries),
        "mean_ms": statistics.mean(latencies_ms) if latencies_ms else float("nan"),
        "median_ms": statistics.median(latencies_ms) if latencies_ms else float("nan"),
        "p90_ms": percentile(latencies_ms, 90),
        "p95_ms": percentile(latencies_ms, 95),
        "parallel_bm25": spec.parallel_bm25,
        "max_workers": spec.max_workers,
        "alpha_pagerank": spec.alpha_pagerank,
        "k1": spec.k1,
        "b": spec.b,
        "postings_prefix": spec.postings_prefix,
        "metadata_prefix": spec.metadata_prefix,
    }

    return {
        "summary": summary,
        "per_query_rows": per_query_rows,
    }


def save_csv(path: str, header: List[str], rows: List[List[Any]]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def plot_latency_bar(summaries: List[Dict[str, Any]], out_png: str) -> None:
    names = [s["variant"] for s in summaries]
    means = [s["mean_ms"] for s in summaries]

    plt.figure()
    plt.bar(names, means)
    plt.ylabel("Mean latency (ms)")
    plt.title("Average query retrieval time per version (BM25 + PageRank)")
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    plt.savefig(out_png, dpi=200)
    plt.close()


def parse_runs_config(config_path: str) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="Path to bench_config_local.json")
    ap.add_argument("--queries", required=True, help="Path to queries_train.json")
    ap.add_argument("--out_dir", default="bench_out", help="Output directory")
    ap.add_argument("--limit", type=int, default=None, help="Optional: run only first N queries")
    ap.add_argument("--repeats", type=int, default=1, help="Timed repeats per query (avg them)")
    ap.add_argument("--warmup", type=int, default=1, help="Warmup queries per variant (not counted)")
    args = ap.parse_args()

    cfg = parse_runs_config(args.config)
    runs_cfg = cfg["runs"]

    queries = load_queries(args.queries)
    if args.limit is not None:
        queries = queries[: args.limit]

    all_summaries: List[Dict[str, Any]] = []
    all_per_query: List[List[Any]] = []

    for r in runs_cfg:
        spec = RunSpec(
            name=r["name"],
            bucket_name=r.get("bucket_name") or os.environ.get("BUCKET_NAME", ""),
            postings_prefix=r.get("postings_prefix") or os.environ.get("POSTINGS_PREFIX", ""),
            metadata_prefix=r.get("metadata_prefix") or os.environ.get("METADATA_PREFIX", ""),
            index_cache_dir = r.get("index_cache_dir") or os.environ.get("INDEX_CACHE_DIR", os.path.join(".cache", "index")),
            metadata_cache_dir = r.get("metadata_cache_dir") or os.environ.get("METADATA_CACHE_DIR", os.path.join(".cache", "metadata")),
            parallel_bm25=bool(r.get("parallel_bm25", False)),
            max_workers=int(r.get("max_workers", 1)),
            alpha_pagerank=float(r.get("alpha_pagerank", 0.15)),
            k1=float(r.get("k1", 1.2)),
            b=float(r.get("b", 0.75)),
            max_results=int(r.get("max_results", 100)),
            force_download=bool(r.get("force_download", False)),
        )

        if not spec.bucket_name or not spec.postings_prefix or not spec.metadata_prefix:
            raise ValueError(f"Missing bucket/prefixes for run '{spec.name}'")

        print(f"\n=== Running: {spec.name} ===")
        print(f"postings_prefix={spec.postings_prefix} | metadata_prefix={spec.metadata_prefix}")
        print(f"parallel_bm25={spec.parallel_bm25} | max_workers={spec.max_workers} | alpha={spec.alpha_pagerank}")

        out = run_benchmark(spec, queries, repeats=args.repeats, warmup=args.warmup)
        all_summaries.append(out["summary"])
        all_per_query.extend(out["per_query_rows"])

        print("Summary:", out["summary"])

    # Save outputs
    out_dir = args.out_dir
    os.makedirs(out_dir, exist_ok=True)

    save_csv(
        os.path.join(out_dir, "per_query.csv"),
        ["variant", "query", "latency_ms_avg", "results_count"],
        all_per_query,
    )

    save_csv(
        os.path.join(out_dir, "summary.csv"),
        ["variant", "n_queries", "mean_ms", "median_ms", "p90_ms", "p95_ms",
         "parallel_bm25", "max_workers", "alpha_pagerank", "k1", "b",
         "postings_prefix", "metadata_prefix"],
        [[
            s["variant"], s["n_queries"],
            f"{s['mean_ms']:.2f}", f"{s['median_ms']:.2f}",
            f"{s['p90_ms']:.2f}", f"{s['p95_ms']:.2f}",
            s["parallel_bm25"], s["max_workers"],
            s["alpha_pagerank"], s["k1"], s["b"],
            s["postings_prefix"], s["metadata_prefix"],
        ] for s in all_summaries],
    )

    plot_latency_bar(all_summaries, os.path.join(out_dir, "latency_bar.png"))

    print("\nSaved:")
    print(" -", os.path.join(out_dir, "per_query.csv"))
    print(" -", os.path.join(out_dir, "summary.csv"))
    print(" -", os.path.join(out_dir, "latency_bar.png"))


if __name__ == "__main__":
    main()
