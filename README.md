# IR Search Engine (Wiki) — Final Project

This repository contains our end-to-end information retrieval system:
- **Index building** (Mini corpus in Colab + Full Wikipedia corpus in GCP)
- **Search engine backend** (BM25, optional PageRank re-ranking)
- **Deployment on a GCP VM** (systemd service + caching step)
- **Evaluation** (quality metrics + runtime/latency benchmarks)

> **Live demo URL:** `http://<EXTERNAL_IP>:8080/search?query=hello+world`  
> **GCS Bucket:** `gs://207400714-task3` (public)  
> Replace bucket/prefix values when running on a different setup.

---

## Repository structure

```
app/
  full/   # server code configured for the full index (GCP)
  mini/   # server code configured for the mini index (Colab artifacts)

data_structures/
  full/   # notebooks/scripts to build the full index + metadata on GCP
  mini/   # notebooks/scripts to build the mini index on Colab

deployment/
  create_instance/     # create VM + open firewall + startup script
  bootstrap_instance/  # upload files, venv, cache build, systemd service

evaluation/
  performance/   # quality evaluation + plots
  runtime/       # latency benchmarks (local + GCP/SSH)
  training queries/queries_train.json   # qrels (training queries)
```

---

## Search engine overview

### Data artifacts (stored in GCS)
We store artifacts in a bucket:
- **Inverted index** (`index.pkl` + postings `.bin` files)
- **Metadata** (pickle files):  
  `doc_id -> title`, `doc_id -> doc_len`, `corpus_stats (N, avgdl)`, plus ranking signals (e.g., PageRank)

Tokenization and stop-word removal are consistent across all artifacts to guarantee term alignment.

### Modular backend design (code)
- **Tokenizer** — tokenization + stopword removal (consistent with earlier course assignments).
- **Index store** — loads postings lists from GCS *on demand* (lazy loading) to save RAM.
- **Metadata store** — loads metadata into RAM for fast access (titles, lengths, corpus stats, PageRank, etc.).
- **Evaluator** — computes BM25; optionally combines BM25 with PageRank using a weighted formula.  
  Includes an optional threaded BM25 computation using `ThreadPoolExecutor`.

---

## Running the server

### Local quick run (Mini / Full)
The server is a Flask app in `app/<mini|full>/search_frontend.py`.

Typical run (example):
```bash
python -u app/full/search_frontend.py
```

> The server expects environment variables (bucket + prefixes + cache path). See `deployment/bootstrap_instance/app.env` for the required keys.

---

## Deployment on GCP

### 1) Create the VM (one-time)
See:
- `deployment/create_instance/README_create_instance.md`

This explains:
- what to fill in `run_frontend_in_gcp.sh` and `startup_script_gcp.sh`
- how to create a VM with a public IP and open port `8080`

### 2) Bootstrap the VM
See:
- `deployment/bootstrap_instance/README_boostrap.md`
- `deployment/bootstrap_instance/BOOTSTRAP_INSTANCE_STEPS.txt`

You will:
1. Upload the required files to the VM (app + env + service).
2. Create a venv on the VM.
3. Run `prepare_frontend_cache.py` to build local caches.
4. Install and start `ir-search.service` (systemd).

After that, the server stays up even if you disconnect SSH:
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

Outputs (examples):
- `per_query_quality.csv`
- `summary_quality.csv`
- `quality_versions.png`

Metrics:
- **P@5**, **P@10**, **F1@30**
- **HM** = harmonic mean(P@5, F1@30) — used as the main “quality score”.

See:
- `evaluation/performance/README_evaluate.txt`

### Runtime / latency benchmarks
Folder:
- `evaluation/runtime/`

Local benchmark (Mini/Full comparisons):
- `evaluation/runtime/local/benchmark_local.py`
- config example: `bench_config_local_example.json`

GCP VM benchmark (SSH):
- `evaluation/runtime/GCP/bench_ssh_simple.py`
- `evaluation/runtime/GCP/README_bench_ssh.txt`

---

## Configuration (what you must fill)

### Environment file (`app.env`)
Used by the VM service (and can be used locally too). Typical keys:
- `BUCKET_NAME`
- `POSTINGS_PREFIX`
- `METADATA_PREFIX`
- `CACHE_DIR`
- `GCP_PROJECT_ID` (only if your code uses it explicitly)

### systemd service (`ir-search.service`)
Must match your VM user and paths:
- `User=...`
- `WorkingDirectory=...`
- `EnvironmentFile=...`
- `ExecStartPre=...`
- `ExecStart=...`

---

## Notes / known behavior
- **Threaded BM25** can be faster locally but not always faster on the GCP VM due to threading overhead vs. low in-region GCS latency.
- PageRank integration improved quality slightly on some queries in our experiments.

---

## Authors
- Noam Yehoshua
- Bar Elhayani
