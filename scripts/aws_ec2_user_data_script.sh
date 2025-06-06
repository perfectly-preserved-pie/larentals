#!/usr/bin/env bash
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SAMPLE_SIZE=10
BASE_DIR=/home/ubuntu/larentals
DB_PATH=$BASE_DIR/assets/datasets/larentals.db
S3_URI=s3://wheretolivedotla-geojsonstorage/larentals.db

# Update & install OS packages
sudo apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-pip git curl unzip

export HOME=/home/ubuntu
cd $HOME

# Clone the repo
git clone https://github.com/perfectly-preserved-pie/larentals.git larentals

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# add the local bin to the PATH
source $HOME/.local/bin/env

# Create a venv and activate it
uv venv
source .venv/bin/activate

# Install requirements 
uv sync --project "$BASE_DIR/pyproject.toml"

cd "$BASE_DIR"

# ensure OS uses PST/PDT
sudo timedatectl set-timezone America/Los_Angeles

# install CloudWatch agent
curl -sS -o /tmp/amazon-cloudwatch-agent.deb \
  https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
dpkg -i /tmp/amazon-cloudwatch-agent.deb || apt-get install -fy

# apply the CloudWatch config
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:$BASE_DIR/scripts/cloudwatch.json \
  -s

run_pipeline() {
  local mode=$1    # "sample" or "full"
  local args=${2:-}

  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [$mode] starting lease pipeline $args" \
    >> /var/log/lease_dataframe.log 2>&1
  uv run python lease_dataframe.py $args \
    >> /var/log/lease_dataframe.log 2>&1 & pid_lease=$!

  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [$mode] starting buy pipeline $args" \
    >> /var/log/buy_dataframe.log 2>&1
  uv run python buy_dataframe.py $args \
    >> /var/log/buy_dataframe.log 2>&1 & pid_buy=$!

  wait $pid_lease; code_lease=$?
  wait $pid_buy;   code_buy=$?

  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [$mode] lease exit code: $code_lease" \
    >> /var/log/lease_dataframe.log
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [$mode] buy   exit code: $code_buy" \
    >> /var/log/buy_dataframe.log

  if (( code_lease != 0 || code_buy != 0 )); then
    echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [$mode] pipelines failed; aborting." \
      >> /var/log/lease_dataframe.log
    return 1
  fi
  return 0
}

# 1) sample test (runs both pipelines on SAMPLE_SIZE rows)
if ! run_pipeline "sample" "--sample $SAMPLE_SIZE"; then
  exit 1
fi

# 2) full run (process all rows and write to SQLite, then S3 upload)
if run_pipeline "full" ""; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [full] pipelines succeeded; uploading DB to S3" \
    >> /var/log/lease_dataframe.log
  aws s3 cp "$DB_PATH" "$S3_URI"
else
  exit 1
fi

shutdown -h now