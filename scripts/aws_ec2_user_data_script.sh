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
BASE_DIR=/home/ec2-user/larentals
S3_BUCKET=wheretolivedotla-geojsonstorage
S3_KEY=larentals.db
CHECKPOINT_S3_PREFIX=checkpoints/listing-pipelines
BROADBAND_GEOPACKAGE_LAYER=ca_broadband_availability_aggregate

# Log directories
SAMPLE_LOG_DIR=$BASE_DIR/sample
FULL_LOG_DIR=$BASE_DIR/full
CHECKPOINT_DIR=$BASE_DIR/data/checkpoints

# Install packages omitted from the AL2023 minimal AMI. GDAL is provided by
# Supplementary Packages for Amazon Linux (SPAL) on current AL2023 releases.
dnf install -y git python3.13 spal-release
dnf install -y gdal310
dnf clean all

# Ensure HOME is set
export HOME=/home/ec2-user
cd "$HOME"

# Clone repo if missing
if [ ! -d "$BASE_DIR" ]; then
  git clone \
    --depth=1 \
    --single-branch \
    https://github.com/perfectly-preserved-pie/larentals.git \
    "$BASE_DIR"
else
  git -C "$BASE_DIR" pull --ff-only
fi

mkdir -p "$SAMPLE_LOG_DIR" "$FULL_LOG_DIR" "$CHECKPOINT_DIR"
chmod 777 "$SAMPLE_LOG_DIR" "$FULL_LOG_DIR" # fuck it lol

# Install uv (Astral)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
source "$HOME/.local/bin/env"

# Create & activate virtualenv, install dependencies
cd "$BASE_DIR"
echo "Creating virtual environment in $BASE_DIR/.venv"
uv venv --python /usr/bin/python3.13
source .venv/bin/activate
uv sync --frozen --project "$BASE_DIR/pyproject.toml"

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
STAGING_DIR="$(dirname "$DB_PATH")/listing-staging"
LEASE_STAGE_DB="$STAGING_DIR/lease.db"
BUY_STAGE_DB="$STAGING_DIR/buy.db"

# Set timezone
timedatectl set-timezone America/Los_Angeles

# Give each pipeline its own copy of the current database. They can then read,
# enrich, and write concurrently without contending for SQLite's single writer.
mkdir -p "$STAGING_DIR"
rm -f "$LEASE_STAGE_DB" "$BUY_STAGE_DB"
if [ -f "$DB_PATH" ]; then
  cp "$DB_PATH" "$LEASE_STAGE_DB"
  cp "$DB_PATH" "$BUY_STAGE_DB"
fi

# Run lease and buy concurrently against isolated staging databases.
(
  uv run lease-dataframe \
    --sample 15 \
    --logfile "$SAMPLE_LOG_DIR/lease_sample.log" \
    --db-path "$LEASE_STAGE_DB" \
    --checkpoint-path "$CHECKPOINT_DIR/lease.sqlite" \
    --checkpoint-s3-bucket "$S3_BUCKET" \
    --checkpoint-s3-key "$CHECKPOINT_S3_PREFIX/lease.sqlite" \
  && uv run lease-dataframe \
    --logfile "$FULL_LOG_DIR/lease_full.log" \
    --db-path "$LEASE_STAGE_DB" \
    --checkpoint-path "$CHECKPOINT_DIR/lease.sqlite" \
    --checkpoint-s3-bucket "$S3_BUCKET" \
    --checkpoint-s3-key "$CHECKPOINT_S3_PREFIX/lease.sqlite"
) &
lease_pid=$!

(
  uv run buy-dataframe \
    --sample 15 \
    --logfile "$SAMPLE_LOG_DIR/buy_sample.log" \
    --db-path "$BUY_STAGE_DB" \
    --checkpoint-path "$CHECKPOINT_DIR/buy.sqlite" \
    --checkpoint-s3-bucket "$S3_BUCKET" \
    --checkpoint-s3-key "$CHECKPOINT_S3_PREFIX/buy.sqlite" \
  && uv run buy-dataframe \
    --logfile "$FULL_LOG_DIR/buy_full.log" \
    --db-path "$BUY_STAGE_DB" \
    --checkpoint-path "$CHECKPOINT_DIR/buy.sqlite" \
    --checkpoint-s3-bucket "$S3_BUCKET" \
    --checkpoint-s3-key "$CHECKPOINT_S3_PREFIX/buy.sqlite"
) &
buy_pid=$!

# Publish only after both staged runs succeed. The publisher replaces the two
# listing tables in one SQLite transaction, so readers never see a half-run.
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
uv run publish-listing-tables \
  --db-path "$DB_PATH" \
  --buy-stage-path "$BUY_STAGE_DB" \
  --lease-stage-path "$LEASE_STAGE_DB"
echo "Both lease+buy pipelines complete"

echo "----- ENRICH SCHOOL DISTRICTS AND NEAREST SCHOOLS -----"
uv run enrich-schools \
  --db-path "$DB_PATH"

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
uv run python - "$DB_PATH" "$S3_BUCKET" "$S3_KEY" <<'PY'
import sys
from pathlib import Path

import boto3

db_path = Path(sys.argv[1])
bucket = sys.argv[2]
key = sys.argv[3]
local_size = db_path.stat().st_size

s3 = boto3.client("s3")
s3.upload_file(str(db_path), bucket, key)
remote_size = int(s3.head_object(Bucket=bucket, Key=key)["ContentLength"])

if local_size != remote_size:
    raise SystemExit(
        "Uploaded database size mismatch "
        f"(local={local_size}, remote={remote_size})."
    )

print(f"Verified s3://{bucket}/{key} ({remote_size} bytes).")
PY
