from loguru import logger
from typing import NoReturn, Dict
import boto3
import sys

logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def load_ssm_parameters(
    path: str,
    region: str = "us-west-1",
    decrypt: bool = True
) -> Dict[str, str]:
    """
    Fetch all SSM parameters under `path` and return a dict mapping
    each parameter name (suffix) → its value.  SecureStrings are
    decrypted if `decrypt=True`.
    """
    client = boto3.client("ssm", region_name=region)
    paginator = client.get_paginator("get_parameters_by_path")
    params: Dict[str, str] = {}

    for page in paginator.paginate(
        Path=path,
        Recursive=True,
        WithDecryption=decrypt,
        PaginationConfig={"PageSize": 10},
    ):
        for p in page["Parameters"]:
            # strip prefix and leading slash to get e.g. "GOOGLE_API_KEY"
            key = p["Name"].removeprefix(path).lstrip("/")
            params[key.upper()] = p["Value"]

    return params

def upload_file_to_s3(
    local_path: str,
    bucket: str,
    key: str
) -> NoReturn:
    """
    Upload a local file to the specified S3 bucket.

    :param local_path: Path to the file on the local filesystem.
    :param bucket: Name of the S3 bucket.
    :param key:   Destination key name under which to store the file.
    """
    s3 = boto3.client("s3")
    s3.upload_file(local_path, bucket, key)
    logger.info(f"Uploaded {local_path} → s3://{bucket}/{key}")
