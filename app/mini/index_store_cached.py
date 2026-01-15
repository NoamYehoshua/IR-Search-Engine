# index_store_cached.py
from __future__ import annotations

import os
import pickle
from typing import List, Tuple, Optional

from google.cloud import storage

from inverted_index_gcp import InvertedIndex

DocId = int
Posting = List[Tuple[DocId, int]]


def get_gcs_client(project_id: Optional[str] = None) -> storage.Client:
    return storage.Client(project=project_id) if project_id else storage.Client()


def ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def download_if_missing(
    client: storage.Client,
    bucket_name: str,
    gcs_path: str,
    local_path: str,
    force: bool = False,
) -> None:
    ensure_dir(os.path.dirname(local_path))
    if (not force) and os.path.exists(local_path):
        return
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    if not blob.exists():
        raise FileNotFoundError(f"GCS object not found: gs://{bucket_name}/{gcs_path}")
    blob.download_to_filename(local_path)


def load_pickle(local_path: str):
    with open(local_path, "rb") as f:
        return pickle.load(f)


class IndexStoreCached:
    """
    - Downloads index.pkl to local disk cache_dir (once).
    - Loads index.pkl into memory (df + posting_locs).
    - Reads posting lists lazily from GCS per term.
    """

    def __init__(
        self,
        bucket_name: str,
        postings_prefix: str,
        cache_dir: str,
        index_name: str = "index",
        project_id: Optional[str] = None,
        force_download: bool = False,
    ):
        self.bucket_name = bucket_name
        self.postings_prefix = postings_prefix.strip("/")
        self.cache_dir = cache_dir
        self.index_name = index_name
        self.project_id = project_id
        self.force_download = force_download

        client = get_gcs_client(project_id)

        # Download index.pkl locally
        index_pkl_name = f"{index_name}.pkl"
        gcs_index_path = f"{self.postings_prefix}/{index_pkl_name}"
        local_index_path = os.path.join(self.cache_dir, index_pkl_name)

        download_if_missing(
            client=client,
            bucket_name=self.bucket_name,
            gcs_path=gcs_index_path,
            local_path=local_index_path,
            force=self.force_download,
        )

        # Load index object from local disk
        loaded = load_pickle(local_index_path)
        if not isinstance(loaded, InvertedIndex):
            raise TypeError(
                f"Loaded object from {local_index_path} is not InvertedIndex. "
                "Possible pickle module-name mismatch."
            )

        self.index: InvertedIndex = loaded

    def df(self, term: str) -> int:
        return int(self.index.df.get(term, 0))

    def read_posting_list(self, term: str) -> Posting:
        return self.index.read_a_posting_list(
            base_dir=self.postings_prefix,
            w=term,
            bucket_name=self.bucket_name,
        )
