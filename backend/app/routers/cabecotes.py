from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
try:
    from ..database import get_db
    from .. import models, schemas
except ImportError:
    from database import get_db
    import models, schemas
from .etapas import construir_e_salvar_relatorio
from .auth import obter_usuario_atual, requer_permissao, requer_qualquer_permissao
import json

MODULOS_OPERACIONAIS = [
    "entrada", "recebimento", "lavagem", "jateamento", "estanqueidade",
    "faceamento", "lapidacao", "montagem", "qualidade", "pintura",
    "expedicao", "relatorios", "dashboard"
]

router = APIRouter(prefix="/api/cabecotes", tags=["Cabecotes"], dependencies=[Depends(obter_usuario_atual)])

# 1. Obter detalhes do cabeçote por número de série
@router.get("/buscar/{numero_serie}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_qualquer_permissao(MODULOS_OPERACIONAIS))])
def obter_cabecote_por_serial(numero_serie: str, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.numero_serie == numero_serie).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado com este número de série.")
    return cabecote

# 2. Listar todos os relatórios individuais disponíveis ou todos os cabeçotes com relatório
@router.get("/relatorios/lista", dependencies=[Depends(requer_qualquer_permissao(["relatorios", "qualidade", "expedicao"]))])
def listar_relatorios(db: Session = Depends(get_db)):
    cabecotes = db.query(models.Cabecote).order_by(models.Cabecote.id.desc()).all()
    resultado = []
    for c in cabecotes:
        lote = c.lote
        resultado.append({
            "cabecote_id": c.id,
            "numero_serie": c.numero_serie,
            "numero_identificacao_peca": c.numero_identificacao_peca,
            "status_etapa": c.status_etapa,
            "codigo_lote": lote.codigo_lote if lote else "N/A",
            "cliente_nome": lote.cliente_nome if lote else "N/A",
            "nf_remessa": lote.nf_remessa if lote else "N/A",
            "nf_retorno": lote.nf_retorno if lote else None,
            "relatorio_gerado": bool(c.relatorio_gerado),
            "relatorio_data": c.relatorio_data.strftime("%d/%m/%Y %H:%M") if c.relatorio_data else None,
            "qualidade_tecnico": c.qualidade_tecnico
        })
    return resultado

# 3. Obter ou Gerar Relatório Técnico Individual de um Cabeçote (Salvo no Banco de Dados)
@router.get("/{cabecote_id}/relatorio", dependencies=[Depends(requer_qualquer_permissao(["relatorios", "qualidade", "expedicao"]))])
def obter_relatorio_cabecote(cabecote_id: int, atualizar: bool = True, db: Session = Depends(get_db)) -> Dict[str, Any]:
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if atualizar or not cabecote.relatorio_json:
        return construir_e_salvar_relatorio(db, cabecote)

    try:
        return json.loads(cabecote.relatorio_json)
    except Exception:
        return construir_e_salvar_relatorio(db, cabecote)

# 4. Obter detalhes de um cabeçote específico por ID
@router.get("/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_qualquer_permissao(MODULOS_OPERACIONAIS))])
def obter_cabecote(cabecote_id: int, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")
    return cabecote

# 5. Listar cabeçotes por etapa (ex: LAVAGEM, JATEAMENTO, ESTANQUEIDADE, FACEAMENTO, etc.)
@router.get("", response_model=List[schemas.CabecoteResponse], dependencies=[Depends(requer_qualquer_permissao(MODULOS_OPERACIONAIS))])
def listar_cabecotes(etapa: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Cabecote)
    if etapa:
        query = query.filter(models.Cabecote.status_etapa == etapa)
    return query.all()

# 6. Configurar checklist/rota flutuante (Definido na desmontagem/triagem)
@router.put("/{cabecote_id}/checklist", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("recebimento"))])
def definir_checklist(cabecote_id: int, checklist: schemas.CabecoteUpdateChecklist, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa != "TRIAGEM":
        raise HTTPException(status_code=400, detail="O roteiro só pode ser configurado na etapa de Triagem/Desmontagem.")

    cabecote.requer_jateamento = checklist.requer_jateamento
    cabecote.requer_estanqueidade = checklist.requer_estanqueidade
    cabecote.requer_faceamento = checklist.requer_faceamento
    cabecote.requer_lapidacao = checklist.requer_lapidacao
    cabecote.requer_montagem = checklist.requer_montagem
    cabecote.requer_pintura = checklist.requer_pintura

    # Primeira etapa da oficina: LAVAGEM
    cabecote.status_etapa = "LAVAGEM"

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="TRIAGEM",
        estagio_destino="LAVAGEM",
        descricao=f"Configurada rota para {cabecote.numero_serie}. Enviado para Lavagem."
    )
    db.add(mov)

    lote = db.query(models.Lote).filter(models.Lote.id == cabecote.lote_id).first()
    if lote and lote.status == "RECEBIDO":
        lote.status = "EM_PROCESSO"

    db.commit()
    db.refresh(cabecote)
    return cabecote
