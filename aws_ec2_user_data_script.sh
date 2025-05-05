#!/bin/bash
set -e

# 1) Install Python 3.11 (and venv/pip) on RPM- or DEB-based AMIs
if ! command -v python3.11 &>/dev/null; then
  # Amazon Linux / RHEL
  yum install -y python3.11 python3.11-venv python3.11-pip \
    || \
  # Ubuntu / Debian
  (apt-get update && DEBIAN_FRONTEND=noninteractive \
    apt-get install -y python3.11 python3.11-venv python3.11-pip)
fi

# 2) Point the `python3` and `pip3` symlinks at 3.11
alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1
alternatives --install /usr/bin/pip3   pip3   /usr/bin/pip3.11   1

# 3) Install uv under Python 3.11
pip3 install --upgrade pip
pip3 install uv

# 4) Clone only the 'aws' branch
cd /home/ec2-user
git clone --branch aws --single-branch https://github.com/perfectly-preserved-pie/larentals.git larentals
cd larentals

# 5) Create a Python 3.11 venv & install all deps
uv venv --python python3.11
uv pip install -r requirements.txt

# 6) Configure CloudWatch Agent to tail the log file
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

# 7) Start the CloudWatch Agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s

# 8) Run the script inside the Python 3.11 venv
uv run python lease_dataframe.py
