"""Check that MONGODB_URI in backend/.env reaches a cluster. Prints no secrets.

.venv/bin/python scripts/check_mongo.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.mongo import get_client, ping  # noqa: E402
from app.config.settings import get_settings  # noqa: E402
from app.schemas import DependencyStatus  # noqa: E402

status = ping()
print(f"mongodb: {status.value}")
if status is DependencyStatus.OK:
    client = get_client()
    print(f"server version: {client.server_info()['version']}")
    print(f"database: {get_settings().mongodb_database}")
sys.exit(0 if status is DependencyStatus.OK else 1)
