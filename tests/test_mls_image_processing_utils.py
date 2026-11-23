"""Exercise the ImageKit SDK request used by listing photo enrichment."""

import json
from email import policy
from email.parser import BytesParser
from urllib.parse import parse_qs, urlsplit

import httpx
import pandas as pd
import pytest
from imagekitio import ImageKit

from functions.mls_image_processing_utils import imagekit_transform, reclaim_imagekit_space


def test_upload_sends_source_url_as_a_multipart_field() -> None:
    """Check the real SDK serialization without uploading to ImageKit.

    A filename on the source URL field would make ImageKit treat the URL
    itself as file contents.

    Returns:
        None.
    """
    source_url = "https://example.test/listing.jpg"
    delivery_url = "https://ik.imagekit.io/account/listings/buy/MLS123"
    requests: list[httpx.Request] = []

    def upload(request: httpx.Request) -> httpx.Response:
        """Record the upload so its multipart fields can be checked.

        Args:
            request: Upload produced by the ImageKit SDK.

        Returns:
            An upload response with an untransformed delivery URL.
        """
        requests.append(request)
        return httpx.Response(200, json={"url": delivery_url})

    with ImageKit(
        private_key="test",
        http_client=httpx.Client(transport=httpx.MockTransport(upload)),
    ) as client:
        transformed_url = imagekit_transform(source_url, "MLS123", client, "/listings/buy")

    request, = requests
    assert request.method == "POST"
    assert request.url.path == "/api/v1/files/upload"
    content_type = request.headers["content-type"].encode()
    message = BytesParser(policy=policy.default).parsebytes(
        b"Content-Type: " + content_type + b"\r\n\r\n" + request.read()
    )
    fields = {
        part.get_param("name", header="content-disposition"): (part.get_filename(), part.get_payload())
        for part in message.iter_parts()
    }
    assert fields == {
        "file": (None, source_url),
        "fileName": (None, "MLS123"),
        "folder": (None, "/listings/buy"),
        "isPrivateFile": (None, "false"),
        "overwriteFile": (None, "true"),
        "useUniqueFileName": (None, "false"),
    }
    assert transformed_url is not None
    assert transformed_url.split("?", 1)[0] == delivery_url
    assert parse_qs(urlsplit(transformed_url).query) == {"tr": ["h-300,w-400"]}


def test_reclaim_deletes_only_unreferenced_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep active images and folders out of the new SDK's bulk delete call.

    ImageKit 5 returns file and folder entries in the same asset response.

    Args:
        monkeypatch: Supplies the local set of active listings without a GeoJSON file.

    Returns:
        None.
    """
    monkeypatch.setattr(
        "functions.mls_image_processing_utils.gpd.read_file",
        lambda path: pd.DataFrame({"mls_number": ["active"]}),
    )
    requests: list[httpx.Request] = []

    def media_library(request: httpx.Request) -> httpx.Response:
        """Record library requests and serve a mixed asset page.

        Args:
            request: Asset list or bulk delete request produced by the SDK.

        Returns:
            The mock asset page or confirmation of the expected deletion.
        """
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=[
                {"type": "file", "fileId": "keep-id", "name": "active.jpg"},
                {"type": "folder", "folderId": "folder-id", "name": "other"},
                {"type": "file", "fileId": "delete-id", "name": "expired.jpg"},
            ])
        return httpx.Response(200, json={"successfullyDeletedFileIds": ["delete-id"]})

    with ImageKit(
        private_key="test",
        http_client=httpx.Client(transport=httpx.MockTransport(media_library)),
    ) as client:
        reclaim_imagekit_space("active.geojson", client)

    asset_list, delete = requests
    assert (asset_list.method, asset_list.url.path) == ("GET", "/v1/files")
    assert (delete.method, delete.url.path) == ("POST", "/v1/files/batch/deleteByFileIds")
    assert json.loads(delete.read()) == {"fileIds": ["delete-id"]}
