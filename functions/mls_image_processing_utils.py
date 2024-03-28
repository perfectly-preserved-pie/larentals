from imagekitio import ImageKit
from imagekitio.models.UploadFileRequestOptions import UploadFileRequestOptions
from loguru import logger
from typing import Optional, List, Generator, Set
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
    This function reclaims space in ImageKit by deleting images in bulk that are not referenced in the dataframe.

    Parameters:
    df_path (str): The path to the dataframe stored in a parquet file.
    imagekit_instance (ImageKit): An instance of ImageKit initialized with the appropriate credentials.

    Returns:
    None
    """
    # Load the dataframe
    df = pd.read_parquet(df_path)

    # Get the list of files
    list_files_response = imagekit_instance.list_files()
    list_files: list = list_files_response.list if hasattr(list_files_response, 'list') else []

    # Create a set of referenced mls numbers for faster searching
    referenced_mls_numbers: Set[str] = set(df['mls_number'].astype(str))

    # Initialize a list for file IDs to delete
    file_ids_for_deletion: List[str] = [
        file.file_id for file in list_files 
        if file.name.replace('.jpg', '') not in referenced_mls_numbers
    ]

    # Function to handle bulk deletion in chunks
    def delete_in_chunks(file_ids: List[str], imagekit_instance: ImageKit) -> None:
        """Deletes files in chunks of 100 to avoid overloading the API requests."""
        for i in range(0, len(file_ids), 100):
            chunk = file_ids[i:i + 100]
            bulk_delete_result = imagekit_instance.bulk_file_delete(file_ids=chunk)
            
            if bulk_delete_result.successfully_deleted_file_ids:
                logger.success(f"Successfully deleted files: {bulk_delete_result.successfully_deleted_file_ids}")
            else:
                # Since successfully_deleted_file_ids is None or empty, no files were deleted.
                logger.error("No files were deleted.")
                # Use the response_metadata to get more details about the request and response.
                if bulk_delete_result.response_metadata:
                    logger.debug(f"Response metadata: {bulk_delete_result.response_metadata.raw}")
                else:
                    logger.error("No response metadata available.")

    # Call the function to delete files in chunks
    delete_in_chunks(file_ids_for_deletion, imagekit_instance)

    # Log the total number of files requested for deletion
    logger.info(f"Total number of files requested for deletion: {len(file_ids_for_deletion)}")