from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import re
from ..database import get_db
from .. import models, schemas
from .auth import obter_usuario_atual

router = APIRouter(prefix="/api/clientes", tags=["Clientes"], dependencies=[Depends(obter_usuario_atual)])

def gerar_iniciais_cliente(nome: str) -> str:
    # Remover caracteres especiais e ignorar palavras irrelevantes
    ignorar = {"DE", "DA", "DO", "DOS", "DAS", "E", "LTDA", "ME", "EPP", "SA", "S/A", "INC", "CORP"}
    palavras = re.sub(r'[^a-zA-Z0-9\s]', '', nome).upper().split()
    filtradas = [p for p in palavras if p not in ignorar]
    
    if not filtradas:
        filtradas = palavras
        
    if not filtradas:
        return "CLI"
        
    if len(filtradas) == 1:
        return filtradas[0][:3]
    elif len(filtradas) == 2:
        return (filtradas[0][:2] + filtradas[1][:1])
    else:
        return "".join([p[0] for p in filtradas[:3]])

@router.get("", response_model=List[schemas.ClienteResponse])
def listar_clientes(db: Session = Depends(get_db)):
    return db.query(models.Cliente).order_by(models.Cliente.nome.asc()).all()

@router.post("", response_model=schemas.ClienteResponse, status_code=status.HTTP_201_CREATED)
def criar_cliente(cliente_in: schemas.ClienteCreate, db: Session = Depends(get_db)):
    # Verificar se cliente já existe pelo nome
    cliente_existente = db.query(models.Cliente).filter(models.Cliente.nome == cliente_in.nome).first()
    if cliente_existente:
        return cliente_existente

    iniciais = gerar_iniciais_cliente(cliente_in.nome)
    
    # Garantir unicidade de iniciais se necessário
    iniciais_existentes = db.query(models.Cliente).filter(models.Cliente.iniciais == iniciais).first()
    if iniciais_existentes:
        count = db.query(models.Cliente).filter(models.Cliente.iniciais.like(f"{iniciais}%")).count()
        iniciais = f"{iniciais}{count+1}"

    novo_cliente = models.Cliente(
        nome=cliente_in.nome,
        cnpj=cliente_in.cnpj,
        inscricao_estadual=cliente_in.inscricao_estadual,
        email=cliente_in.email,
        telefone=cliente_in.telefone,
        iniciais=iniciais
    )
    db.add(novo_cliente)
    db.commit()
    db.refresh(novo_cliente)
    return novo_cliente
