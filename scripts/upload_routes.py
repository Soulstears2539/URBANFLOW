import sys
import requests
from pathlib import Path

SERVER = "http://127.0.0.1:5052"

if len(sys.argv) < 2:
    print("Uso: python scripts/upload_routes.py <ruta_al_archivo> [reemplazar]")
    sys.exit(1)

file_path = Path(sys.argv[1])
if not file_path.exists():
    print(f"No existe: {file_path}")
    sys.exit(2)

reemplazar = len(sys.argv) > 2 and sys.argv[2].lower() in ("1", "true", "yes", "on")
url = f"{SERVER}/api/transport/matrix/import"
with file_path.open("rb") as fh:
    files = {"file": (file_path.name, fh)}
    data = {"reemplazar": "1" if reemplazar else "0"}
    print(f"Subiendo {file_path.name} -> {url} (reemplazar={reemplazar})")
    r = requests.post(url, files=files, data=data, timeout=120)

print(r.status_code)
try:
    print(r.json())
except Exception:
    print(r.text)
