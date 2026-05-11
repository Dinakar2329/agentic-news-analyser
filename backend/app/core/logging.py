import logging


class SecretFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage().lower()
        return "api_key" not in message and "authorization" not in message and "bearer " not in message


def configure_logging():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger().addFilter(SecretFilter())
