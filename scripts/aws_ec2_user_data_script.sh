#!/bin/bash
set -euo pipefail

# Timestamp for logs (not used in filenames here, but could be useful)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Configuration variables
SAMPLE_SIZE=10
BASE_DIR=/home/ubuntu/larentals
DB_PATH=$BASE_DIR/assets/datasets/larentals.db
S3_URI=s3://wheretolivedotla-geojsonstorage/larentals.db

# Log directories
SAMPLE_LOG_DIR=/var/log/larentals/sample
FULL_LOG_DIR=/var/log/larentals/full
mkdir -p "$SAMPLE_LOG_DIR" "$FULL_LOG_DIR"

# Update & install OS packages (script runs as root)
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-pip git curl unzip

# Ensure HOME is set
export HOME=/home/ubuntu
cd "$HOME"

# Clone repo if missing
if [ ! -d "$BASE_DIR" ]; then
  git clone https://github.com/perfectly-preserved-pie/larentals.git larentals
fi

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
export PYTHONPATH="$BASE_DIR:$PYTHONPATH"

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

# Helper function to run both pipelines in parallel and check exit codes
run_parallel() {
  local mode=$1      # "sample" or "full"
  local args=$2      # flags like "--sample $SAMPLE_SIZE" or empty
  local outdir=$3    # log directory

  echo "===== [$mode] Starting lease and buy pipelines ($args) ====="

  # Lease pipeline
  uv run python -m pipelines.lease_dataframe \
    $args \
    --logfile "$outdir/lease_dataframe_${mode}.log" &
  pid_lease=$!

  # Buy pipeline
  uv run python -m pipelines.buy_dataframe \
    $args \
    --logfile "$outdir/buy_dataframe_${mode}.log" &
  pid_buy=$!

  echo "[$mode] Waiting on PIDs: lease=$pid_lease, buy=$pid_buy"
  wait "$pid_lease"; code_lease=$?
  wait "$pid_buy";   code_buy=$?

  echo "[$mode] lease exit: $code_lease; buy exit: $code_buy"
  if (( code_lease != 0 || code_buy != 0 )); then
    echo "[$mode] One or both pipelines failed (exit codes $code_lease, $code_buy); exiting."
    exit 1
  fi

  echo "[$mode] Both pipelines succeeded."
}

echo "----- SAMPLE RUN -----"
run_parallel "sample" "--sample $SAMPLE_SIZE" "$SAMPLE_LOG_DIR"

echo "----- FULL RUN -----"
run_parallel "full" "" "$FULL_LOG_DIR"

echo "----- UPLOAD DB -----"
aws s3 cp "$DB_PATH" "$S3_URI"

echo "All steps completed successfully."

shutdown -h now
