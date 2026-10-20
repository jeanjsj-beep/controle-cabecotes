from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys

# URL oficial do PostgreSQL no Supabase (Pooler IPv4 compatível com Rede Local e Vercel Serverless)
DEFAULT_SUPABASE_URL = "postgresql+pg8000://postgres.hmjspzoabaiqtrkswgco:Lidertech%401995@aws-1-ca-central-1.pooler.supabase.com:6543/postgres"

RAW_DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def resolver_database_url(raw_url: str) -> str:
    """Normaliza e corrige automaticamente URLs do Supabase (incluindo senhas com '@' sem encode
    ou host direto IPv6 db.hmjspzoabaiqtrkswgco.supabase.co incompatível com Vercel IPv4)."""
    if not raw_url:
        return DEFAULT_SUPABASE_URL

    # Se for SQLite local explícito
    if raw_url.startswith("sqlite"):
        return raw_url

    # Se apontar para o projeto Supabase do usuário (mesmo com host direto IPv6 ou '@' não escapado na senha)
    if (
        "hmjspzoabaiqtrkswgco" in raw_url
        or "[YOUR-PASSWORD]" in raw_url
        or "Lidertech@1995@" in raw_url
    ):
        return DEFAULT_SUPABASE_URL

    url = raw_url
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    if url.startswith("postgresql://"):
        try:
            import pg8000  # noqa: F401
            url = url.replace("postgresql://", "postgresql+pg8000://", 1)
        except ImportError:
            pass

    return url


DATABASE_URL = resolver_database_url(RAW_DATABASE_URL)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

try:
    if IS_SQLITE:
        engine = create_engine(
            DATABASE_URL, connect_args={"check_same_thread": False}
        )
    else:
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300
        )
except Exception:
    DATABASE_URL = DEFAULT_SUPABASE_URL
    IS_SQLITE = False
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


def check_and_migrate_db():
    if not IS_SQLITE:
        return
