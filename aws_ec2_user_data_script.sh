#!/bin/bash
set -e

# 1) Install system deps: python3 (3.11), venv, pip, git, awscli, CloudWatch Agent
yum install -y python3 python3-venv python3-pip git awscli amazon-cloudwatch-agent

# 2) Install uv into the system Python
python3 -m pip install --upgrade pip
python3 -m pip install uv

# 3) Clone only the 'aws' branch
cd /home/ec2-user
git clone --branch aws --single-branch https://github.com/perfectly-preserved-pie/larentals.git larentals
cd larentals

# 4) Create a Python 3.11 venv & install requirements
uv venv --python python3
uv pip install -r requirements.txt

# 5) Configure CloudWatch Agent to tail log file
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

# 6) Enable & start the CloudWatch Agent
systemctl enable amazon-cloudwatch-agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s

# 7) Run the script inside the venv
uv run python lease_dataframe.py
