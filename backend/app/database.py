from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys

# URL do PostgreSQL no Supabase (Pooler IPv4 compatível com Rede Local e Vercel Serverless)
DEFAULT_SUPABASE_URL = "postgresql://postgres.hmjspzoabaiqtrkswgco:Lidertech%401995@aws-1-ca-central-1.pooler.supabase.com:6543/postgres"

RAW_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SUPABASE_URL).strip()

# Normalizar prefixo e usar pg8000 (driver puro Python sem dependência binária C na Vercel)
if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

IS_SQLITE = DATABASE_URL.startswith("sqlite")

if not IS_SQLITE and DATABASE_URL.startswith("postgresql://"):
    try:
        import pg8000  # noqa: F401
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)
    except ImportError:
        pass

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
