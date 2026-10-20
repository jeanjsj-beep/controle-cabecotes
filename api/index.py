import os
import sys
import traceback

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")
APP_DIR = os.path.join(BACKEND_DIR, "app")
for p in (BASE_DIR, BACKEND_DIR, APP_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from backend.app.main import app
except Exception:
    try:
        from app.main import app
    except Exception as e:
        from fastapi import FastAPI
        err_trace = traceback.format_exc()
        app = FastAPI()

        @app.get("/{full_path:path}")
        def diagnostic_fallback(full_path: str):
            return {
                "status": "boot_error",
                "error": str(e),
                "traceback": err_trace,
                "cwd": os.getcwd(),
                "sys_path": sys.path,
            }
