from imagekitio import ImageKit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from loguru import logger
from typing import Optional
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

def reclaim_imagekit_space(df_path: str, imagekit_instance: ImageKit) -> None:
    """
    This function reclaims space in ImageKit by bulk deleting images that are not referenced in the dataframe.

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

    if file_ids_for_deletion:
        # Perform bulk file deletion
        bulk_delete_result = imagekit_instance.bulk_file_delete(file_ids=file_ids_for_deletion)

        # Log bulk deletion result
        logger.success(f"Successfully deleted file IDs: {bulk_delete_result.successfully_deleted_file_ids}")
        # If needed, log raw response and any additional details
        logger.debug(f"Raw Response: {bulk_delete_result.response_metadata.raw}")

        # Log the total number of deleted files
        logger.info(f"Total number of deleted files: {len(bulk_delete_result.successfully_deleted_file_ids)}")
    else:
        logger.info("No files need to be deleted.")