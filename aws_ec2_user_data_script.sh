#!/bin/bash
set -e

# 1) Install system deps: python3, pip, git, awscli, CloudWatch Agent
yum install -y python3 python3-pip git awscli amazon-cloudwatch-agent \
  || (apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-pip git awscli amazon-cloudwatch-agent)

# 2) Install uv 
pip3 install uv

# 3) Clone only the 'aws' branch
cd /home/ec2-user
git clone --branch aws --single-branch https://github.com/perfectly-preserved-pie/larentals.git larentals
cd larentals

# 4) Create venv & install all Python deps via uv
uv pip install -r requirements.txt

# 5) Configure CloudWatch Agent to tail the loguru file
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

# 6) Start the CloudWatch Agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s

# 7) Run the Python script inside the uv venv
uv run python lease_dataframe.py
