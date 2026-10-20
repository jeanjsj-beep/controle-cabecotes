from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session
import datetime
import os
import sys
import base64
import uuid
import re
import json
import traceback

# Item 5: Desabilitar Swagger/Redoc públicos em produção (exceto se SCRC_ENABLE_DOCS=1)
_DOCS_ENABLED = os.getenv("SCRC_ENABLE_DOCS", "0") == "1"

app = FastAPI(
    title="Sistema de Controle de Recondicionamento de Cabeçotes (SCRC)",
    description="Backend seguro para gerenciamento do fluxo fabril de cabeçotes de motor.",
    version="3.0.0",
    docs_url="/docs" if _DOCS_ENABLED else None,
    redoc_url="/redoc" if _DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _DOCS_ENABLED else None,
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
    from app.routers.auth import (
        obter_usuario_atual,
        requer_admin,
        garantir_admin_padrao,
        gerar_hash_senha,
        aplicar_rls_postgresql,
        registrar_evento_seguranca,
    )
except Exception:
    _BOOT_ERROR = traceback.format_exc()
    IS_SQLITE = False
    def get_db(): yield None
    def obter_usuario_atual(): return None
    def requer_admin(): return None
    def aplicar_rls_postgresql(_db): return {}
    def registrar_evento_seguranca(*_args, **_kwargs): pass
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
            aplicar_rls_postgresql(_init_db)
        _DB_INITIALIZED = True
    except Exception as e:
        print(f"Aviso na inicialização do banco: {e}")


if not _BOOT_ERROR and IS_SQLITE:
    init_db_safe()

# --- ITEM 9: RATE LIMITING GLOBAL E DE UPLOAD POR IP ---
_GLOBAL_RATE_BUCKETS: dict[str, list[datetime.datetime]] = {}
_UPLOAD_RATE_BUCKETS: dict[str, list[datetime.datetime]] = {}
MAX_GLOBAL_REQ_PER_MIN = 120
MAX_UPLOAD_REQ_PER_MIN = 20
MAX_REQUEST_BODY_BYTES = 15 * 1024 * 1024  # Item 10: Máximo 15 MB por requisição

# --- ITEM 2: LISTA DE ORIGENS CONFIÁVEIS (CORS & CSRF) ---
_DEFAULT_ALLOWED_ORIGINS = [
    "https://controle-cabecotes-hpef.vercel.app",
    "https://controle-cabecotes.vercel.app",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]
_EXTRA_ORIGINS = [
    o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()
]
ALLOWED_ORIGINS = list(dict.fromkeys(_DEFAULT_ALLOWED_ORIGINS + _EXTRA_ORIGINS))


# --- ITEM 1, 9, 10, 13 & 14: MIDDLEWARE DE SEGURANÇA MULTICAMADA ---
@app.middleware("http")
async def enterprise_security_middleware(request: Request, call_next):
    path = request.url.path
    host = request.headers.get("host", "")
    proto = request.headers.get("x-forwarded-proto", request.url.scheme).lower()

    # Item 1: Forçar HTTPS em produção (exceto localhost / rede local interna)
    is_local = any(h in host for h in ("localhost", "127.0.0.1", "10.", "192.168.", "172."))
    if proto == "http" and not is_local:
        https_url = str(request.url).replace("http://", "https://", 1)
        return RedirectResponse(url=https_url, status_code=307)

    # Item 10: Limite de tamanho de payload contra DoS
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_REQUEST_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"detail": "Payload excede o limite máximo de segurança permitido (15 MB)."}
        )

    # Item 9: Rate Limit Global e de Upload por IP
    client_ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else "unknown")
    )
    if path.startswith("/api/"):
        agora = datetime.datetime.utcnow()
        janela = agora - datetime.timedelta(minutes=1)

        hist_global = [t for t in _GLOBAL_RATE_BUCKETS.get(client_ip, []) if t > janela]
        if len(hist_global) >= MAX_GLOBAL_REQ_PER_MIN:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "60"},
                content={"detail": "Limite de requisições por minuto excedido (Rate Limit). Aguarde alguns segundos."}
            )
        hist_global.append(agora)
        _GLOBAL_RATE_BUCKETS[client_ip] = hist_global

        if path == "/api/upload" and request.method == "POST":
            hist_up = [t for t in _UPLOAD_RATE_BUCKETS.get(client_ip, []) if t > janela]
            if len(hist_up) >= MAX_UPLOAD_REQ_PER_MIN:
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": "60"},
                    content={"detail": "Limite de uploads por minuto excedido. Aguarde 1 minuto."}
                )
            hist_up.append(agora)
            _UPLOAD_RATE_BUCKETS[client_ip] = hist_up

        # Item 13: Proteção contra CSRF em operações de escrita (POST, PUT, DELETE, PATCH)
        if request.method in ("POST", "PUT", "DELETE", "PATCH") and path != "/api/auth/login":
            csrf_cookie = request.cookies.get("scrc_csrf")
            csrf_header = request.headers.get("x-csrf-token")
            if csrf_cookie and csrf_header:
                import hmac
                if not hmac.compare_digest(csrf_cookie, csrf_header):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Bloqueio de segurança CSRF: Token CSRF não confere."}
                    )
            else:
                origin = request.headers.get("origin")
                referer = request.headers.get("referer")
                req_src = origin or referer
                if req_src:
                    origin_host = req_src.split("://")[-1].split("/")[0]
                    if not any(req_src.startswith(o) for o in ALLOWED_ORIGINS) and origin_host != host:
                        return JSONResponse(
                            status_code=403,
                            content={"detail": "Bloqueio de segurança CSRF: Origem não autorizada."}
                        )

    response = await call_next(request)

    # Item 1 & 14: Cabeçalhos de Segurança OWASP Completos
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=(), payment=()"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "script-src-attr 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com data:; "
        "img-src 'self' data: blob:; "
        "connect-src 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )
    return response


# --- ITEM 16: TRATAMENTO SEGURO DE ERROS SEM VAZAMENTO DE STACK TRACE ---
@app.exception_handler(Exception)
async def global_safe_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    trace_id = uuid.uuid4().hex[:10].upper()
    print(f"[ERRO INTERNO #{trace_id}] {request.method} {request.url.path}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Erro interno processado com segurança (Código de rastreio: {trace_id}).",
            "trace_id": trace_id
        }
    )


# --- ITEM 2: CONFIGURAÇÃO DE CORS RESTRITA ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With", "X-CSRF-Token"],
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
    return {
        "status": "error" if _BOOT_ERROR else "ok",
        "frontend_dir_exists": os.path.exists(FRONTEND_DIR),
        "db_initialized": _DB_INITIALIZED
    }


@app.post("/api/upload")
def upload_foto(
    payload: schemas.FotoUploadInput,
    request: Request,
    usuario: models.Usuario = Depends(obter_usuario_atual),
    db: Session = Depends(get_db)
):
    """Item 15: Recebe uma imagem em Base64 validada por assinatura binária (Magic Bytes),
    tamanho máximo e sanitização de nome, persistindo no Banco de Dados."""
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

        # 1. Persistir no Banco de Dados (compatível com Vercel Serverless + Supabase)
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

        registrar_evento_seguranca(
            db,
            evento="UPLOAD_FOTO_VALIDADO",
            severidade="INFO",
            usuario=usuario.username if usuario else "operador",
            ip_origem=request.client.host if request.client else "unknown",
            detalhes=f"Upload seguro validado: {unique_filename} ({len(file_bytes) // 1024} KB)."
        )

        return {"url": f"/uploads/{unique_filename}", "filename": unique_filename}
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Falha ao processar imagem enviada.")


@app.get("/uploads/{filename}")
def get_uploaded_file(filename: str, db: Session = Depends(get_db)):
    safe_file = os.path.basename(filename)
    if not re.match(r"^[a-zA-Z0-9_.-]{1,120}$", safe_file):
        raise HTTPException(status_code=400, detail="Identificador de arquivo inválido.")

    # 1. Buscar no Banco de Dados (funciona na Vercel e localmente)
    foto_db = db.query(models.FotoArmazenada).filter(models.FotoArmazenada.filename == safe_file).first()
    if foto_db:
        img_bytes = base64.b64decode(foto_db.content_base64)
        return Response(
            content=img_bytes,
            media_type=foto_db.mime_type or "image/jpeg",
            headers={
                "Cache-Control": "public, max-age=31536000",
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'inline; filename="{safe_file}"'
            }
        )

    # 2. Fallback para arquivo em disco local
    file_path = os.path.join(UPLOADS_DIR, safe_file)
    if os.path.exists(file_path):
        return FileResponse(
            file_path,
            headers={
                "X-Content-Type-Options": "nosniff",
                "Content-Disposition": f'inline; filename="{safe_file}"'
            }
        )

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
    return {"message": "SCRC API Online. Frontend index.html não localizado."}


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
