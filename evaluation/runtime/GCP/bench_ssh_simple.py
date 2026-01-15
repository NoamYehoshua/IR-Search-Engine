import os, json, argparse
from time import perf_counter

from index_store_cached import IndexStoreCached
from metadata_store import build_metadata_store_from_gcs
from tokenizer import tokenize
from evaluator import Evaluator


def load_queries(path: str):
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.keys())


def run_mode(ev: Evaluator, queries, mode_name: str):
    print(f"\n===== MODE: {mode_name} | queries={len(queries)} =====", flush=True)
    for i, q in enumerate(queries, 1):
        t0 = perf_counter()
        _ = ev.search(q)
        dt = perf_counter() - t0
        print(f"{mode_name}\t{i:02d}\t{dt:.6f}\t{q}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queries", required=True, help="path to queries_train.json")
    ap.add_argument("--mode", default="both", choices=["seq", "thr", "both"])
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    BUCKET_NAME = os.environ["BUCKET_NAME"]
    POSTINGS_PREFIX = os.environ["POSTINGS_PREFIX"]
    METADATA_PREFIX = os.environ.get("METADATA_PREFIX", "metadata")
    CACHE_DIR = os.environ.get("CACHE_DIR", os.path.expanduser("~/cache"))
    PROJECT_ID = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT")

    IDX = IndexStoreCached(
        bucket_name=BUCKET_NAME,
        postings_prefix=POSTINGS_PREFIX,
        cache_dir=os.path.join(CACHE_DIR, "postings_cache"),
        index_name="index",
        project_id=PROJECT_ID,
        force_download=False,
    )

    META = build_metadata_store_from_gcs(
        bucket_name=BUCKET_NAME,
        metadata_prefix=METADATA_PREFIX,
        cache_dir=os.path.join(CACHE_DIR, "meta_cache"),
        project_id=PROJECT_ID,
        force_download=False,
    )

    queries = load_queries(args.queries)

    _ = Evaluator(IDX, META, tokenize, alpha_pagerank=0.15, max_results=100,
                  parallel_bm25=False, max_workers=1).search(queries[0])

    if args.mode in ("seq", "both"):
        ev_seq = Evaluator(
            index_store=IDX,
            meta_store=META,
            tokenizer=tokenize,
            alpha_pagerank=0.15,
            max_results=100,
            parallel_bm25=False,
            max_workers=1,
        )
        run_mode(ev_seq, queries, "SEQ")

    if args.mode in ("thr", "both"):
        ev_thr = Evaluator(
            index_store=IDX,
            meta_store=META,
            tokenizer=tokenize,
            alpha_pagerank=0.15,
            max_results=100,
            parallel_bm25=True,
            max_workers=args.workers,
        )
        run_mode(ev_thr, queries, f"THR{args.workers}")


if __name__ == "__main__":
    main()