from dotenv import load_dotenv, find_dotenv
from imagekitio import ImageKit
from imagekitio.types.file import File
from loguru import logger
from typing import Optional, List, Generator, Set
import geopandas as gpd
import os
import pandas as pd

load_dotenv(find_dotenv())

# https://github.com/imagekit-developer/imagekit-python#file-upload


def imagekit_transform(
        bhhs_mls_photo_url: Optional[str],
        mls: str,
        imagekit_instance: ImageKit,
        folder: Optional[str] = None,
    ) -> Optional[str]:
    """Upload a listing photo and return its 400-by-300 delivery URL.

    Use the MLS number as a stable filename so retrying an upload replaces the
    same asset. A missing source URL or failed ImageKit operation leaves the
    listing without a new delivery URL.

    Args:
        bhhs_mls_photo_url: URL for the bhhs MLS photo.
        mls: MLS identifier for the listing.
        imagekit_instance: Configured ImageKit client used for image operations.
        folder: ImageKit destination folder for the listing image.

    Returns:
        The transformed ImageKit URL, or ``None`` if processing fails.
    """
    if pd.isna(bhhs_mls_photo_url):
        logger.info(f"No image URL found on BHHS for {mls}. Not uploading anything to ImageKit.")
        return None

    try:
        uploaded_image = imagekit_instance.files.upload(
            # A multipart field without a filename tells ImageKit to fetch the source URL.
            file=(None, bhhs_mls_photo_url.encode("utf-8")),
            file_name=mls,
            folder=folder or "/",
            is_private_file=False,
            use_unique_file_name=False,
            overwrite_file=True,
        ).url
    except Exception as e:
        logger.warning(f"Couldn't upload image to ImageKit because {e}.")
        return None

    if not uploaded_image:
        return None

    try:
        transformed_image = imagekit_instance.helper.build_url(
            src=uploaded_image,
            transformation=[{"height": 300, "width": 400}],
        )
    except Exception as e:
        logger.warning(f"Couldn't transform image because {e}.")
        return None

    logger.debug(f"ImageKit transformation generated for MLS {mls}.")
    return transformed_image

def chunked_list(lst: List, chunk_size: int) -> Generator[List, None, None]:
    """Yields successive n-sized chunks from lst.

Bounded groups keep remote image operations within service request limits.

    Parameters:
    lst (List): The list to be chunked.
    chunk_size (int): The maximum size of each chunk.

    Yields:
    List: A chunk of the original list of up to chunk_size elements.
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def reclaim_imagekit_space(geojson_path: str, imagekit_instance: ImageKit) -> None:
    """Delete ImageKit files absent from the active listing GeoJSON.

    Use the GeoJSON's MLS numbers as the keep set for files in the returned
    asset page. The input must represent the intended active listings because
    this operation removes remote assets.

    Parameters:
    geojson_path (str): The path to the GeoJSON file.
    imagekit_instance (ImageKit): An instance of ImageKit initialized with the appropriate credentials.

    Returns:
    None
    """
    # Load the GeoJSON file
    gdf = gpd.read_file(geojson_path)

    list_files = imagekit_instance.assets.list()

    # Create a set of referenced mls numbers for faster searching
    referenced_mls_numbers: Set[str] = set(
        gdf["mls_number"].dropna().astype("string")
    )

    # Initialize a list for file IDs to delete
    file_ids_for_deletion: List[str] = [
        file.file_id for file in list_files
        if isinstance(file, File) and file.file_id and file.name
        and os.path.splitext(file.name)[0] not in referenced_mls_numbers
    ]

    # Function to handle bulk deletion in chunks
    def delete_in_chunks(file_ids: List[str], imagekit_instance: ImageKit) -> None:
        """Submit bulk deletes in batches accepted by ImageKit.

        Each API call accepts at most 100 IDs and can return without deleting
        any of them, so log that outcome for the corresponding batch.

        Args:
            file_ids: ImageKit file identifiers to delete in one or more batches.
            imagekit_instance: Configured ImageKit client used for image operations.

        Returns:
            None.
        """
        for i in range(0, len(file_ids), 100):
            chunk = file_ids[i:i + 100]
            bulk_delete_result = imagekit_instance.files.bulk.delete(file_ids=chunk)

            if not bulk_delete_result.successfully_deleted_file_ids:
                logger.error(f"No files were deleted in the batch of {len(chunk)} ImageKit IDs.")

    # Call the function to delete files in chunks
    delete_in_chunks(file_ids_for_deletion, imagekit_instance)

    # Log the total number of files requested for deletion
    logger.info(f"Total number of files requested for deletion: {len(file_ids_for_deletion)}")

def delete_single_mls_image(mls_number: str) -> None:
    """Delete ImageKit files whose names start with the given MLS number.

    Check the returned asset page and skip directory entries, which have no
    file ID for the bulk delete API.

    Parameters:
    mls_number (str): The MLS number associated with the images.

    Returns:
    None
    """
    try:
        with ImageKit() as imagekit_instance:
            files_to_delete = [
                file.file_id for file in imagekit_instance.assets.list()
                if isinstance(file, File) and file.file_id and file.name
                and file.name.startswith(mls_number)
            ]

            if files_to_delete:
                bulk_delete_result = imagekit_instance.files.bulk.delete(file_ids=files_to_delete)
                if bulk_delete_result.successfully_deleted_file_ids:
                    logger.info(f"Deleted images for MLS {mls_number}.")
                else:
                    logger.error(f"Failed to delete images for MLS {mls_number}.")
            else:
                logger.info(f"No images found for MLS {mls_number}.")
    except Exception as e:
        logger.error(f"Error deleting images for MLS {mls_number}: {e}")
