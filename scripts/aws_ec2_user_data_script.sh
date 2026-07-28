#!/bin/bash

set -Eeuo pipefail

shutdown_on_exit() {
  status=$?
  trap - EXIT

  if (( status == 0 )); then
    echo "All steps completed successfully."
  else
    echo "ERROR: bootstrap failed with exit code $status; database publication was not verified." >&2
  fi

  shutdown -h now || true
  exit "$status"
}

trap shutdown_on_exit EXIT

# Timestamp for logs (not used in filenames here, but could be useful)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Configuration variables
SAMPLE_SIZE=30
BASE_DIR=/home/ubuntu/larentals
S3_BUCKET=wheretolivedotla-geojsonstorage
S3_KEY=larentals.db
S3_URI=s3://$S3_BUCKET/$S3_KEY
BROADBAND_GEOPACKAGE_LAYER=ca_broadband_availability_aggregate

# Log directories
SAMPLE_LOG_DIR=$BASE_DIR/sample
FULL_LOG_DIR=$BASE_DIR/full

# Update & install OS packages (script runs as root)
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-pip git curl unzip gdal-bin

# Ensure HOME is set
export HOME=/home/ubuntu
cd "$HOME"

# Clone repo if missing
if [ ! -d "$BASE_DIR" ]; then
  git clone https://github.com/perfectly-preserved-pie/larentals.git larentals
else
  git -C "$BASE_DIR" pull --ff-only
fi

mkdir -p "$SAMPLE_LOG_DIR" "$FULL_LOG_DIR"
chmod 777 "$SAMPLE_LOG_DIR" "$FULL_LOG_DIR" # fuck it lol

# Install AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
./aws/install

# Install uv (Astral)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
source "$HOME/.local/bin/env"

# Create & activate virtualenv, install dependencies
cd "$BASE_DIR"
echo "Creating virtual environment in $BASE_DIR/.venv"
uv venv
source .venv/bin/activate
uv sync --project "$BASE_DIR/pyproject.toml"

# Fix PYTHONPATH so `import functions` works
echo "Setting PYTHONPATH to $BASE_DIR"
export PYTHONPATH="$BASE_DIR:${PYTHONPATH:-}"

# Resolve artifact paths from the checked-out code so user-data cannot drift
# from the paths used by the Python pipelines.
DB_PATH=$(uv run python -c \
  "from functions.data_paths import LARENTALS_DB_PATH; print(LARENTALS_DB_PATH)")
BROADBAND_GEOPACKAGE_PATH=$(uv run python -c \
  "from functions.data_paths import CA_BROADBAND_GEOPACKAGE_PATH; print(CA_BROADBAND_GEOPACKAGE_PATH)")
ALPR_CAMERAS_PATH=$(uv run python -c \
  "from functions.data_paths import ALPR_CAMERAS_PATH; print(ALPR_CAMERAS_PATH)")

# Set timezone
timedatectl set-timezone America/Los_Angeles

# Install CloudWatch agent
echo "Installing CloudWatch agent..."
curl -sS -o /tmp/amazon-cloudwatch-agent.deb \
     https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
dpkg -i /tmp/amazon-cloudwatch-agent.deb || apt-get install -fy

# Apply CloudWatch config
echo "Applying CloudWatch config..."
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:$BASE_DIR/scripts/cloudwatch.json \
  -s

# Enable & restart CloudWatch agent
systemctl enable amazon-cloudwatch-agent
systemctl restart amazon-cloudwatch-agent

# Sample both in parallel
(
  uv run lease-dataframe \
    --sample 15 \
    --logfile "$SAMPLE_LOG_DIR/lease_sample.log" \
  && uv run lease-dataframe \
    --logfile "$FULL_LOG_DIR/lease_full.log"
) &
lease_pid=$!

(
  uv run buy-dataframe \
    --sample 15 \
    --logfile "$SAMPLE_LOG_DIR/buy_sample.log" \
  && uv run buy-dataframe \
    --logfile "$FULL_LOG_DIR/buy_full.log"
) &
buy_pid=$!

# Wait for both pipelines to finish before proceeding
pipeline_status=0
wait "$lease_pid" || {
  echo "ERROR: lease pipeline failed." >&2
  pipeline_status=1
}
wait "$buy_pid" || {
  echo "ERROR: buy pipeline failed." >&2
  pipeline_status=1
}
if (( pipeline_status != 0 )); then
  exit "$pipeline_status"
fi
echo "Both lease+buy pipelines complete"

echo "----- FETCH CPUC BROADBAND GEOPACKAGE -----"
uv run fetch-cpuc-broadband-geopackage \
  --output "$BROADBAND_GEOPACKAGE_PATH" \
  --layer "$BROADBAND_GEOPACKAGE_LAYER"

echo "----- RUN BROADBAND MERGE -----"
uv run run-broadband-merge \
  --db-path "$DB_PATH" \
  --geopackage-path "$BROADBAND_GEOPACKAGE_PATH" \
  --geopackage-layer "$BROADBAND_GEOPACKAGE_LAYER"

echo "----- FETCH ALPR CAMERAS -----"
uv run fetch-alpr-cameras \
  --output "$ALPR_CAMERAS_PATH"

echo "----- VALIDATE DB -----"
uv run python - "$DB_PATH" <<'PY'
import sqlite3
import sys
from pathlib import Path

db_path = Path(sys.argv[1])
if not db_path.is_file() or db_path.stat().st_size == 0:
    raise SystemExit(f"Database does not exist or is empty: {db_path}")

with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as connection:
    integrity = connection.execute("PRAGMA quick_check").fetchone()
    if integrity != ("ok",):
        raise SystemExit(f"SQLite quick_check failed: {integrity}")

    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    missing = {"buy", "lease"} - tables
    if missing:
        raise SystemExit(f"Database is missing required tables: {sorted(missing)}")

    for table in ("buy", "lease"):
        row_count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        if row_count == 0:
            raise SystemExit(f"Database table is empty: {table}")
        print(f"Validated {table}: {row_count} rows")
PY

echo "----- UPLOAD DB -----"
aws s3 cp "$DB_PATH" "$S3_URI" --only-show-errors

local_size=$(stat -c %s "$DB_PATH")
remote_size=$(aws s3api head-object \
  --bucket "$S3_BUCKET" \
  --key "$S3_KEY" \
  --query ContentLength \
  --output text)
if [ "$local_size" != "$remote_size" ]; then
  echo "ERROR: uploaded database size mismatch (local=$local_size, remote=$remote_size)." >&2
  exit 1
fi
echo "Verified $S3_URI ($remote_size bytes)."
