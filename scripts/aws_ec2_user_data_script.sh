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
  # pick a suffix for sample vs full
  local suffix=""
  if [[ $mode == "sample" ]]; then
    suffix="_sample"
  fi

  echo "[$(date)] [$mode] starting lease…" 
  uv run python -m pipelines.lease_dataframe \
    $args \
    --logfile /var/log/lease_dataframe${suffix}.log
  pid_lease=$!

  echo "[$(date)] [$mode] starting buy…" 
  uv run python -m pipelines.buy_dataframe \
    $args \
    --logfile /var/log/buy_dataframe${suffix}.log
  pid_buy=$!

  wait $pid_lease; code_lease=$?
  wait $pid_buy;   code_buy=$?

  echo "[$(date)] [$mode] lease exit: $code_lease"
  echo "[$(date)] [$mode] buy   exit: $code_buy"

  if (( code_lease != 0 || code_buy != 0 )); then
    echo "[$(date)] [$mode] pipelines failed."
    return 1
  fi
  return 0
}

# sample run logs to *_sample.log
run_pipeline "sample" "--sample $SAMPLE_SIZE" || exit 1

# full run logs back to the normal files
run_pipeline "full" ""  && aws s3 cp "$DB_PATH" "$S3_URI" || exit 1

shutdown -h now