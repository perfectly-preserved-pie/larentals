#!/bin/bash
set -e

# 1) Update & install OS packages
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-pip git curl unzip

export HOME=/home/ubuntu
cd $HOME

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create a venv and activate it
uv venv
source .venv/bin/activate

# Install the CloudWatch Agent
curl -sS -o /tmp/amazon-cloudwatch-agent.deb \
  https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
dpkg -i /tmp/amazon-cloudwatch-agent.deb || apt-get install -fy

# Install the AWS CLI
uv pip install --no-cache-dir \
  awscli

# Set the git config to use the best compression
# This is a workaround for the issue with the default git compression
git config --global core.compression 9 repack

# Clone only the 'aws' branch
cd /home/ubuntu
git clone --branch aws --single-branch \
  https://github.com/perfectly-preserved-pie/larentals.git larentals
cd larentals

# Install requirements 
uv pip install --no-cache-dir -r requirements.txt

# Configure the CloudWatch Agent to tail the log file
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<'EOF'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/lease_dataframe.log",
            "log_group_name": "LarentalsLeaseDF",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
EOF

# Enable & start the CloudWatch Agent
systemctl enable amazon-cloudwatch-agent
systemctl start amazon-cloudwatch-agent

# Run dataframe script
uv run python lease_dataframe.py

# If anything fails, check cloud-init logs:
#    sudo tail -f /var/log/cloud-init-output.log