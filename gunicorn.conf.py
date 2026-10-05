"""Emit Gunicorn warnings and errors without routine request or lifecycle noise."""

from functions.logging_config import get_log_level

loglevel = "warning"
accesslog = None
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
    "root": {"level": get_log_level(), "handlers": ["console"]},
    "loggers": {
        "gunicorn.error": {
            "level": loglevel.upper(), "handlers": ["console"], "propagate": False,
        },
        "gunicorn.access": {
            "level": loglevel.upper(), "handlers": ["console"], "propagate": False,
        },
    },
}
