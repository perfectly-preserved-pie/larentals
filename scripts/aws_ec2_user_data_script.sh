#!/bin/bash

# Timestamp for logs (not used in filenames here, but could be useful)
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Configuration variables
SAMPLE_SIZE=30
BASE_DIR=/home/ubuntu/larentals
DB_PATH=$BASE_DIR/assets/datasets/larentals.db
S3_URI=s3://wheretolivedotla-geojsonstorage/larentals.db

# Log directories
SAMPLE_LOG_DIR=~/larentals/sample
FULL_LOG_DIR=~/larentals/full
mkdir -p "$SAMPLE_LOG_DIR" "$FULL_LOG_DIR"
chmod 777 "$SAMPLE_LOG_DIR" "$FULL_LOG_DIR" # fuck it lol

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

# Sample both in parallel
(
  uv run python -m pipelines.lease_dataframe \
    --sample 15 \
    --logfile "$SAMPLE_LOG_DIR/lease_sample.log" \
  && uv run python -m pipelines.lease_dataframe \
    --logfile "$FULL_LOG_DIR/lease_full.log"
) &

(
  uv run python -m pipelines.buy_dataframe \
    --sample 15 \
    --logfile "$SAMPLE_LOG_DIR/buy_sample.log" \
  && uv run python -m pipelines.buy_dataframe \
    --logfile "$FULL_LOG_DIR/buy_full.log"
) &

# Wait for both pipelines to finish before proceeding
wait
echo "Both lease+buy pipelines complete"

echo "----- UPLOAD DB -----"
aws s3 cp "$DB_PATH" "$S3_URI"

echo "All steps completed successfully."

shutdown -h now