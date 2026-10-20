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


@app.get("/")
def read_root():
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "SCRC API Online. Frontend index.html não localizado.", "docs": "/docs"}


@app.get("/style.css")
def read_style():
    style_path = os.path.join(FRONTEND_DIR, "style.css")
    if os.path.exists(style_path):
        return FileResponse(style_path, media_type="text/css")
    return {"error": "style.css não localizado."}


@app.get("/app.js")
def read_js():
    js_path = os.path.join(FRONTEND_DIR, "app.js")
    if os.path.exists(js_path):
        return FileResponse(js_path, media_type="application/javascript")
    return {"error": "app.js não localizado."}


# Endpoint para popular banco com dados fictícios para demonstração
@app.post("/api/sistema/seed", status_code=201)
def popular_dados_iniciais(
    _: models.Usuario = Depends(requer_admin),
    db: Session = Depends(get_db)
):
    import datetime
    import json

    check_and_migrate_db()
    garantir_admin_padrao(db)

    # Criar usuários operadores de exemplo caso não existam
    if not db.query(models.Usuario).filter(models.Usuario.username == "marcos.oficina").first():
        h_op, s_op = gerar_hash_senha("Oficina@2026")
        db.add(models.Usuario(
            username="marcos.oficina",
            nome_completo="Marcos Silva",
            cargo="Operador de Preparação & Usinagem",
            senha_hash=h_op,
            senha_salt=s_op,
            is_admin=False,
            ativo=True,
            permissoes_json=json.dumps(["dashboard", "lavagem", "jateamento", "estanqueidade", "faceamento", "lapidacao", "montagem"])
        ))
    if not db.query(models.Usuario).filter(models.Usuario.username == "pedro.qualidade").first():
        h_qa, s_qa = gerar_hash_senha("Qualidade@2026")
        db.add(models.Usuario(
            username="pedro.qualidade",
            nome_completo="Pedro Almeida",
            cargo="Inspetor de Qualidade & Expedição",
            senha_hash=h_qa,
            senha_salt=s_qa,
            is_admin=False,
            ativo=True,
            permissoes_json=json.dumps(["dashboard", "qualidade", "pintura", "expedicao", "relatorios"])
        ))

    # Limpar tabelas operacionais
    db.query(models.Movimentacao).delete()
    db.query(models.Cabecote).delete()
    db.query(models.Lote).delete()
    db.query(models.Cliente).delete()
    db.commit()

    # 0. Criar Clientes Exemplo
    cli1 = models.Cliente(nome="Retificadora São Paulo LTDA", cnpj="12.345.678/0001-90", inscricao_estadual="110.229.388.110", email="contato@retificarasp.com.br", telefone="(11) 98822-1100", iniciais="RSP")
    cli2 = models.Cliente(nome="Motores Diesel Brasil", cnpj="98.765.432/0001-11", inscricao_estadual="332.110.998.001", email="recebimento@motoresdiesel.com.br", telefone="(11) 3455-8899", iniciais="MDB")
    cli3 = models.Cliente(nome="Caterpillar Servicos", cnpj="44.555.666/0001-22", inscricao_estadual="554.443.221.990", email="oficina@caterpillar.com", telefone="(19) 3881-2000", iniciais="CAT")
    cli4 = models.Cliente(nome="Scania Logistica", cnpj="11.222.333/0001-44", inscricao_estadual="998.776.554.332", email="logistica@scania.com", telefone="(16) 3344-5566", iniciais="SCA")

    db.add_all([cli1, cli2, cli3, cli4])
    db.commit()
    for c in [cli1, cli2, cli3, cli4]:
        db.refresh(c)

    # 1. Lote Recebido (Na Fila de Triagem)
    lote1 = models.Lote(
        codigo_lote="LOT-2026-0001",
        cliente_id=cli2.id,
        cliente_nome=cli2.nome,
        nf_remessa="NF-88231",
        status="RECEBIDO",
        data_pre_cadastro=datetime.datetime.utcnow() - datetime.timedelta(days=1),
        data_entrada=datetime.datetime.utcnow() - datetime.timedelta(hours=4),
        data_estimada_entrega=datetime.datetime.utcnow() + datetime.timedelta(days=4)
    )
    db.add(lote1)
    db.commit()
    db.refresh(lote1)

    for idx, p_id in enumerate(["P-901", "P-902"], start=1):
        num_int = f"MDB-000{idx}"
        db.add(models.Cabecote(
            lote_id=lote1.id,
            numero_serie=f"{num_int} ({p_id})",
            numero_serie_interno=num_int,
            numero_identificacao_peca=p_id,
            status_etapa="TRIAGEM"
        ))

    # 2. Lote em Processo na Oficina com Cabeçotes nas novas etapas
    lote2 = models.Lote(
        codigo_lote="LOT-2026-0002",
        cliente_id=cli3.id,
        cliente_nome=cli3.nome,
        nf_remessa="NF-10022",
        status="EM_PROCESSO",
        data_pre_cadastro=datetime.datetime.utcnow() - datetime.timedelta(days=2),
        data_entrada=datetime.datetime.utcnow() - datetime.timedelta(days=1),
        data_estimada_entrega=datetime.datetime.utcnow() + datetime.timedelta(days=3)
    )
    db.add(lote2)
    db.commit()
    db.refresh(lote2)

    cab_lav = models.Cabecote(
        lote_id=lote2.id,
        numero_serie="CAT-0001 (PECA-111)",
        numero_serie_interno="CAT-0001",
        numero_identificacao_peca="PECA-111",
        status_etapa="LAVAGEM"
    )
    cab_jat = models.Cabecote(
        lote_id=lote2.id,
        numero_serie="CAT-0002 (PECA-112)",
        numero_serie_interno="CAT-0002",
        numero_identificacao_peca="PECA-112",
        status_etapa="JATEAMENTO",
        lavagem_concluida=True,
        lavagem_checkbox=True,
        lavagem_operador="Marcos Silva",
        lavagem_data=datetime.datetime.utcnow() - datetime.timedelta(hours=7)
    )
    cab_est = models.Cabecote(
        lote_id=lote2.id,
        numero_serie="CAT-0003 (PECA-113)",
        numero_serie_interno="CAT-0003",
        numero_identificacao_peca="PECA-113",
        status_etapa="ESTANQUEIDADE",
        lavagem_concluida=True,
        lavagem_checkbox=True,
        lavagem_operador="Marcos Silva",
        jateamento_concluido=True,
        jateamento_checkbox=True,
        jateamento_operador="Marcos Silva"
    )
    cab_lap = models.Cabecote(
        lote_id=lote2.id,
        numero_serie="CAT-0004 (PECA-114)",
        numero_serie_interno="CAT-0004",
        numero_identificacao_peca="PECA-114",
        status_etapa="LAPIDACAO",
        lavagem_concluida=True,
        lavagem_checkbox=True,
        jateamento_concluido=True,
        jateamento_checkbox=True,
        estanqueidade_concluida=True,
        estanqueidade_checkbox=True,
        estanqueidade_pressao=4.5,
        face_concluido=True,
        face_altura_entrada=95.00,
        face_altura_saida=94.85,
        face_plana=True,
        face_operador="Jose Santos",
        lapidacao_tentativas_reprovadas=1,
        lapidacao_confirmacao_vacuo="REP",
        lapidacao_status_retrabalho="TROCAR_VALVULA"
    )
    cab_pronto = models.Cabecote(
        lote_id=lote2.id,
        numero_serie="CAT-0005 (PECA-115)",
        numero_serie_interno="CAT-0005",
        numero_identificacao_peca="PECA-115",
        status_etapa="PRONTO",
        lavagem_concluida=True,
        lavagem_checkbox=True,
        lavagem_operador="Marcos Silva",
        lavagem_data=datetime.datetime.utcnow() - datetime.timedelta(hours=6),
        jateamento_concluido=True,
        jateamento_checkbox=True,
        jateamento_operador="Marcos Silva",
        jateamento_data=datetime.datetime.utcnow() - datetime.timedelta(hours=5),
        estanqueidade_concluida=True,
        estanqueidade_checkbox=True,
        estanqueidade_pressao=5.0,
        estanqueidade_operador="Roberto Dias",
        estanqueidade_data=datetime.datetime.utcnow() - datetime.timedelta(hours=4),
        face_concluido=True,
        face_altura_entrada=95.00,
        face_altura_saida=94.82,
        face_plana=True,
        face_operador="Jose Santos",
        face_data=datetime.datetime.utcnow() - datetime.timedelta(hours=3),
        lapidacao_concluida=True,
        lapidacao_confirmacao_vacuo="APR",
        lapidacao_status_retrabalho="APROVADO",
        lapidacao_trocou_valvula=True,
        lapidacao_operador="Carlos Lima",
        lapidacao_data=datetime.datetime.utcnow() - datetime.timedelta(hours=2),
        montagem_concluida=True,
        montagem_valvula_exaustao=True,
        montagem_valvula_admissao=True,
        montagem_sede_exaustao=False,
        montagem_sede_admissao=True,
        montagem_guia_exaustao=True,
        montagem_guia_admissao=True,
        montagem_operador="Julio Ribeiro",
        montagem_data=datetime.datetime.utcnow() - datetime.timedelta(hours=1, minutes=30),
        qualidade_aprovada=True,
        qualidade_altura_cilindro=94.82,
        qualidade_fotos_json=json.dumps([]),
        qualidade_observacoes="Inspeção dimensional e vedação 100% conformes.",
        qualidade_tecnico="Pedro Almeida",
        qualidade_data=datetime.datetime.utcnow() - datetime.timedelta(hours=1),
        pintura_concluida=True,
        pintura_passa=True,
        pintura_operador="Carlos Lima",
        pintura_data=datetime.datetime.utcnow() - datetime.timedelta(minutes=30)
    )
    db.add_all([cab_lav, cab_jat, cab_est, cab_lap, cab_pronto])
    db.commit()
    db.refresh(cab_pronto)
    construir_e_salvar_relatorio(db, cab_pronto)

    # 3. Lote Concluído Pronto para Expedir
    lote3 = models.Lote(
        codigo_lote="LOT-2026-0003",
        cliente_id=cli4.id,
        cliente_nome=cli4.nome,
        nf_remessa="NF-55421",
        status="CONCLUIDO",
        data_pre_cadastro=datetime.datetime.utcnow() - datetime.timedelta(days=3),
        data_entrada=datetime.datetime.utcnow() - datetime.timedelta(days=2),
        data_estimada_entrega=datetime.datetime.utcnow() + datetime.timedelta(days=2),
        pallet_almoxarifado_final="ALM-A01"
    )
    db.add(lote3)
    db.commit()
    db.refresh(lote3)

    cab_exp = models.Cabecote(
        lote_id=lote3.id,
        numero_serie="SCA-0001 (PECA-001)",
        numero_serie_interno="SCA-0001",
        numero_identificacao_peca="PECA-001",
        status_etapa="PRONTO",
        lavagem_concluida=True,
        lavagem_checkbox=True,
        lavagem_operador="Marcos Silva",
        lavagem_data=datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=6),
        jateamento_concluido=True,
        jateamento_checkbox=True,
        jateamento_operador="Marcos Silva",
        jateamento_data=datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=5),
        estanqueidade_concluida=True,
        estanqueidade_checkbox=True,
        estanqueidade_pressao=5.2,
        estanqueidade_operador="Roberto Dias",
        estanqueidade_data=datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=4),
        face_concluido=True,
        face_altura_entrada=110.50,
        face_altura_saida=110.20,
        face_plana=True,
        face_operador="Jose Santos",
        face_data=datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=3),
        lapidacao_concluida=True,
        lapidacao_confirmacao_vacuo="APR",
        lapidacao_status_retrabalho="APROVADO",
        lapidacao_operador="Carlos Lima",
        lapidacao_data=datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=2),
        montagem_concluida=True,
        montagem_valvula_exaustao=True,
        montagem_valvula_admissao=True,
        montagem_sede_exaustao=True,
        montagem_sede_admissao=True,
        montagem_guia_exaustao=True,
        montagem_guia_admissao=True,
        montagem_operador="Julio Ribeiro",
        montagem_data=datetime.datetime.utcnow() - datetime.timedelta(days=1, hours=1),
        qualidade_aprovada=True,
        qualidade_altura_cilindro=110.20,
        qualidade_fotos_json=json.dumps([]),
        qualidade_observacoes="Peça aprovada sem ressalvas. Relatório emitido.",
        qualidade_tecnico="Pedro Almeida",
        qualidade_data=datetime.datetime.utcnow() - datetime.timedelta(hours=12),
        pintura_concluida=True,
        pintura_passa=True,
        pintura_operador="Carlos Lima",
        pintura_data=datetime.datetime.utcnow() - datetime.timedelta(hours=8)
    )
    db.add(cab_exp)
    db.commit()
    db.refresh(cab_exp)
    construir_e_salvar_relatorio(db, cab_exp)

    # Adicionar logs de movimentações
    db.add(models.Movimentacao(lote_id=lote1.id, estagio_origem="CLIENTE", estagio_destino="TRIAGEM", descricao="Lote recebido fisicamente na portaria."))
    db.add(models.Movimentacao(lote_id=lote2.id, cabecote_id=cab_jat.id, estagio_origem="LAVAGEM", estagio_destino="JATEAMENTO", operador="Marcos Silva", descricao="Cabeçote CAT-0002 lavado e enviado ao Jateamento."))
    db.add(models.Movimentacao(lote_id=lote2.id, cabecote_id=cab_lap.id, estagio_origem="LAPIDACAO", estagio_destino="LAPIDACAO", operador="Carlos Lima", descricao="Teste de Vácuo REPROVADO (1ª vez). Ação obrigatória: TROCAR VÁLVULA e TESTAR novamente."))
    db.add(models.Movimentacao(lote_id=lote3.id, cabecote_id=cab_exp.id, estagio_origem="PINTURA", estagio_destino="PRONTO", operador="Carlos Lima", descricao="Pintura concluída. Peça pronta para Expedição e relatório técnico individual salvo."))

    db.commit()
    return {"message": "Banco de dados populado com o novo fluxo e relatórios individuais!"}
