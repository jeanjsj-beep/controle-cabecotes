from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session
import os
import sys
import base64
import uuid
import re
import json
import traceback

app = FastAPI(
    title="Sistema de Controle de Recondicionamento de Cabeçotes (SCRC)",
    description="Backend para gerenciamento do fluxo fabril de cabeçotes de motor.",
    version="2.0.0"
)

# Garantir que o pacote 'app' funcione em qualquer Root Directory da Vercel ('./', 'backend' ou 'backend/app')
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PARENT_DIR = os.path.dirname(_THIS_DIR)
if _PARENT_DIR not in sys.path:
    sys.path.insert(0, _PARENT_DIR)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

try:
    import app as _app_pkg  # noqa: F401
except ImportError:
    import types
    _app_pkg = types.ModuleType("app")
    _app_pkg.__path__ = [_THIS_DIR]
    _app_pkg.__package__ = "app"
    sys.modules["app"] = _app_pkg

_BOOT_ERROR = None
_DB_INITIALIZED = False

try:
    from app.database import engine, Base, get_db, check_and_migrate_db, SessionLocal, IS_SQLITE
    from app import models, schemas
    from app.routers import lotes, cabecotes, etapas, dashboard, clientes, auth
    from app.routers.etapas import construir_e_salvar_relatorio
    from app.routers.auth import obter_usuario_atual, requer_admin, garantir_admin_padrao, gerar_hash_senha
except Exception:
    _BOOT_ERROR = traceback.format_exc()
    IS_SQLITE = False
    def get_db(): yield None
    def obter_usuario_atual(): return None
    def requer_admin(): return None
    class _Dummy:
        FotoUploadInput = dict
        Usuario = object
    schemas = _Dummy()
    models = _Dummy()

def init_db_safe():
    global _DB_INITIALIZED
    if _DB_INITIALIZED or _BOOT_ERROR:
        return
    try:
        Base.metadata.create_all(bind=engine)
        check_and_migrate_db()
        with SessionLocal() as _init_db:
            garantir_admin_padrao(_init_db)
        _DB_INITIALIZED = True
    except Exception as e:
        print(f"Aviso na inicialização do banco: {e}")

if not _BOOT_ERROR and IS_SQLITE:
    init_db_safe()

# Middleware de Cabeçalhos de Segurança HTTP
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "same-origin"
    return response

# Configuração de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Registrar Routers
if not _BOOT_ERROR:
    app.include_router(auth.router)
    app.include_router(clientes.router)
    app.include_router(lotes.router)
    app.include_router(cabecotes.router)
    app.include_router(etapas.router)
    app.include_router(dashboard.router)

# Diretórios de Frontend e Uploads (compatível com Root Directory './', 'backend' ou 'backend/app' na Vercel)
_CANDIDATE_FRONTENDS = [
    os.path.abspath(os.path.join(os.path.dirname(__file__), "frontend")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend")),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend")),
]
FRONTEND_DIR = next((p for p in _CANDIDATE_FRONTENDS if os.path.exists(p)), _CANDIDATE_FRONTENDS[-1])

UPLOADS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "uploads"))
try:
    os.makedirs(UPLOADS_DIR, exist_ok=True)
except Exception:
    pass


@app.get("/api/health")
def health_check():
    init_db_safe()
    return {
        "status": "error" if _BOOT_ERROR else "ok",
        "boot_error": _BOOT_ERROR,
        "frontend_dir_exists": os.path.exists(FRONTEND_DIR),
        "db_initialized": _DB_INITIALIZED
    }


@app.post("/api/upload")
def upload_foto(
    payload: schemas.FotoUploadInput,
    _: models.Usuario = Depends(obter_usuario_atual),
    db: Session = Depends(get_db)
):
    """Recebe uma imagem em Base64 validada, salva no Banco de Dados (para Vercel/Supabase)
    e opcionalmente em disco local, retornando a URL pública."""
    try:
        raw_b64 = payload.content_base64
        ext = "jpg"
        mime_type = "image/jpeg"
        if "," in raw_b64:
            header, raw_b64 = raw_b64.split(",", 1)
            if "png" in header:
                ext = "png"
                mime_type = "image/png"
            elif "webp" in header:
                ext = "webp"
                mime_type = "image/webp"
            elif "gif" in header:
                ext = "gif"
                mime_type = "image/gif"
        else:
            orig_ext = os.path.splitext(payload.filename)[1].lower().replace(".", "")
            if orig_ext in ["png", "jpg", "jpeg", "webp", "gif"]:
                ext = orig_ext
                mime_type = f"image/{'jpeg' if ext == 'jpg' else ext}"

        file_bytes = base64.b64decode(raw_b64)

        # Limite de segurança: máximo 10 MB por foto
        if len(file_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Arquivo excede o tamanho máximo permitido de 10 MB.")

        # Validação de assinatura binária (Magic Bytes) para garantir que é uma imagem legítima
        is_valid_image = (
            file_bytes.startswith(b"\xff\xd8\xff") or
            file_bytes.startswith(b"\x89PNG\r\n\x1a\n") or
            file_bytes.startswith(b"GIF87a") or
            file_bytes.startswith(b"GIF89a") or
            (file_bytes.startswith(b"RIFF") and b"WEBP" in file_bytes[:16])
        )
        if not is_valid_image:
            raise HTTPException(status_code=400, detail="Arquivo inválido: apenas imagens reais (JPG, PNG, WEBP, GIF) são permitidas.")

        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "", os.path.splitext(payload.filename)[0])[:24] or "foto"
        unique_filename = f"{safe_name}_{uuid.uuid4().hex[:8]}.{ext}"

        # 1. Persistir no Banco de Dados (compatível com Vercel Serverless + Supabase/Neon)
        nova_foto = models.FotoArmazenada(
            filename=unique_filename,
            mime_type=mime_type,
            content_base64=raw_b64
        )
        db.add(nova_foto)
        db.commit()

        # 2. Tentar salvar cópia em disco local se o ambiente permitir escrita
        try:
            file_path = os.path.join(UPLOADS_DIR, unique_filename)
            with open(file_path, "wb") as f:
                f.write(file_bytes)
        except Exception:
            pass

        return {"url": f"/uploads/{unique_filename}", "filename": unique_filename}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Falha ao salvar imagem: {str(e)}")


@app.get("/uploads/{filename}")
def get_uploaded_file(filename: str, db: Session = Depends(get_db)):
    safe_file = os.path.basename(filename)

    # 1. Buscar no Banco de Dados (funciona na Vercel e localmente)
    foto_db = db.query(models.FotoArmazenada).filter(models.FotoArmazenada.filename == safe_file).first()
    if foto_db:
        img_bytes = base64.b64decode(foto_db.content_base64)
        return Response(
            content=img_bytes,
            media_type=foto_db.mime_type or "image/jpeg",
            headers={"Cache-Control": "public, max-age=31536000"}
        )

    # 2. Fallback para arquivo em disco local
    file_path = os.path.join(UPLOADS_DIR, safe_file)
    if os.path.exists(file_path):
        return FileResponse(file_path)

    raise HTTPException(status_code=404, detail="Imagem não encontrada.")


_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


@app.get("/")
def read_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path, headers=_NO_CACHE_HEADERS)
    return {"message": "SCRC API Online. Frontend index.html não localizado.", "docs": "/docs"}


@app.get("/style.css")
def read_style():
    style_path = os.path.join(FRONTEND_DIR, "style.css")
    if os.path.exists(style_path):
        return FileResponse(style_path, media_type="text/css", headers=_NO_CACHE_HEADERS)
    return {"error": "style.css não localizado."}


@app.get("/app.js")
def read_js():
    js_path = os.path.join(FRONTEND_DIR, "app.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript", headers=_NO_CACHE_HEADERS)
    return {"error": "app.js não localizado."}

