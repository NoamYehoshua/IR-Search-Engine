# prepare_frontend_cache.py
"""
Prepare (warm) the local cache needed by the search frontend.

What this script downloads:
1) postings_gcp/index.pkl  -> local: $CACHE_DIR/postings_cache/index.pkl
2) all metadata/*.pkl      -> local: $CACHE_DIR/meta_cache/<file>.pkl

What it DOES NOT download:
- The large postings .bin files (posting lists). Those are read lazily from GCS during search.
"""

import os
from pathlib import Path
from google.cloud import storage


def make_gcs_client() -> storage.Client:
    """
    Create a GCS client.

    If GCP_PROJECT_ID is set, we pass it to the client.
    Otherwise we rely on ADC (Application Default Credentials),
    which works on a properly configured GCE VM.
    """
    project_id = os.getenv("GCP_PROJECT_ID") or os.getenv("GOOGLE_CLOUD_PROJECT")
    return storage.Client(project=project_id) if project_id else storage.Client()


def download_if_missing(bucket_name: str, gcs_path: str, local_path: str) -> None:
    """
    Download a single object from GCS to local disk only if it doesn't already exist.
    """
    lp = Path(local_path)
    lp.parent.mkdir(parents=True, exist_ok=True)

    if lp.exists() and lp.stat().st_size > 0:
        print(f"SKIP (exists): {local_path}")
        return

    client = make_gcs_client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)

    # Optional check: fail fast if object does not exist
    if not blob.exists():
        raise FileNotFoundError(f"GCS object not found: gs://{bucket_name}/{gcs_path}")

    print(f"DOWNLOADING: gs://{bucket_name}/{gcs_path} -> {local_path}")
    blob.download_to_filename(str(lp))


def main() -> None:
    # Read configuration from environment variables (same names as in search_frontend.py)
    bucket_name = os.environ["BUCKET_NAME"]           # e.g. 207400714-task3
    postings_prefix = os.environ["POSTINGS_PREFIX"]   # e.g. postings_gcp
    metadata_prefix = os.environ["METADATA_PREFIX"]   # e.g. metadata
    cache_dir = os.environ["CACHE_DIR"]               # e.g. /home/$USER/cache

    # 1) Download postings index.pkl (required)
    download_if_missing(
        bucket_name=bucket_name,
        gcs_path=f"{postings_prefix}/index.pkl",
        local_path=os.path.join(cache_dir, "postings_cache", "index.pkl"),
    )

    # 2) Download all metadata .pkl files (recommended)
    client = make_gcs_client()
    prefix = f"{metadata_prefix}/"  # list objects under "metadata/"
    blobs = list(client.list_blobs(bucket_name, prefix=prefix))
    pkl_blobs = [b for b in blobs if b.name.endswith(".pkl")]

    if not pkl_blobs:
        print(f"WARNING: No .pkl files found under gs://{bucket_name}/{metadata_prefix}/")
    else:
        for b in pkl_blobs:
            filename = b.name.split("/")[-1]
            download_if_missing(
                bucket_name=bucket_name,
                gcs_path=b.name,
                local_path=os.path.join(cache_dir, "meta_cache", filename),
            )

    print("OK: cache is ready.")
    print("Local index:", os.path.join(cache_dir, "postings_cache", "index.pkl"))
    print("Local meta dir:", os.path.join(cache_dir, "meta_cache"))


if __name__ == "__main__":
    main()
