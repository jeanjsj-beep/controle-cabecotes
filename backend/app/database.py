from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# URL do PostgreSQL no Supabase (Pooler IPv4 compatível com Rede Local e Vercel Serverless)
DEFAULT_SUPABASE_URL = "postgresql://postgres.hmjspzoabaiqtrkswgco:Lidertech%401995@aws-1-ca-central-1.pooler.supabase.com:6543/postgres"

RAW_DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_SUPABASE_URL).strip()

# SQLAlchemy 2.0 requer 'postgresql://' em vez de 'postgres://'
if RAW_DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = RAW_DATABASE_URL.replace("postgres://", "postgresql://", 1)
else:
    DATABASE_URL = RAW_DATABASE_URL

IS_SQLITE = DATABASE_URL.startswith("sqlite")

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

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_and_migrate_db():
    """Executa migração automática de colunas para bancos SQLite locais caso utilizado."""
    if not IS_SQLITE:
        return
