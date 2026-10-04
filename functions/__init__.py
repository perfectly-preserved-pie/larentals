from functions.logging_config import configure_logging

# Every app, pipeline, and maintenance script imports this package. Configure
# once here so standalone commands also emit the container's JSON log format.
configure_logging()
