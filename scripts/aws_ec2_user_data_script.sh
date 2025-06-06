#!/usr/bin/env bash
set -euo pipefail

TIMESTAMP=$(date +%Y%m%d-%H%M%S)
SAMPLE_SIZE=10
BASE_DIR=/home/ubuntu/larentals
DB_PATH=$BASE_DIR/assets/datasets/larentals.db
S3_URI=s3://wheretolivedotla-geojsonstorage/larentals.db

cd "$BASE_DIR"

# install CloudWatch agent
sudo yum install -y amazon-cloudwatch-agent

# apply the CloudWatch config
sudo /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -c file:$BASE_DIR/scripts/cloudwatch.json \
  -s

run_pipeline() {
  local mode=$1    # "sample" or "full"
  local args=$2    # "--sample N" or ""

  echo "[$mode] starting lease pipeline $args"
  uv run python lease_dataframe.py $args >> /var/log/lease_dataframe.log 2>&1 & pid_lease=$!

  echo "[$mode] starting buy pipeline $args"
  uv run python buy_dataframe.py   $args >> /var/log/buy_dataframe.log   2>&1 & pid_buy=$!

  wait $pid_lease; code_lease=$?
  wait $pid_buy;   code_buy=$?

  echo "[$mode] lease exit code: $code_lease" >> /var/log/lease_dataframe.log
  echo "[$mode] buy   exit code: $code_buy"   >> /var/log/buy_dataframe.log

  if (( code_lease != 0 || code_buy != 0 )); then
    echo "[$mode] pipelines failed; aborting." >> /var/log/lease_dataframe.log
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
  echo "[full] pipelines succeeded; uploading DB to S3" >> /var/log/lease_dataframe.log
  aws s3 cp "$DB_PATH" "$S3_URI"
else
  exit 1
fi

shutdown -h now