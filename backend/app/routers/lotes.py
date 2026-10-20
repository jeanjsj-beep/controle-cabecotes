from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from ..database import get_db
from .. import models, schemas
from .clientes import criar_cliente
from .etapas import construir_e_salvar_relatorio
from .auth import obter_usuario_atual, requer_permissao
import datetime

router = APIRouter(prefix="/api/lotes", tags=["Lotes"], dependencies=[Depends(obter_usuario_atual)])

# 0. Registro Direto de Entrada de Lote (Com Cliente e Identificação de Peças)
@router.post("/entrada", response_model=schemas.LoteResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(requer_permissao("entrada"))])
def registrar_entrada_lote(dados: schemas.EntradaLoteInput, db: Session = Depends(get_db)):
    cliente = None
    if dados.cliente_id:
        cliente = db.query(models.Cliente).filter(models.Cliente.id == dados.cliente_id).first()
        if not cliente:
            raise HTTPException(status_code=404, detail="Cliente selecionado não encontrado.")
    elif dados.novo_cliente:
        cliente = criar_cliente(dados.novo_cliente, db)
    else:
        raise HTTPException(status_code=400, detail="É necessário selecionar um cliente existente ou cadastrar um novo cliente.")

    if not dados.identificacoes_pecas or len(dados.identificacoes_pecas) == 0:
        raise HTTPException(status_code=400, detail="Por favor, forneça o número de identificação das peças.")

    ano_atual = datetime.datetime.utcnow().strftime("%Y")
    count_lotes = db.query(models.Lote).filter(models.Lote.status != "PRE_CADASTRO").count() + 1
    codigo_lote = f"LOT-{ano_atual}-{count_lotes:04d}"
    while db.query(models.Lote).filter(models.Lote.codigo_lote == codigo_lote).first():
        count_lotes += 1
        codigo_lote = f"LOT-{ano_atual}-{count_lotes:04d}"

    data_atual = datetime.datetime.utcnow()
    novo_lote = models.Lote(
        codigo_lote=codigo_lote,
        cliente_id=cliente.id,
        cliente_nome=cliente.nome,
        status="RECEBIDO",
        data_entrada=data_atual,
        data_estimada_entrega=data_atual + datetime.timedelta(days=5)
    )
    db.add(novo_lote)
    db.commit()
    db.refresh(novo_lote)

    iniciais = cliente.iniciais
    total_existentes_iniciais = db.query(models.Cabecote).filter(models.Cabecote.numero_serie_interno.like(f"{iniciais}-%")).count()

    for idx, id_peca in enumerate(dados.identificacoes_pecas, start=1):
        seq_num = total_existentes_iniciais + idx
        num_interno = f"{iniciais}-{seq_num:04d}"

        id_peca_clean = id_peca.strip() if id_peca else f"PECA-{idx}"
        numero_serie_agregado = f"{num_interno} ({id_peca_clean})" if id_peca_clean else num_interno

        cabecote = models.Cabecote(
            lote_id=novo_lote.id,
            numero_serie=numero_serie_agregado,
            numero_serie_interno=num_interno,
            numero_identificacao_peca=id_peca_clean,
            status_etapa="TRIAGEM",
            requer_jateamento=True,
            requer_estanqueidade=True,
            requer_faceamento=True,
            requer_lapidacao=True,
            requer_montagem=True,
            requer_pintura=True
        )
        db.add(cabecote)

    db.commit()
    db.refresh(novo_lote)

    mov = models.Movimentacao(
        lote_id=novo_lote.id,
        estagio_origem="CLIENTE",
        estagio_destino="TRIAGEM",
        descricao=f"Lote recebido e registrado com {len(dados.identificacoes_pecas)} peças para o cliente {cliente.nome}."
    )
    db.add(mov)
    db.commit()
    db.refresh(novo_lote)
    return novo_lote


# 1. Pré-cadastro do Cliente
@router.post("/pre-cadastro", response_model=schemas.LoteResponse, status_code=status.HTTP_201_CREATED)
def pre_cadastrar_lote(lote_in: schemas.LotePreCadastro, db: Session = Depends(get_db)):
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    codigo_pre = f"PRE-{timestamp}"

    novo_lote = models.Lote(
        codigo_lote=codigo_pre,
        cliente_nome=lote_in.cliente_nome,
        nf_remessa=lote_in.nf_remessa,
        status="PRE_CADASTRO",
        data_pre_cadastro=datetime.datetime.utcnow()
    )
    db.add(novo_lote)
    db.commit()
    db.refresh(novo_lote)

    mov = models.Movimentacao(
        lote_id=novo_lote.id,
        estagio_origem="CLIENTE",
        estagio_destino="RECEBIMENTO",
        descricao=f"Pré-cadastro realizado pelo cliente {lote_in.cliente_nome}. Aguardando chegada física."
    )
    db.add(mov)
    db.commit()
    return novo_lote


# 2. Recebimento Físico (Confirmação na Portaria/Triagem)
@router.post("/{lote_id}/receber", response_model=schemas.LoteResponse, dependencies=[Depends(requer_permissao("recebimento"))])
def receber_lote_fisico(lote_id: int, seriais: List[str], db: Session = Depends(get_db)):
    lote = db.query(models.Lote).filter(models.Lote.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote de pré-cadastro não encontrado.")

    if lote.status != "PRE_CADASTRO":
        raise HTTPException(status_code=400, detail="Este lote já foi recebido fisicamente.")

    if not seriais:
        raise HTTPException(status_code=400, detail="É necessário informar ao menos um número de série de cabeçote.")

    ano_atual = datetime.datetime.utcnow().strftime("%Y")
    count_lotes = db.query(models.Lote).filter(models.Lote.status != "PRE_CADASTRO").count() + 1
    lote.codigo_lote = f"LOT-{ano_atual}-{count_lotes:04d}"

    lote.status = "RECEBIDO"
    lote.data_entrada = datetime.datetime.utcnow()
    lote.data_estimada_entrega = lote.data_entrada + datetime.timedelta(days=5)

    for serial in seriais:
        cabecote_existente = db.query(models.Cabecote).filter(models.Cabecote.numero_serie == serial).first()
        if cabecote_existente:
            raise HTTPException(status_code=400, detail=f"O número de série {serial} já está cadastrado no sistema.")

        novo_cabecote = models.Cabecote(
            lote_id=lote.id,
            numero_serie=serial,
            status_etapa="TRIAGEM",
            requer_jateamento=True,
            requer_estanqueidade=True,
            requer_faceamento=True,
            requer_lapidacao=True,
            requer_montagem=True,
            requer_pintura=True
        )
        db.add(novo_cabecote)

    db.commit()
    db.refresh(lote)

    mov = models.Movimentacao(
        lote_id=lote.id,
        estagio_origem="RECEBIMENTO",
        estagio_destino="TRIAGEM",
        descricao=f"Lote recebido fisicamente com {len(seriais)} cabeçotes individuais cadastrados."
    )
    db.add(mov)
    db.commit()

    db.refresh(lote)
    return lote


# 3. Listagem Geral de Lotes (opção de filtrar por status)
@router.get("", response_model=List[schemas.LoteResponse])
def listar_lotes(status: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Lote)
    if status:
        query = query.filter(models.Lote.status == status)
    lotes = query.order_by(models.Lote.data_entrada.asc()).all()
    return lotes


# 4. Detalhes de um Lote Específico
@router.get("/{lote_id}", response_model=schemas.LoteResponse)
def obter_lote(lote_id: int, db: Session = Depends(get_db)):
    lote = db.query(models.Lote).filter(models.Lote.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")
    return lote


# 5. Expedição e Saída do Lote (Foto, Número da Nota, Veículo, Motorista)
@router.post("/{lote_id}/expedir", response_model=schemas.LoteResponse, dependencies=[Depends(requer_permissao("expedicao"))])
def expedir_lote(lote_id: int, dados: schemas.ExpedicaoInput, db: Session = Depends(get_db)):
    lote = db.query(models.Lote).filter(models.Lote.id == lote_id).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote não encontrado.")

    if lote.status == "PRE_CADASTRO":
        raise HTTPException(status_code=400, detail="Lote não recebido fisicamente.")

    if lote.status == "EXPEDIDO":
        raise HTTPException(status_code=400, detail="Este lote já foi expedido.")

    for cab in lote.cabecotes:
        if cab.status_etapa not in ["PRONTO", "CONDENADO"]:
            raise HTTPException(
                status_code=400,
                detail=f"Não é possível expedir o lote. O cabeçote {cab.numero_serie} está na etapa {cab.status_etapa}."
            )

    lote.status = "EXPEDIDO"
    lote.nf_retorno = dados.nf_retorno
    lote.veiculo = dados.veiculo
    lote.motorista = dados.motorista
    lote.expedicao_foto_url = dados.foto_url
    lote.data_saida = datetime.datetime.utcnow()
    lote.horario_saida = dados.horario_saida or lote.data_saida.strftime("%H:%M")
    if dados.pallet_almoxarifado_final:
        lote.pallet_almoxarifado_final = dados.pallet_almoxarifado_final

    mov = models.Movimentacao(
        lote_id=lote.id,
        estagio_origem="EXPEDICAO",
        estagio_destino="CLIENTE",
        operador=dados.motorista,
        descricao=f"Lote expedido. NF: {dados.nf_retorno} | Veículo: {dados.veiculo} | Motorista: {dados.motorista}."
    )
    db.add(mov)
    db.commit()

    # Atualiza os relatórios individuais de cada cabeçote do lote com os dados da expedição
    for cab in lote.cabecotes:
        construir_e_salvar_relatorio(db, cab)

    db.refresh(lote)
    return lote
