import json

from app.main import app
from tests.contracts.utils import SNAPSHOT_FILE, normalize_openapi

print(f"Updating snapshot at {SNAPSHOT_FILE}")
SNAPSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
schema = normalize_openapi(app.openapi())
SNAPSHOT_FILE.write_text(json.dumps(schema, indent=2))
print("Done.")
