#!/bin/bash
set -e

# 1) Update & install OS packages
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-pip git curl unzip awscli

# 2) Install uv via pip (system-wide)
python3 -m pip install --upgrade pip
python3 -m pip install --no-cache-dir uv

# 3) Install the CloudWatch Agent
curl -sS -o /tmp/amazon-cloudwatch-agent.deb \
  https://s3.amazonaws.com/amazoncloudwatch-agent/ubuntu/amd64/latest/amazon-cloudwatch-agent.deb
dpkg -i /tmp/amazon-cloudwatch-agent.deb || apt-get install -fy

# 4) Clone only the 'aws' branch
cd /home/ubuntu
git clone --branch aws --single-branch \
  https://github.com/perfectly-preserved-pie/larentals.git larentals
cd larentals

# 5) Install requirements system-wide
uv pip install --system --no-cache-dir -r requirements.txt

# 6) Configure the CloudWatch Agent to tail the log file
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

# 7) Enable & start the CloudWatch Agent
systemctl enable amazon-cloudwatch-agent
systemctl start amazon-cloudwatch-agent

# 8) Run dataframe script
uv run python lease_dataframe.py

# 9) If anything fails, check cloud-init logs:
#    sudo cat /var/log/cloud-init-output.log | less