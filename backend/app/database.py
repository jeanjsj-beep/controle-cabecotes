from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker
try:
    from sqlalchemy.orm import declarative_base
except ImportError:  # SQLAlchemy < 1.4
    from sqlalchemy.ext.declarative import declarative_base
from urllib.parse import unquote
import os
import re
import sys

# Ambiente de execução: a Vercel define VERCEL=1; SCRC_ENV=production força o modo produção em qualquer host.
IS_PRODUCTION = bool(os.getenv("VERCEL")) or os.getenv("SCRC_ENV", "").strip().lower() == "production"

# Host (não secreto) do Supabase Transaction Pooler IPv4, compatível com a Vercel (rede IPv4).
# Pode ser sobrescrito pela variável SUPABASE_POOLER_HOST caso o projeto mude de região.
SUPABASE_POOLER_HOST = os.getenv("SUPABASE_POOLER_HOST", "aws-1-ca-central-1.pooler.supabase.com").strip()

RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

# Banco local de desenvolvimento (somente quando NÃO estamos em produção e DATABASE_URL não foi definida)
LOCAL_SQLITE_URL = "sqlite:///" + os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scrc_dev.db"
).replace("\\", "/")


class ConfiguracaoBancoError(RuntimeError):
    """Configuração do banco de dados ausente ou inválida (nenhuma credencial é incluída na mensagem)."""


def resolver_database_url(raw_url: str) -> str:
    """Normaliza a DATABASE_URL vinda EXCLUSIVAMENTE das variáveis de ambiente.

    - Aceita senhas contendo '@' sem URL-encode.
    - Converte o host direto do Supabase (db.<ref>.supabase.co, apenas IPv6) para o Pooler IPv4 (porta 6543),
      que é o único acessível a partir da Vercel.
    - Usa o driver puro-Python pg8000 (sem dependência de libpq em ambiente Serverless).
    Nenhuma credencial é mantida no código-fonte.
    """
    if not raw_url:
        if IS_PRODUCTION:
            raise ConfiguracaoBancoError(
                "DATABASE_URL não está configurada nas variáveis de ambiente de produção."
            )
        return LOCAL_SQLITE_URL

    if raw_url.startswith("sqlite"):
        return raw_url

    if "[YOUR-PASSWORD]" in raw_url or "YOUR-PASSWORD" in raw_url:
        raise ConfiguracaoBancoError(
            "DATABASE_URL contém o placeholder [YOUR-PASSWORD]; informe a senha real do banco."
        )

    m = re.match(r"^(?:postgres(?:ql)?(?:\+\w+)?)://(?P<resto>.+)$", raw_url)
    if not m:
        raise ConfiguracaoBancoError("DATABASE_URL com formato não suportado (esperado postgresql://...).")

    resto = m.group("resto")
    # O último '@' separa credenciais de host (permite '@' sem encode dentro da senha)
    if "@" not in resto:
        raise ConfiguracaoBancoError("DATABASE_URL sem credenciais (usuario:senha@host).")
    userinfo, hostpart = resto.rsplit("@", 1)
    if ":" in userinfo:
        usuario, senha = userinfo.split(":", 1)
    else:
        usuario, senha = userinfo, ""
    senha = unquote(senha)
    usuario = unquote(usuario)

    host_porta, _, banco = hostpart.partition("/")
    banco = (banco.split("?", 1)[0] or "postgres")
    if ":" in host_porta:
        host, porta_txt = host_porta.rsplit(":", 1)
        porta = int(porta_txt) if porta_txt.isdigit() else 5432
    else:
        host, porta = host_porta, 5432

    direto = re.match(r"^db\.([a-z0-9]+)\.supabase\.co$", host)
    if direto:
        ref = direto.group(1)
        if usuario == "postgres":
            usuario = f"postgres.{ref}"
        host, porta = SUPABASE_POOLER_HOST, 6543

    url = URL.create(
        drivername="postgresql+pg8000",
        username=usuario,
        password=senha,
        host=host,
        port=porta,
        database=banco,
    )
    return url.render_as_string(hide_password=False)


try:
    DATABASE_URL = resolver_database_url(RAW_DATABASE_URL)
except ConfiguracaoBancoError:
    # Propaga para que o main.py registre o erro de boot e responda 503 com mensagem segura
    raise

IS_SQLITE = DATABASE_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Garantir que tanto 'database' quanto 'app.database' apontem para a mesma instância de Base
sys.modules.setdefault("database", sys.modules[__name__])
sys.modules.setdefault("app.database", sys.modules[__name__])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Colunas adicionadas após a primeira versão do esquema: (tabela, coluna, tipo SQLite, tipo PostgreSQL)
_COLUNAS_MIGRACAO = [
    ("usuarios", "token_version", "INTEGER NOT NULL DEFAULT 0", "INTEGER NOT NULL DEFAULT 0"),
    ("usuarios", "must_change_password", "BOOLEAN NOT NULL DEFAULT 0", "BOOLEAN NOT NULL DEFAULT FALSE"),
]


def check_and_migrate_db():
    """Migração idempotente e segura: só executa ALTER TABLE quando a coluna realmente não existe
    (evita bloqueios de tabela desnecessários em cada cold start)."""
    insp = inspect(engine)
    tabelas = set(insp.get_table_names())
    for tabela, coluna, tipo_sqlite, tipo_pg in _COLUNAS_MIGRACAO:
        if tabela not in tabelas:
            continue
        existentes = {c["name"] for c in insp.get_columns(tabela)}
        if coluna in existentes:
            continue
        tipo = tipo_sqlite if IS_SQLITE else tipo_pg
        with engine.begin() as conn:
            conn.execute(text(f'ALTER TABLE "{tabela}" ADD COLUMN "{coluna}" {tipo}'))
