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