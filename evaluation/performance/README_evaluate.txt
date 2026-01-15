Quality Evaluation (P@5 / P@10 / F1@30 / HM) + Plot

What this script does
- Loads qrels from a JSON file (default: queries_train.json).
- Runs the engine (Evaluator.search) for each query.
- Computes:
  - P@5, P@10
  - F1@30
  - HM = harmonic mean(P@5, F1@30)  [this is the official "quality score"]
- Saves outputs:
  - per_query_quality.csv
  - summary_quality.csv
  - quality_versions.png

Prerequisites
1) Python deps:
   pip install -r requirements.txt

2) GCS access (choose ONE):
   A) Service account key:
      export BUCKET_NAME="YOUR_BUCKET"
      export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
   B) Application Default Credentials:
      gcloud auth application-default login

Required inputs (via args or env vars)
- --bucket OR env BUCKET_NAME
- --postings_prefix OR env POSTINGS_PREFIX
- --metadata_prefix OR env METADATA_PREFIX
- --qrels (default: queries_train.json)

Run (recommended)
From repo root:
python -u evaluation/performance/evaluate_quality_and_plot.py \
  --qrels evaluation/queries/queries_train.json \
  --bucket YOUR_BUCKET \
  --postings_prefix YOUR_POSTINGS_PREFIX \
  --metadata_prefix YOUR_METADATA_PREFIX \
  --cache_dir .cache

Notes
- The script evaluates two versions:
  1) BM25 only (no PageRank)
  2) BM25 + PageRank (alpha is controlled by --alpha_pr, default 0.15)
- Output files are written to the current working directory.
  If you want outputs inside evaluation/performance/, run the command from that folder.

Optional flags
- --parallel_bm25       Use multi-thread BM25 inside a single query (ranking should stay the same)
- --max_workers N       Number of workers for parallel BM25 (default: 5)
- --max_results N       Max results per query (default: 100)
- --alpha_pr X          PageRank alpha for the "BM25 + PageRank" version (default: 0.15)
