"""Keep Gunicorn lifecycle and access events filterable alongside app logs."""

from functions.logging_config import get_log_level

loglevel = get_log_level().lower()
accesslog = "-"
errorlog = "-"
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {"()": "functions.logging_config.DozzleFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stderr",
            "formatter": "json",
        },
    },
    "root": {"level": loglevel.upper(), "handlers": ["console"]},
    "loggers": {
        "gunicorn.error": {
            "level": loglevel.upper(), "handlers": ["console"], "propagate": False,
        },
        "gunicorn.access": {
            "level": loglevel.upper(), "handlers": ["console"], "propagate": False,
        },
    },
}
