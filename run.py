import os
import sys

from waitress import serve

from dms_api import create_app


os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass


app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print(f"DMS API Server iniciado en http://0.0.0.0:{port}")
    serve(app, host="0.0.0.0", port=port, threads=8)
