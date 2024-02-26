from imagekitio import ImageKit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from loguru import logger
from typing import Optional, List, Generator
import pandas as pd
import sys

# https://github.com/imagekit-developer/imagekit-python#file-upload

# Initialize logging
logger.add(sys.stderr, format="{time} {level} {message}", filter="my_module", level="INFO")

def imagekit_transform(
        bhhs_mls_photo_url: Optional[str], 
        mls: str, 
        imagekit_instance: ImageKit
    ) -> Optional[str]:
    """
    Uploads and transforms an image using ImageKit.
    """
    # Initialize variables
    uploaded_image: Optional[str] = None
    transformed_image: Optional[str] = None
    
    # Set up upload options
    options = UploadFileRequestOptions(
        is_private_file=False,
        use_unique_file_name=False,
        #folder = 'wheretolivedotla'
    )
    
    # Check if a photo URL is available
    if pd.notnull(bhhs_mls_photo_url):
        try:
            uploaded_image = imagekit_instance.upload_file(
                file=bhhs_mls_photo_url,
                file_name=mls,
                options=options
            ).url
        except Exception as e:
            logger.warning(f"Couldn't upload image to ImageKit because {e}.")
            return None  # Return early if upload fails
    else:
        logger.info(f"No image URL found on BHHS for {mls}. Not uploading anything to ImageKit.")
        return None  # Return early if no image URL
    
    # Transform the uploaded image if it exists
    if uploaded_image:
        try:
            transformed_image = imagekit_instance.url({
                "src": uploaded_image,
                "transformation": [{
                    "height": "300",
                    "width": "400"
                }]
            })
            logger.success(f"Transformed photo {transformed_image} generated for {mls}.")  # Log success only if transform succeeds
        except Exception as e:
            logger.warning(f"Couldn't transform image because {e}.")
            return None  # Return early if transform fails
    
    return transformed_image

def chunked_list(lst: List, chunk_size: int) -> Generator[List, None, None]:
    """
    Yields successive n-sized chunks from lst.

    Parameters:
    lst (List): The list to be chunked.
    chunk_size (int): The maximum size of each chunk.

    Yields:
    List: A chunk of the original list of up to chunk_size elements.
    """
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]

def reclaim_imagekit_space(df_path: str, imagekit_instance: ImageKit) -> None:
    """
    This function reclaims space in ImageKit by bulk deleting images that are not referenced in the dataframe,
    taking into account the limitation on the number of file IDs per request.

    Parameters:
    df_path (str): The path to the dataframe stored in a parquet file.
    imagekit_instance (ImageKit): An instance of ImageKit initialized with the appropriate credentials.

    Returns:
    None
    """
    # Load the dataframe
    df = pd.read_parquet(df_path)

    # Get the list of files
    list_files = imagekit_instance.list_files()

    # Collect file IDs for deletion
    file_ids_for_deletion = [file.file_id for file in list_files.list if file.name.replace('.jpg', '') not in df['mls_number'].values]

    # Split file IDs into chunks of 100 or fewer
    file_id_chunks = list(chunked_list(file_ids_for_deletion, 100))

    # Initialize a counter for deleted files
    deleted_files_count = 0

    # Iterate over each chunk and perform bulk deletion
    for chunk in file_id_chunks:
        try:
            bulk_delete_result = imagekit_instance.bulk_file_delete(file_ids=chunk)
            deleted_files_count += len(bulk_delete_result.successfully_deleted_file_ids)
            # Log each chunk's deletion result
            logger.success(f"Successfully deleted {len(bulk_delete_result.successfully_deleted_file_ids)} files in this chunk.")
        except Exception as e:
            logger.error(f"Error during bulk file deletion: {e}")

    # Log the total number of deleted files
    logger.info(f"Total number of deleted files: {deleted_files_count}")