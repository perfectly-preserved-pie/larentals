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

# Run pipelines in parallel
uv run python -m pipelines.lease_dataframe ||  uv run python -m pipelines.buy_dataframe

shutdown -h now