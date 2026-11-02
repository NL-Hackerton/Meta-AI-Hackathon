"""Serve the review app on loopback. Live mode is still refused by load_config."""

import os
import tempfile

import uvicorn

from adloom.config import load_config
from adloom.web.app import LOOPBACK_HOSTS, create_app


def main() -> None:
    settings = load_config()
    host = os.environ.get("ADLOOM_HOST", "127.0.0.1")
    port = int(os.environ.get("ADLOOM_PORT", "8000"))
    # Multipart spools large uploads to tempfile; keep those bytes inside the data root.
    spool = settings.data_dir / "tmp"
    spool.mkdir(parents=True, exist_ok=True)
    tempfile.tempdir = str(spool)
    hosts = LOOPBACK_HOSTS if host in LOOPBACK_HOSTS else (*LOOPBACK_HOSTS, host)
    uvicorn.run(create_app(settings, hosts), host=host, port=port)


if __name__ == "__main__":
    main()
