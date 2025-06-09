#!/bin/bash
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SAMPLE_SIZE=10
BASE_DIR=/home/ubuntu/larentals
DB_PATH=$BASE_DIR/assets/datasets/larentals.db
S3_URI=s3://wheretolivedotla-geojsonstorage/larentals.db

# Install OS packages (runs as root)
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-pip git curl unzip

export HOME=/home/ubuntu
cd $HOME

# Clone the repo if needed
if [ ! -d "$BASE_DIR" ]; then
  git clone https://github.com/perfectly-preserved-pie/larentals.git larentals
fi

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Create & activate venv, install deps
uv venv
source .venv/bin/activate
uv sync --project "$BASE_DIR/pyproject.toml"

cd "$BASE_DIR"
export PYTHONPATH="$BASE_DIR:$PYTHONPATH"

# Set timezone
timedatectl set-timezone America/Los_Angeles

# Install CloudWatch agent
curl -sS -o /tmp/amazon-cloudwatch-agent.deb \
  https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
dpkg -i /tmp/amazon-cloudwatch-agent.deb || apt-get install -fy
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 -c file:$BASE_DIR/scripts/cloudwatch.json -s
systemctl enable amazon-cloudwatch-agent
systemctl restart amazon-cloudwatch-agent

run_pipeline() {
  local extra_args=$1

  echo "[$(date +'%Y-%m-%d %H:%M:%S')] running lease pipeline $extra_args"
  uv run python -m pipelines.lease_dataframe $extra_args \
     --logfile /var/log/lease_dataframe.log &
  pid_lease=$!

  echo "[$(date +'%Y-%m-%d %H:%M:%S')] running buy pipeline   $extra_args"
  uv run python -m pipelines.buy_dataframe   $extra_args \
     --logfile /var/log/buy_dataframe.log &
  pid_buy=$!

  wait $pid_lease; code_lease=$?
  wait $pid_buy;   code_buy=$?

  if (( code_lease != 0 || code_buy != 0 )); then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] pipeline failed (lease=$code_lease, buy=$code_buy)"
    return 1
  fi
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] pipeline succeeded"
  return 0
}

# 1) test on SAMPLE_SIZE rows
run_pipeline "--sample $SAMPLE_SIZE" || exit 1

# 2) full run and upload DB
run_pipeline "" && aws s3 cp "$DB_PATH" "$S3_URI" || exit 1

shutdown -h now