import logging
import os
from logging.handlers import RotatingFileHandler

from waitress import serve

from app import BASE_DIR, app, init_db


def get_env_int(name, default):
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def configure_logging():
    instance_dir = os.path.join(BASE_DIR, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    log_path = os.path.join(instance_dir, "server.log")

    handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if not any(getattr(existing, "baseFilename", None) == handler.baseFilename for existing in root_logger.handlers):
        root_logger.addHandler(handler)

    for logger_name in ("waitress", app.logger.name):
        logging.getLogger(logger_name).setLevel(logging.INFO)


def main():
    configure_logging()
    host = os.getenv("TRINITY_HOST", "127.0.0.1")
    port = get_env_int("TRINITY_PORT", 5000)
    threads = max(1, get_env_int("TRINITY_THREADS", 4))

    with app.app_context():
        init_db()

    app.logger.info("Starting Trinity server on %s:%s with %s threads.", host, port, threads)
    serve(app, host=host, port=port, threads=threads)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.getLogger(__name__).exception("Trinity server failed to start.")
        raise
