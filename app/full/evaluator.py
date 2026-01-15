from __future__ import annotations

import math
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple, Protocol, Optional


class IIndexStore(Protocol):
    def df(self, term: str) -> int: ...
    def read_posting_list(self, term: str) -> List[Tuple[int, int]]: ...


class IMetaStore(Protocol):
    def get_title(self, doc_id: int) -> str: ...
    def get_len(self, doc_id: int) -> int: ...
    def get_pagerank(self, doc_id: int) -> float: ...
    @property
    def avgdl(self) -> float: ...
    @property
    def N(self) -> int: ...


class Evaluator:
    def __init__(
        self,
        index_store: IIndexStore,
        meta_store: IMetaStore,
        tokenizer,  # callable: str -> List[str]
        k1: float = 1.2,
        b: float = 0.75,
        alpha_pagerank: float = 0.15,
        max_results: int = 100,
        max_workers: int = 5,          # <= NEW: max parallel terms
        parallel_bm25: bool = True,    # <= NEW: toggle
    ):
        self.idx = index_store
        self.meta = meta_store
        self.tokenize = tokenizer

        self.k1 = k1
        self.b = b
        self.alpha = alpha_pagerank
        self.max_results = max_results

        self.max_workers = max_workers
        self.parallel_bm25 = parallel_bm25

    # --------- term-level scoring (runs per term, can run in threads) ---------
    def _score_one_term(self, term: str, N: float, avgdl: float) -> Dict[int, float]:
        """
        Compute BM25 contribution of a SINGLE term over all docs in its posting list.
        Returns: {doc_id -> partial_score_for_this_term}
        """
        df = self.idx.df(term)
        if df <= 0:
            return {}

        idf = math.log(1.0 + (N - df + 0.5) / (df + 0.5))

        local: Dict[int, float] = defaultdict(float)
        posting_list = self.idx.read_posting_list(term)

        for doc_id, tf in posting_list:
            dl = self.meta.get_len(doc_id)
            if dl <= 0:
                continue

            norm = (1.0 - self.b) + self.b * (dl / avgdl) if avgdl > 0 else 1.0
            denom = tf + self.k1 * norm
            score = idf * (tf * (self.k1 + 1.0)) / (denom if denom != 0 else 1.0)

            local[int(doc_id)] += float(score)

        return local

    # ---------------- BM25 core (sequential) ----------------
    def bm25_scores(self, query_tokens: List[str]) -> Dict[int, float]:
        scores: Dict[int, float] = defaultdict(float)

        N = float(self.meta.N)
        avgdl = float(self.meta.avgdl) if self.meta.avgdl > 0 else 0.0

        # Only unique terms matter in your current formula (you ignore query tf)
        for term in Counter(query_tokens).keys():
            local = self._score_one_term(term, N, avgdl)
            for doc_id, s in local.items():
                scores[doc_id] += s

        return scores

    # ---------------- BM25 core (parallel: up to max_workers) ----------------
    def bm25_scores_parallel(self, query_tokens: List[str]) -> Dict[int, float]:
        scores: Dict[int, float] = defaultdict(float)

        N = float(self.meta.N)
        avgdl = float(self.meta.avgdl) if self.meta.avgdl > 0 else 0.0

        terms = list(Counter(query_tokens).keys())
        if not terms:
            return {}

        workers = min(self.max_workers, len(terms))

        # Thread pool will run at most `workers` terms in parallel,
        # and automatically queue the rest (no need for "rounds").
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(self._score_one_term, t, N, avgdl) for t in terms]
            for fut in as_completed(futures):
                local = fut.result()
                for doc_id, s in local.items():
                    scores[doc_id] += s

        return scores

    # ---------------- PageRank blend ----------------
    def blend_with_pagerank(self, bm25: Dict[int, float]) -> List[Tuple[int, float]]:
        if not bm25:
            return []

        # ---- 1) Min-Max normalize BM25 to [0,1] (monotonic => BM25-only ranking unchanged) ----
        bm_vals = list(bm25.values())
        bm_min, bm_max = min(bm_vals), max(bm_vals)
        if bm_max == bm_min:
            bm_norm = {doc_id: 0.0 for doc_id in bm25.keys()}
        else:
            bm_norm = {doc_id: (s - bm_min) / (bm_max - bm_min) for doc_id, s in bm25.items()}

        # ---- 2) Get PageRank for same candidate set and normalize to [0,1] ----
        pr_values = {doc_id: float(self.meta.get_pagerank(doc_id)) for doc_id in bm25.keys()}
        pr_vals = list(pr_values.values())
        pr_min, pr_max = (min(pr_vals), max(pr_vals)) if pr_vals else (0.0, 0.0)

        if pr_max == pr_min:
            pr_norm = {doc_id: 0.0 for doc_id in bm25.keys()}
        else:
            pr_norm = {doc_id: (pr - pr_min) / (pr_max - pr_min) for doc_id, pr in pr_values.items()}

        # ---- 3) Blend in the SAME scale ----
        combined: List[Tuple[int, float]] = []
        a = float(self.alpha)

        for doc_id in bm25.keys():
            final_score = (1.0 - a) * bm_norm.get(doc_id, 0.0) + a * pr_norm.get(doc_id, 0.0)
            combined.append((doc_id, final_score))

        combined.sort(key=lambda x: x[1], reverse=True)
        return combined


    # ---------------- Public API ----------------
    def search(self, query: str) -> List[Tuple[int, str]]:
        if not query:
            return []

        tokens = self.tokenize(query)
        if not tokens:
            return []

        if self.parallel_bm25:
            bm25 = self.bm25_scores_parallel(tokens)
        else:
            bm25 = self.bm25_scores(tokens)

        if not bm25:
            return []

        ranked = self.blend_with_pagerank(bm25)

        res: List[Tuple[int, str]] = []
        for doc_id, _ in ranked[: self.max_results]:
            res.append((int(doc_id), self.meta.get_title(doc_id) or ""))

        return res
