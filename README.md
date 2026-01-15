# IR Search Engine (Wiki) — Final Project

This repository contains our end-to-end Information Retrieval system for English Wikipedia:
- **Index building** (Mini corpus in Colab + Full Wikipedia corpus in GCP)
- **Search backend** (BM25, optional PageRank re-ranking, threaded BM25)
- **Deployment on a GCP VM** (systemd service + cache preparation)
- **Evaluation** (quality metrics + runtime/latency benchmarks)

> **Live demo URL (fill for submission):** `http://<EXTERNAL_IP>:8080/search?query=hello+world`  
> **Public GCS bucket:** `gs://207400714-task3`  
> Replace bucket/prefix values when running on a different setup.

---

## Ranking logic and evaluation approach

### Core retrieval model
Our best `/search` method ranks documents using **BM25** over the article body, with the same tokenization + stop-word removal used when building the index (to keep term spaces consistent).

### Optional PageRank re-ranking (best version)
We also tested a combined score that mixes BM25 with a popularity/salience signal (**PageRank**).  
In our experiments, using **alpha = 0.15** improved (or did not degrade) the quality metrics compared to BM25 alone.

Conceptually:
- **BM25-only**: rank by BM25 score.
- **BM25 + PageRank**: rank by a weighted combination, where `alpha` controls PageRank contribution (default `0.15`).

### Parallelization
To improve latency, BM25 can be computed using a `ThreadPoolExecutor`:
- each query term is handled by a separate thread,
- the thread loads the posting list for that term and contributes to document scores,
- results are accumulated and sorted.

### How we evaluate quality
We evaluate retrieval quality over `queries_train.json` using:
- **Precision@5 (P@5)**
- **Precision@10 (P@10)**
- **F1@30**
- **HM** = harmonic mean(P@5, F1@30) — used as the main summary score.

See `evaluation/performance/` for scripts and output CSVs.

---

## Repository structure

```
app/
  full/   # server code configured for the full index (GCP artifacts)
  mini/   # server code configured for the mini index (Colab artifacts)

data_structures/
  full/         # notebooks/scripts to build the full index + metadata on GCP
  mini/         # notebooks/scripts to build the mini index on Colab
  Data_Example/ # small example artifacts (for sanity checks & demos)

deployment/
  create_instance/     # create VM + open firewall + startup script
  bootstrap_instance/  # upload files, venv, cache build, systemd service

evaluation/
  performance/   # quality evaluation + plots
  runtime/       # latency benchmarks (local + GCP/SSH)
  training queries/queries_train.json   # training queries + relevance lists
```

---

## Major components (what each main file does)

### App (server + ranking)
- `app/*/search_frontend.py` — Flask server. Exposes `/search?query=...` and returns top results (doc_id + title).
- `app/*/evaluator.py` — scoring/ranking logic: BM25 (and BM25+PageRank option) + optional threaded BM25.
- `app/*/tokenizer.py` — tokenization and stop-word removal (must match the index-building logic).
- `app/*/index_store_cached.py` — loads `index.pkl` and reads posting lists lazily (from GCS or local cache).
- `app/*/metadata_store.py` — loads metadata pickles (titles, doc_len, corpus_stats, pagerank) into RAM.
- `app/*/prepare_frontend_cache.py` — downloads artifacts from GCS into `CACHE_DIR` before the server starts.
- `app/*/inverted_index_gcp.py` / `app/mini/inverted_index_colab.py` — index I/O utilities (read/write posting lists).

### Index building (notebooks)
- `data_structures/mini/Proj_IR_MiniIndex.ipynb` — builds a mini index (Colab-sized).
- `data_structures/full/Full_Inverted_Index_PR_ass3.ipynb` — builds the full index + ranking signals on GCP.
- `data_structures/full/CreateMetaDataFull.ipynb` — builds and saves metadata files for the full corpus.
- `data_structures/Data_Example/` — small example artifacts for sanity checks (not the full dataset).

### Deployment (GCP VM)
- `deployment/create_instance/run_frontend_in_gcp.sh` — creates a VM, opens port 8080, prints SCP/SSH commands.
- `deployment/create_instance/startup_script_gcp.sh` — startup script: installs Python and creates `~/venv`.
- `deployment/bootstrap_instance/ir-search.service` — systemd service: runs cache-prep, then starts the Flask app.
- `deployment/bootstrap_instance/app.env` — environment variables (bucket/prefixes/cache path).
- `deployment/bootstrap_instance/BOOTSTRAP_INSTANCE_STEPS.txt` — exact bootstrap commands (copy/paste).

### Evaluation
- `evaluation/performance/evaluate_quality_and_plot.py` — runs queries, computes P@5/P@10/F1@30/HM, outputs CSV + plot.
- `evaluation/runtime/local/benchmark_local.py` — local latency benchmark (config-driven).
- `evaluation/runtime/GCP/bench_ssh_simple.py` — latency benchmark on the VM via SSH.

---

## Data artifacts (GCS bucket) and how we load them

Our system separates **index storage** (postings) from **metadata** (RAM-friendly files).

### 1) Postings / inverted index (large, stored in GCS)
Stored under a postings prefix (e.g., `postings_gcp/` or `runs/<run_id>/postings/`):
- `index.pkl`  
  The `InvertedIndex` object containing:
  - `df` (document frequency per term)
  - `posting_locs` (file locations for each term’s posting list)
- postings binary files: `*_*.bin`  
  Contain packed `(doc_id, tf)` tuples for each term.

**How it’s used in code**
- `IndexStore` / `index_store_cached.py` loads `index.pkl` once, then reads posting lists **on demand** using `inverted_index_gcp.py` (lazy I/O to reduce RAM usage).

### 2) Metadata (small-to-medium, loaded to RAM)
Stored under a metadata prefix (e.g., `metadata/` or `runs/<run_id>/meta/`):
- `titles.pkl` — `doc_id -> title` (used to return titles)
- `doc_len.pkl` — `doc_id -> document length` (needed for BM25 normalization)
- `corpus_stats.pkl` — includes `N` (number of documents) and `avgdl` (average document length)
- `pagerank.pkl` — `doc_id -> PageRank score` (used when mixing BM25 + PR)

**How it’s used in code**
- `metadata_store.py` loads these pickles to RAM and exposes a small API used by `evaluator.py`.

### 3) Local cache on the VM (no query-time caching)
To avoid repeated downloads from GCS on each VM restart, we build a **local cache on startup**:
- `prepare_frontend_cache.py` downloads the needed artifacts into `CACHE_DIR` before the server starts.
- This is done once during service startup (`ExecStartPre=`), then the server runs normally.

---

## Data_Example (in this repo)
`data_structures/Data_Example/` contains a small subset of artifacts for quick validation:
- `corpus_stats.pkl`, `doc_len.pkl`, `index.pkl`, `pagerank.pkl`

> Note: `titles.pkl` can be very large (often > 100MB), so we keep it in the GCS bucket and avoid committing it to GitHub.

---

## Running the server (local)

The Flask server entry point is:
- `app/full/search_frontend.py` (full index)
- `app/mini/search_frontend.py` (mini index)

Example:
```bash
python -u app/full/search_frontend.py
```

The server expects environment variables (bucket, prefixes, cache path).  
See `deployment/bootstrap_instance/app.env` (or create your own `app.env` from the template described there).

---

## Deployment on GCP (recommended for submission)

### 1) Create the VM (one-time)
See:
- `deployment/create_instance/README_create_instance.md`

Includes:
- what to fill in `run_frontend_in_gcp.sh` and `startup_script_gcp.sh`
- how to create a VM with a public IP and open port `8080`

### 2) Bootstrap the VM (make it a service)
See:
- `deployment/bootstrap_instance/README_boostrap.md`
- `deployment/bootstrap_instance/BOOTSTRAP_INSTANCE_STEPS.txt`

You will:
1. Upload required files to the VM (app code + `app.env` + `ir-search.service`)
2. Create a venv on the VM
3. Run `prepare_frontend_cache.py` to build local caches
4. Install and start `ir-search.service` (systemd)

Useful commands:
```bash
sudo systemctl status ir-search.service --no-pager
sudo journalctl -u ir-search.service -f
```

---

## Evaluation

### Quality evaluation
Folder:
- `evaluation/performance/`

Script:
- `evaluate_quality_and_plot.py`

Outputs:
- `results/per_query_quality.csv`
- `results/summary_quality.csv`
- `results/results.txt`

See:
- `evaluation/performance/README_evaluate.txt`

### Runtime / latency benchmarks
Folder:
- `evaluation/runtime/`

Local:
- `evaluation/runtime/local/benchmark_local.py`
- `evaluation/runtime/local/bench_config_local_example.json`
- `evaluation/runtime/local/run_benchmark_local.txt`

GCP VM (via SSH):
- `evaluation/runtime/GCP/bench_ssh_simple.py`
- `evaluation/runtime/GCP/README_bench_ssh.txt`

---

## Authors
- Noam Yehoshua
- Bar Elhayani
