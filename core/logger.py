import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler

from core.config_loader import config
from core.path_constants import LOGS_PATH, MAX_LOG_SIZE

LOGS_PATH.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = getattr(logging, config.logging.level)
LOG_FORMAT = logging.Formatter(config.logging.format)
LOG_FILE = f"{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"

log_file_path = LOGS_PATH / LOG_FILE

def configure_logger():
    """
    Function to configure logger so as to enable logging via console handler and file handler.
    """

    try:
        logging.info("Creating and setting up logger object")

        # initiate logger
        logger = logging.getLogger("VeriLearn")
        logger.setLevel(LOG_LEVEL)

        # remove existing handlers
        if logger.hasHandlers():
            logger.handlers.clear()

        # console loggers
        console_logger = logging.StreamHandler()
        console_logger.setLevel(LOG_LEVEL)

        # file logger
        file_logger = RotatingFileHandler(log_file_path, maxBytes=MAX_LOG_SIZE)
        file_logger.setLevel(LOG_LEVEL)

        # set formatters
        console_logger.setFormatter(LOG_FORMAT)
        file_logger.setFormatter(LOG_FORMAT)

        # add handlers
        logger.addHandler(console_logger)
        logger.addHandler(file_logger)

    except Exception as e:
        logging.error(f"Error while creating logger object : {e}")
        raise

configure_logger()