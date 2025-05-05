from typing import Dict
import boto3

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
