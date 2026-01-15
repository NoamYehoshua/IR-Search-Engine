# Bootstrap the VM (turn it into a running service)

This folder contains everything needed to **initialize an already-created GCP VM**
so it runs the search engine continuously via **systemd**.

## What you do here
1. Upload the python app files + config files to the VM.
2. Place everything under `~/ir_app/`.
3. Create a Python virtual environment under `~/venv/`.
4. Download/cache the index + metadata locally (`prepare_frontend_cache.py`).
5. Install a systemd service (`ir-search.service`) and start it.

## Files in this folder
- `BOOTSTRAP_INSTANCE_STEPS.txt`  
  A step-by-step command list to run on the VM.
- `app.env`  
  Environment variables (bucket/prefixes/cache path).
- `ir-search.service`  
  systemd service definition (runs cache-prep, then starts the Flask server).

## What you must fill (placeholders)
### app.env
Edit these keys before uploading:
- `BUCKET_NAME`
- `POSTINGS_PREFIX`
- `METADATA_PREFIX`
- `CACHE_DIR`
- `GCP_PROJECT_ID` (only if your code requires it)

### ir-search.service
Edit these fields to match your VM user and paths:
- `User=...`
- `WorkingDirectory=...`
- `EnvironmentFile=...`
- `ExecStartPre=...`
- `ExecStart=...`

## Troubleshooting (quick)
- If `systemctl status` shows env-related errors, run:
  `sed -i 's/\r$//' ~/ir_app/app.env`
- To view logs:
  `sudo journalctl -u ir-search.service -f`
