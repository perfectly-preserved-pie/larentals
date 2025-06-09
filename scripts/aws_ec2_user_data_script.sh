#!/bin/bash
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SAMPLE_SIZE=10
BASE_DIR=/home/ubuntu/larentals
DB_PATH=$BASE_DIR/assets/datasets/larentals.db
S3_URI=s3://wheretolivedotla-geojsonstorage/larentals.db

# Update & install OS packages (script runs as root, no sudo)
apt-get update -y
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-pip git curl unzip

export HOME=/home/ubuntu
cd $HOME

# Clone the repo
if [ ! -d "$BASE_DIR" ]; then
  git clone https://github.com/perfectly-preserved-pie/larentals.git larentals
fi

# Ensure ubuntu can access workspace and cache
chown -R ubuntu:ubuntu "$BASE_DIR"
mkdir -p /home/ubuntu/.cache/uv
chown -R ubuntu:ubuntu /home/ubuntu/.cache

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Add uv to PATH
source $HOME/.local/bin/env

# Create & activate venv, install deps
echo "Creating virtual environment in $BASE_DIR/.venv"
uv venv
source .venv/bin/activate
uv sync --project "$BASE_DIR/pyproject.toml"

cd "$BASE_DIR"

# Fix PYTHONPATH so `import functions` works
echo "Setting PYTHONPATH to $BASE_DIR"
export PYTHONPATH="$BASE_DIR:$PYTHONPATH"

# Set timezone (non-interactive)
timedatectl set-timezone America/Los_Angeles

# Install CloudWatch agent
echo "Installing CloudWatch agent..."
curl -sS -o /tmp/amazon-cloudwatch-agent.deb \
  https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
dpkg -i /tmp/amazon-cloudwatch-agent.deb || apt-get install -fy

# Apply CloudWatch config (ignore if already running)
echo "Applying CloudWatch config..."
 /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:$BASE_DIR/scripts/cloudwatch.json \
  -s

# Enable & restart agent
systemctl enable amazon-cloudwatch-agent
systemctl restart amazon-cloudwatch-agent

echo "Running pipelines..."
run_pipeline() {
  local mode=$1
  local args=${2:-}

  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [$mode] starting lease pipeline $args" \
    >> /var/log/lease_dataframe.log 2>&1
  rm -rf /home/ubuntu/.cache/uv
  uv run python -m pipelines.lease_dataframe $args \
    >> /var/log/lease_dataframe.log 2>&1 & pid_lease=$!

  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [$mode] starting buy pipeline $args" \
    >> /var/log/buy_dataframe.log 2>&1
  rm -rf /home/ubuntu/.cache/uv
  uv run python -m pipelines.buy_dataframe $args \
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

# 1) sample test
if ! run_pipeline "sample" "--sample $SAMPLE_SIZE"; then
  exit 1
fi

# 2) full run & S3 upload
if run_pipeline "full"; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S %Z')] [full] uploading DB to S3" \
    >> /var/log/lease_dataframe.log
  aws s3 cp "$DB_PATH" "$S3_URI"
else
  exit 1
fi

shutdown -h now