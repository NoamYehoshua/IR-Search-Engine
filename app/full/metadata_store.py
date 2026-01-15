# metadata_store.py
from __future__ import annotations

import os
import pickle
from dataclasses import dataclass
from typing import Any, Dict, Optional

from google.cloud import storage

DocId = int


def get_gcs_client(project_id: Optional[str] = None) -> storage.Client:
    """Create a GCS client using ADC / service account JSON."""
    return storage.Client(project=project_id) if project_id else storage.Client()


def ensure_dir(path: str) -> None:
    """Create directory (and parents) if it doesn't exist."""
    os.makedirs(path, exist_ok=True)


def download_if_missing(
    client: storage.Client,
    bucket_name: str,
    gcs_path: str,
    local_path: str,
    force: bool = False,
) -> None:
    """
    Download one object from GCS into a local file.
    If force=False: download only if local file does not exist.
    If force=True: always download (overwrite).
    """
    ensure_dir(os.path.dirname(local_path))

    if (not force) and os.path.exists(local_path):
        return

    bucket = client.bucket(bucket_name)
    blob = bucket.blob(gcs_path)
    if not blob.exists():
        raise FileNotFoundError(f"GCS object not found: gs://{bucket_name}/{gcs_path}")

    blob.download_to_filename(local_path)


def load_pickle(local_path: str) -> Any:
    """Load a Python object from a local pickle file."""
    with open(local_path, "rb") as f:
        return pickle.load(f)


@dataclass
class MetaDataStore:
    """In-memory metadata store."""
    titles: Dict[DocId, str]
    doc_len: Dict[DocId, int]
    pagerank: Optional[Dict[DocId, float]] = None
    pageviews: Optional[Dict[DocId, int]] = None
    corpus_stats: Optional[Dict[str, Any]] = None

    def get_title(self, doc_id: DocId) -> str:
        return self.titles.get(doc_id, "")

    def get_len(self, doc_id: DocId) -> int:
        return int(self.doc_len.get(doc_id, 0))
    
    @property
    def N(self) -> int:
        """Number of documents in the corpus."""
        # Prefer corpus_stats if exists (more 'official'), otherwise derive from doc_len
        if self.corpus_stats and "N" in self.corpus_stats:
            return int(self.corpus_stats["N"])
        return len(self.doc_len)

    @property
    def avgdl(self) -> float:
        """Average document length (in tokens)."""
        if self.corpus_stats and "avgdl" in self.corpus_stats:
            return float(self.corpus_stats["avgdl"])
        n = self.N
        return (sum(self.doc_len.values()) / n) if n > 0 else 0.0

    def get_pagerank(self, doc_id: DocId) -> float:
        return float(self.pagerank.get(doc_id, 0.0)) if self.pagerank else 0.0

    def get_pageviews(self, doc_id: DocId) -> int:
        return int(self.pageviews.get(doc_id, 0)) if self.pageviews else 0


def build_metadata_store_from_gcs(
    bucket_name: str,
    metadata_prefix: str,
    cache_dir: str,
    project_id: Optional[str] = None,
    force_download: bool = False,
    filenames: Optional[Dict[str, Optional[str]]] = None,
) -> MetaDataStore:
    """
    1) Download PKL files from GCS to local cache_dir
    2) Load PKLs into memory
    3) Return MetaDataStore
    """
    if filenames is None:
        filenames = {
            "titles": "titles.pkl",
            "doc_len": "doc_len.pkl",
            "pagerank": "pagerank.pkl",
            "pageviews": "pageviews.pkl",
            "corpus_stats": "corpus_stats.pkl",
        }

    metadata_prefix = metadata_prefix.strip("/")
    client = get_gcs_client(project_id)

    def gcs_path(name: str) -> str:
        return f"{metadata_prefix}/{name}" if metadata_prefix else name

    titles_name = filenames.get("titles")
    doc_len_name = filenames.get("doc_len")
    if not titles_name or not doc_len_name:
        raise ValueError("filenames must include non-empty 'titles' and 'doc_len'.")

    titles_local = os.path.join(cache_dir, titles_name)
    doc_len_local = os.path.join(cache_dir, doc_len_name)

    download_if_missing(client, bucket_name, gcs_path(titles_name), titles_local, force_download)
    download_if_missing(client, bucket_name, gcs_path(doc_len_name), doc_len_local, force_download)

    # Optional files
    pagerank = None
    pageviews = None
    corpus_stats = None

    pagerank_name = filenames.get("pagerank")
    if pagerank_name:
        pagerank_local = os.path.join(cache_dir, pagerank_name)
        try:
            download_if_missing(client, bucket_name, gcs_path(pagerank_name), pagerank_local, force_download)
            pagerank = load_pickle(pagerank_local)
        except FileNotFoundError:
            pagerank = None

    pageviews_name = filenames.get("pageviews")
    if pageviews_name:
        pageviews_local = os.path.join(cache_dir, pageviews_name)
        try:
            download_if_missing(client, bucket_name, gcs_path(pageviews_name), pageviews_local, force_download)
            pageviews = load_pickle(pageviews_local)
        except FileNotFoundError:
            pageviews = None

    corpus_stats_name = filenames.get("corpus_stats")
    if corpus_stats_name:
        corpus_stats_local = os.path.join(cache_dir, corpus_stats_name)
        try:
            download_if_missing(client, bucket_name, gcs_path(corpus_stats_name), corpus_stats_local, force_download)
            corpus_stats = load_pickle(corpus_stats_local)
        except FileNotFoundError:
            corpus_stats = None

    titles = load_pickle(titles_local)
    doc_len = load_pickle(doc_len_local)

    if not isinstance(titles, dict) or not isinstance(doc_len, dict):
        raise TypeError("titles.pkl and doc_len.pkl must be dictionaries.")

    return MetaDataStore(
        titles=titles,
        doc_len=doc_len,
        pagerank=pagerank if isinstance(pagerank, dict) else None,
        pageviews=pageviews if isinstance(pageviews, dict) else None,
        corpus_stats=corpus_stats if isinstance(corpus_stats, dict) else None,
    )
