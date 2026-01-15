# Create GCP VM Instance (one-time setup)

This folder contains scripts to create a Google Compute Engine VM with a public IP
and install the Python environment needed to run our search frontend.

## Files
- `run_frontend_in_gcp.sh`  
  Creates a static external IP, opens firewall port 8080, creates the VM, and
  shows commands to SCP/SSH and run the server.
- `startup_script_gcp.sh`  
  Runs automatically on the VM at first boot. Installs Python + creates a venv
  under the VM user and installs required packages.

---

## Before you run (fill these placeholders)

### 1) Edit `run_frontend_in_gcp.sh`
Open the file and replace:
- `PROJECT_NAME="YOUR_PROJECT_NAME_HERE"`  -> your GCP project id
- `GOOGLE_ACCOUNT_NAME="YOUR_ACCOUNT_NAME_HERE"` -> your VM username (without the email domain)

Optional (you can keep defaults):
- `INSTANCE_NAME` (default: `instance-1`)
- `REGION`, `ZONE` (default: `us-central1`, `us-central1-c`)
- machine type (default: `e2-medium`)

### 2) Edit `startup_script_gcp.sh`
Replace:
- `APP_USER="YOUR_ACCOUNT_NAME_HERE"` -> SAME VM username as above (without the email domain)

---

## Run (from your local machine or Cloud Shell)
Make sure the Cloud SDK is installed and you are logged in:

```bash
gcloud auth list
gcloud config list
# If needed:
# gcloud config set project <YOUR_PROJECT_NAME>
# gcloud config set compute/zone <YOUR_ZONE>
```

Then run:
```bash
bash run_frontend_in_gcp.sh
```

The script will print the external IP. Save it (this is the URL you provide for the demo).

---

## After the VM is up (manual steps shown in the script)
From the same folder (or repo root), copy the app code to the VM and SSH:

```bash
gcloud compute scp ./search_frontend.py <USER>@<INSTANCE_NAME>:/home/<USER> --zone <ZONE>
gcloud compute ssh <USER>@<INSTANCE_NAME> --zone <ZONE>
```

Inside the VM, start the server (example):
```bash
nohup ~/venv/bin/python ~/search_frontend.py > ~/frontend.log 2>&1 &
```

---

## Cleanup (avoid charges)
When you are done, delete resources:
```bash
gcloud compute instances delete -q <INSTANCE_NAME>
gcloud compute firewall-rules delete -q default-allow-http-8080
gcloud compute addresses delete -q <PROJECT_NAME>-ip --region <REGION>
```
