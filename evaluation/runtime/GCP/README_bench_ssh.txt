SSH Runtime Benchmark

This folder contains bench_ssh_simple.py which measures per-query runtime on the GCP VM.

Required env vars (set in your SSH session):
  BUCKET_NAME        - your GCS bucket name (required)
  POSTINGS_PREFIX    - postings/index prefix in the bucket (required)
Optional:
  METADATA_PREFIX    - metadata prefix (default: metadata)
  CACHE_DIR          - local cache dir (default: ~/cache)
  GOOGLE_CLOUD_PROJECT or GCP_PROJECT_ID - project id (optional)

Example:
  export BUCKET_NAME="YOUR_BUCKET"
  export POSTINGS_PREFIX="runs/full/postings"
  export CACHE_DIR="$HOME/cache"

Run (from repo root):
  python -u evaluation/runtime/bench_ssh_simple.py --queries evaluation/queries/queries_train.json --mode both --workers 5

Modes:
  --mode seq   (single-thread)
  --mode thr   (multi-thread, set --workers)
  --mode both  (default)
