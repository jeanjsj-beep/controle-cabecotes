from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Dict, Any
try:
    from ..database import get_db
    from .. import models, schemas
except ImportError:
    from database import get_db
    import models, schemas
from .auth import obter_usuario_atual, requer_permissao
import datetime
import json

router = APIRouter(prefix="/api/etapas", tags=["Etapas"], dependencies=[Depends(obter_usuario_atual)])

# Configuração Modular: Lapidação Ativa por padrão
CONFIG_LAPIDACAO_ATIVA = True

@router.get("/config", response_model=Dict[str, bool])
def obter_configuracao():
    global CONFIG_LAPIDACAO_ATIVA
    return {"lapidacao_ativa": CONFIG_LAPIDACAO_ATIVA}

@router.post("/config", response_model=Dict[str, bool], dependencies=[Depends(requer_permissao("configuracoes"))])
def atualizar_configuracao(config: Dict[str, bool]):
    global CONFIG_LAPIDACAO_ATIVA
    if "lapidacao_ativa" in config:
        CONFIG_LAPIDACAO_ATIVA = config["lapidacao_ativa"]
    return {"lapidacao_ativa": CONFIG_LAPIDACAO_ATIVA}


def construir_e_salvar_relatorio(db: Session, cabecote: models.Cabecote) -> Dict[str, Any]:
    """
    Monta o relatório técnico individual completo do cabeçote, salva no banco de dados
    do produto (relatorio_json) e retorna o dicionário estruturado para visualização/impressão PDF.
    """
    lote = cabecote.lote
    qual_fotos = []
    if cabecote.qualidade_fotos_json:
        try:
            qual_fotos = json.loads(cabecote.qualidade_fotos_json)
        except Exception:
            qual_fotos = [cabecote.qualidade_fotos_json]

    desgaste_face = None
    if cabecote.face_altura_entrada is not None and cabecote.face_altura_saida is not None:
        desgaste_face = round(cabecote.face_altura_entrada - cabecote.face_altura_saida, 3)

    relatorio = {
        "cabecote_id": cabecote.id,
        "numero_serie": cabecote.numero_serie,
        "numero_serie_interno": cabecote.numero_serie_interno,
        "numero_identificacao_peca": cabecote.numero_identificacao_peca,
        "status_etapa": cabecote.status_etapa,
        "data_emissao": datetime.datetime.utcnow().strftime("%d/%m/%Y %H:%M:%S"),
        "lote": {
            "id": lote.id if lote else None,
            "codigo_lote": lote.codigo_lote if lote else "N/A",
            "cliente_nome": lote.cliente_nome if lote else "N/A",
            "nf_remessa": lote.nf_remessa if lote else "N/A",
            "nf_retorno": lote.nf_retorno if lote else None,
            "veiculo": lote.veiculo if lote else None,
            "motorista": lote.motorista if lote else None,
            "expedicao_foto_url": lote.expedicao_foto_url if lote else None,
            "data_entrada": lote.data_entrada.strftime("%d/%m/%Y %H:%M") if (lote and lote.data_entrada) else None,
            "data_saida": lote.data_saida.strftime("%d/%m/%Y %H:%M") if (lote and lote.data_saida) else None,
        },
        "etapas": {
            "lavagem": {
                "concluida": bool(cabecote.lavagem_concluida),
                "checkbox": bool(cabecote.lavagem_checkbox),
                "foto_url": cabecote.lavagem_foto_url,
                "operador": cabecote.lavagem_operador,
                "data": cabecote.lavagem_data.strftime("%d/%m/%Y %H:%M") if cabecote.lavagem_data else None
            },
            "jateamento": {
                "concluido": bool(cabecote.jateamento_concluido),
                "checkbox": bool(cabecote.jateamento_checkbox),
                "foto_url": cabecote.jateamento_foto_url,
                "operador": cabecote.jateamento_operador,
                "data": cabecote.jateamento_data.strftime("%d/%m/%Y %H:%M") if cabecote.jateamento_data else None
            },
            "estanqueidade": {
                "concluida": bool(cabecote.estanqueidade_concluida),
                "checkbox": bool(cabecote.estanqueidade_checkbox),
                "pressao_aplicada": cabecote.estanqueidade_pressao,
                "foto_url": cabecote.estanqueidade_foto_url,
                "operador": cabecote.estanqueidade_operador,
                "data": cabecote.estanqueidade_data.strftime("%d/%m/%Y %H:%M") if cabecote.estanqueidade_data else None
            },
            "faceamento": {
                "concluido": bool(cabecote.face_concluido),
                "medida_inicial": cabecote.face_altura_entrada,
                "medida_final": cabecote.face_altura_saida,
                "desbaste_mm": desgaste_face,
                "plana": bool(cabecote.face_plana),
                "condenado": bool(cabecote.face_condenado),
                "operador": cabecote.face_operador,
                "data": cabecote.face_data.strftime("%d/%m/%Y %H:%M") if cabecote.face_data else None
            },
            "lapidacao": {
                "concluida": bool(cabecote.lapidacao_concluida),
                "confirmacao_vacuo": cabecote.lapidacao_confirmacao_vacuo,
                "tentativas_reprovadas": cabecote.lapidacao_tentativas_reprovadas or 0,
                "status_retrabalho": cabecote.lapidacao_status_retrabalho,
                "trocou_valvula": bool(cabecote.lapidacao_trocou_valvula),
                "trocou_sede": bool(cabecote.lapidacao_trocou_sede),
                "operador": cabecote.lapidacao_operador,
                "data": cabecote.lapidacao_data.strftime("%d/%m/%Y %H:%M") if cabecote.lapidacao_data else None
            },
            "montagem": {
                "concluida": bool(cabecote.montagem_concluida),
                "valvula_exaustao": bool(cabecote.montagem_valvula_exaustao),
                "valvula_admissao": bool(cabecote.montagem_valvula_admissao),
                "sede_exaustao": bool(cabecote.montagem_sede_exaustao),
                "sede_admissao": bool(cabecote.montagem_sede_admissao),
                "guia_exaustao": bool(cabecote.montagem_guia_exaustao),
                "guia_admissao": bool(cabecote.montagem_guia_admissao),
                "operador": cabecote.montagem_operador,
                "data": cabecote.montagem_data.strftime("%d/%m/%Y %H:%M") if cabecote.montagem_data else None
            },
            "qualidade": {
                "aprovada": cabecote.qualidade_aprovada,
                "altura_cilindro": cabecote.qualidade_altura_cilindro,
                "fotos": qual_fotos,
                "observacoes": cabecote.qualidade_observacoes,
                "tecnico": cabecote.qualidade_tecnico,
                "data": cabecote.qualidade_data.strftime("%d/%m/%Y %H:%M") if cabecote.qualidade_data else None
            },
            "pintura": {
                "concluida": bool(cabecote.pintura_concluida),
                "passa": cabecote.pintura_passa,
                "foto_url": cabecote.pintura_foto_url,
                "operador": cabecote.pintura_operador,
                "data": cabecote.pintura_data.strftime("%d/%m/%Y %H:%M") if cabecote.pintura_data else None
            }
        }
    }

    cabecote.relatorio_gerado = True
    if not cabecote.relatorio_data:
        cabecote.relatorio_data = datetime.datetime.utcnow()
    cabecote.relatorio_json = json.dumps(relatorio, ensure_ascii=False)
    db.commit()
    return relatorio


def obter_proxima_etapa(cabecote: models.Cabecote, etapa_atual: str) -> str:
    """
    Determina a próxima etapa do fluxo de cabeçotes:
    LAVAGEM -> JATEAMENTO -> ESTANQUEIDADE -> FACEAMENTO -> LAPIDACAO -> MONTAGEM -> QUALIDADE -> PINTURA -> PRONTO
    """
    global CONFIG_LAPIDACAO_ATIVA

    fluxo = ["LAVAGEM"]

    if cabecote.requer_jateamento is not False:
        fluxo.append("JATEAMENTO")

    if cabecote.requer_estanqueidade is not False:
        fluxo.append("ESTANQUEIDADE")

    if cabecote.requer_faceamento:
        fluxo.append("FACEAMENTO")

    if cabecote.requer_lapidacao and CONFIG_LAPIDACAO_ATIVA:
        fluxo.append("LAPIDACAO")

    if cabecote.requer_montagem:
        fluxo.append("MONTAGEM")
        fluxo.append("QUALIDADE")

    if cabecote.requer_pintura:
        fluxo.append("PINTURA")

    fluxo.append("PRONTO")

    try:
        idx = fluxo.index(etapa_atual)
        if idx + 1 < len(fluxo):
            return fluxo[idx + 1]
    except ValueError:
        pass

    return "PRONTO"


def verificar_fechamento_lote(db: Session, lote_id: int):
    """
    Verifica se todas as peças do lote foram concluídas (PRONTO ou CONDENADO).
    Se sim, atualiza o status do lote para CONCLUIDO (disponível para Expedição).
    """
    lote = db.query(models.Lote).filter(models.Lote.id == lote_id).first()
    if not lote:
        return

    todas_resolvidas = True
    for cab in lote.cabecotes:
        if cab.status_etapa not in ["PRONTO", "CONDENADO"]:
            todas_resolvidas = False
            break

    if todas_resolvidas and lote.status == "EM_PROCESSO":
        lote.status = "CONCLUIDO"
        mov = models.Movimentacao(
            lote_id=lote.id,
            estagio_origem="OFICINA",
            estagio_destino="EXPEDICAO",
            descricao="Todos os cabeçotes do lote foram finalizados (Prontos/Condenados). Lote liberado para Expedição."
        )
        db.add(mov)
        db.commit()


# 1. Concluir Lavagem (Foto + Checkbox)
@router.post("/lavagem/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("lavagem"))])
def registrar_lavagem(cabecote_id: int, input_data: schemas.LavagemInput, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa not in ["LAVAGEM", "LIMPEZA"]:
        raise HTTPException(status_code=400, detail="O cabeçote não está na etapa de Lavagem.")

    if not input_data.checkbox:
        raise HTTPException(status_code=400, detail="Marque o checkbox de confirmação da Lavagem.")

    cabecote.lavagem_concluida = True
    cabecote.lavagem_checkbox = input_data.checkbox
    cabecote.lavagem_foto_url = input_data.foto_url
    cabecote.lavagem_data = datetime.datetime.utcnow()
    cabecote.lavagem_operador = input_data.operador
    cabecote.limpeza_concluida = True
    cabecote.limpeza_data = cabecote.lavagem_data
    cabecote.limpeza_operador = input_data.operador

    prox = obter_proxima_etapa(cabecote, "LAVAGEM")
    cabecote.status_etapa = prox

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="LAVAGEM",
        estagio_destino=prox,
        operador=input_data.operador,
        descricao="Lavagem química/desengraxante concluída com foto e confirmação."
    )
    db.add(mov)
    db.commit()
    if prox == "PRONTO":
        verificar_fechamento_lote(db, cabecote.lote_id)
    db.refresh(cabecote)
    return cabecote


# 2. Concluir Jateamento (Foto + Checkbox)
@router.post("/jateamento/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("jateamento"))])
def registrar_jateamento(cabecote_id: int, input_data: schemas.JateamentoInput, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa != "JATEAMENTO":
        raise HTTPException(status_code=400, detail="O cabeçote não está na etapa de Jateamento.")

    if not input_data.checkbox:
        raise HTTPException(status_code=400, detail="Marque o checkbox de confirmação do Jateamento.")

    cabecote.jateamento_concluido = True
    cabecote.jateamento_checkbox = input_data.checkbox
    cabecote.jateamento_foto_url = input_data.foto_url
    cabecote.jateamento_data = datetime.datetime.utcnow()
    cabecote.jateamento_operador = input_data.operador

    prox = obter_proxima_etapa(cabecote, "JATEAMENTO")
    cabecote.status_etapa = prox

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="JATEAMENTO",
        estagio_destino=prox,
        operador=input_data.operador,
        descricao="Jateamento abrasivo concluído com registro fotográfico e checkbox."
    )
    db.add(mov)
    db.commit()
    if prox == "PRONTO":
        verificar_fechamento_lote(db, cabecote.lote_id)
    db.refresh(cabecote)
    return cabecote


# 3. Concluir Estanqueidade (Foto + Checkbox + Pressão Aplicada)
@router.post("/estanqueidade/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("estanqueidade"))])
def registrar_estanqueidade(cabecote_id: int, input_data: schemas.EstanqueidadeInput, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa != "ESTANQUEIDADE":
        raise HTTPException(status_code=400, detail="O cabeçote não está na etapa de Estanqueidade.")

    if not input_data.checkbox:
        raise HTTPException(status_code=400, detail="Marque o checkbox de confirmação da Estanqueidade.")

    cabecote.estanqueidade_concluida = True
    cabecote.estanqueidade_checkbox = input_data.checkbox
    cabecote.estanqueidade_foto_url = input_data.foto_url
    cabecote.estanqueidade_pressao = input_data.pressao_aplicada
    cabecote.estanqueidade_data = datetime.datetime.utcnow()
    cabecote.estanqueidade_operador = input_data.operador

    prox = obter_proxima_etapa(cabecote, "ESTANQUEIDADE")
    cabecote.status_etapa = prox

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="ESTANQUEIDADE",
        estagio_destino=prox,
        operador=input_data.operador,
        descricao=f"Teste de Estanqueidade aprovado. Pressão aplicada: {input_data.pressao_aplicada} bar/PSI."
    )
    db.add(mov)
    db.commit()
    if prox == "PRONTO":
        verificar_fechamento_lote(db, cabecote.lote_id)
    db.refresh(cabecote)
    return cabecote


# 4. Registrar Faceamento (Medida Inicial e Medida Final)
@router.post("/faceamento/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("faceamento"))])
def registrar_faceamento(cabecote_id: int, input_data: schemas.FaceamentoInput, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa != "FACEAMENTO":
        raise HTTPException(status_code=400, detail="O cabeçote não está na etapa de Faceamento.")

    cabecote.face_concluido = True
    cabecote.face_altura_entrada = input_data.altura_entrada
    cabecote.face_altura_saida = input_data.altura_saida
    cabecote.face_plana = input_data.plana
    cabecote.face_condenado = input_data.condenado
    cabecote.face_data = datetime.datetime.utcnow()
    cabecote.face_operador = input_data.operador

    if input_data.condenado:
        cabecote.status_etapa = "CONDENADO"
        destino = "CONDENADO"
        lote_atual = db.query(models.Lote).filter(models.Lote.id == cabecote.lote_id).first()
        cliente = lote_atual.cliente_nome if lote_atual else "Desconhecido"
        msg_mov = f"Cabeçote CONDENADO no Faceamento (Medida Inicial: {input_data.altura_entrada}mm, Final: {input_data.altura_saida}mm). Solicitar reposição ao cliente {cliente}."
    else:
        destino = obter_proxima_etapa(cabecote, "FACEAMENTO")
        cabecote.status_etapa = destino
        desgaste = input_data.altura_entrada - input_data.altura_saida
        msg_mov = f"Faceamento concluído. Medida Inicial: {input_data.altura_entrada}mm | Medida Final: {input_data.altura_saida}mm (Desbaste: {desgaste:.3f}mm)."

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="FACEAMENTO",
        estagio_destino=destino,
        operador=input_data.operador,
        descricao=msg_mov
    )
    db.add(mov)
    db.commit()

    if destino in ["CONDENADO", "PRONTO"]:
        verificar_fechamento_lote(db, cabecote.lote_id)

    db.refresh(cabecote)
    return cabecote


# 5. Registrar Lapidação (Confirmação do Vácuo: APR / REP + Fluxo Trocar Válvula -> Testar -> Trocar Sede)
@router.post("/lapidacao/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("lapidacao"))])
def registrar_lapidacao(cabecote_id: int, input_data: schemas.LapidacaoInput, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa != "LAPIDACAO":
        raise HTTPException(status_code=400, detail="O cabeçote não está na etapa de Lapidação.")

    vacuo = input_data.confirmacao_vacuo.upper().strip()
    if vacuo not in ["APR", "REP"]:
        raise HTTPException(status_code=400, detail="Confirmação do vácuo deve ser 'APR' (Aprovado) ou 'REP' (Reprovado).")

    cabecote.lapidacao_confirmacao_vacuo = vacuo
    cabecote.lapidacao_data = datetime.datetime.utcnow()
    cabecote.lapidacao_operador = input_data.operador

    if input_data.trocou_valvula:
        cabecote.lapidacao_trocou_valvula = True
    if input_data.trocou_sede:
        cabecote.lapidacao_trocou_sede = True

    if vacuo == "APR":
        cabecote.lapidacao_concluida = True
        cabecote.lapidacao_status_retrabalho = "APROVADO"
        prox = obter_proxima_etapa(cabecote, "LAPIDACAO")
        cabecote.status_etapa = prox

        detalhes_troca = []
        if cabecote.lapidacao_trocou_valvula:
            detalhes_troca.append("Válvula trocada")
        if cabecote.lapidacao_trocou_sede:
            detalhes_troca.append("Sede trocada")
        complemento = f" ({', '.join(detalhes_troca)})" if detalhes_troca else ""

        msg_mov = f"Lapidação APROVADA no teste de vácuo (APR){complemento}."
    else:
        # Reprovado no teste de vácuo (REP)
        tentativas = (cabecote.lapidacao_tentativas_reprovadas or 0) + 1
        cabecote.lapidacao_tentativas_reprovadas = tentativas
        cabecote.lapidacao_concluida = False
        prox = "LAPIDACAO" # Permanece na Lapidação para o retrabalho

        if tentativas == 1:
            cabecote.lapidacao_status_retrabalho = "TROCAR_VALVULA"
            msg_mov = "Teste de Vácuo REPROVADO (1ª vez). Ação obrigatória: TROCAR VÁLVULA e TESTAR novamente."
        else:
            cabecote.lapidacao_status_retrabalho = "TROCAR_SEDE"
            msg_mov = f"Teste de Vácuo REPROVADO novamente ({tentativas}ª vez após troca de válvula). Ação obrigatória: TROCAR SEDE e realizar novo teste."

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="LAPIDACAO",
        estagio_destino=prox,
        operador=input_data.operador,
        descricao=msg_mov
    )
    db.add(mov)
    db.commit()
    if prox == "PRONTO":
        verificar_fechamento_lote(db, cabecote.lote_id)
    db.refresh(cabecote)
    return cabecote


# 6. Registrar Montagem (Checkboxes: Válvula [Exaustão, Admissão], Sede [Exaustão, Admissão], Guia [Exaustão, Admissão])
@router.post("/montagem/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("montagem"))])
def registrar_montagem(cabecote_id: int, input_data: schemas.MontagemInput, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa != "MONTAGEM":
        raise HTTPException(status_code=400, detail="O cabeçote não está na etapa de Montagem.")

    cabecote.montagem_concluida = True
    cabecote.montagem_valvula_exaustao = input_data.valvula_exaustao
    cabecote.montagem_valvula_admissao = input_data.valvula_admissao
    cabecote.montagem_sede_exaustao = input_data.sede_exaustao
    cabecote.montagem_sede_admissao = input_data.sede_admissao
    cabecote.montagem_guia_exaustao = input_data.guia_exaustao
    cabecote.montagem_guia_admissao = input_data.guia_admissao
    cabecote.montagem_data = datetime.datetime.utcnow()
    cabecote.montagem_operador = input_data.operador

    cabecote.status_etapa = "QUALIDADE"

    itens = []
    if input_data.valvula_exaustao or input_data.valvula_admissao:
        v = []
        if input_data.valvula_exaustao: v.append("Exaustão")
        if input_data.valvula_admissao: v.append("Admissão")
        itens.append(f"Válvula ({', '.join(v)})")
    if input_data.sede_exaustao or input_data.sede_admissao:
        s = []
        if input_data.sede_exaustao: s.append("Exaustão")
        if input_data.sede_admissao: s.append("Admissão")
        itens.append(f"Sede ({', '.join(s)})")
    if input_data.guia_exaustao or input_data.guia_admissao:
        g = []
        if input_data.guia_exaustao: g.append("Exaustão")
        if input_data.guia_admissao: g.append("Admissão")
        itens.append(f"Guia ({', '.join(g)})")

    resumo_itens = ", ".join(itens) if itens else "Componentes padrão"

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="MONTAGEM",
        estagio_destino="QUALIDADE",
        operador=input_data.operador,
        descricao=f"Montagem concluída: {resumo_itens}. Encaminhado para Qualidade."
    )
    db.add(mov)
    db.commit()
    db.refresh(cabecote)
    return cabecote


# 7. Registrar Qualidade (Fotos + Geração e Salvamento do Relatório Individual no Banco)
@router.post("/qualidade/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("qualidade"))])
def registrar_qualidade(cabecote_id: int, input_data: schemas.QualidadeInput, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa != "QUALIDADE":
        raise HTTPException(status_code=400, detail="O cabeçote não está na etapa de Qualidade.")

    cabecote.qualidade_aprovada = input_data.aprovada
    cabecote.qualidade_altura_cilindro = input_data.altura_cilindro
    cabecote.qualidade_fotos_json = json.dumps(input_data.fotos_urls, ensure_ascii=False)
    cabecote.qualidade_observacoes = input_data.observacoes
    cabecote.qualidade_data = datetime.datetime.utcnow()
    cabecote.qualidade_tecnico = input_data.tecnico

    if input_data.aprovada:
        prox = obter_proxima_etapa(cabecote, "QUALIDADE")
        cabecote.status_etapa = prox
        msg_mov = f"Qualidade APROVADA por {input_data.tecnico} ({len(input_data.fotos_urls)} foto(s)). Relatório técnico individual salvo no banco de dados."
    else:
        prox = "MONTAGEM"
        cabecote.status_etapa = prox
        cabecote.montagem_concluida = False
        msg_mov = f"Qualidade REPROVADA por {input_data.tecnico}. Peça retornada para Montagem."

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="QUALIDADE",
        estagio_destino=prox,
        operador=input_data.tecnico,
        descricao=msg_mov
    )
    db.add(mov)
    db.commit()

    # Sempre monta e salva o relatório individual no banco de dados do cabeçote
    if input_data.gerar_relatorio or input_data.aprovada:
        construir_e_salvar_relatorio(db, cabecote)

    if prox == "PRONTO":
        verificar_fechamento_lote(db, cabecote.lote_id)

    db.refresh(cabecote)
    return cabecote


# 8. Registrar Pintura (Foto -> vai direto para PRONTO / Expedição, sem Embalagem)
@router.post("/pintura/{cabecote_id}", response_model=schemas.CabecoteResponse, dependencies=[Depends(requer_permissao("pintura"))])
def registrar_pintura(cabecote_id: int, input_data: schemas.PinturaInput, db: Session = Depends(get_db)):
    cabecote = db.query(models.Cabecote).filter(models.Cabecote.id == cabecote_id).first()
    if not cabecote:
        raise HTTPException(status_code=404, detail="Cabeçote não encontrado.")

    if cabecote.status_etapa != "PINTURA":
        raise HTTPException(status_code=400, detail="O cabeçote não está na etapa de Pintura.")

    cabecote.pintura_concluida = True
    cabecote.pintura_passa = input_data.passa
    cabecote.pintura_operador = input_data.operador
    cabecote.pintura_data = datetime.datetime.utcnow()
    cabecote.pintura_foto_url = input_data.foto_url

    # Sem etapa de embalagem: avança direto para PRONTO (Expedição)
    prox = obter_proxima_etapa(cabecote, "PINTURA")
    cabecote.status_etapa = prox

    mov = models.Movimentacao(
        lote_id=cabecote.lote_id,
        cabecote_id=cabecote.id,
        estagio_origem="PINTURA",
        estagio_destino=prox,
        operador=input_data.operador,
        descricao=f"Pintura concluída ({'APROVADA' if input_data.passa else 'RESSALVA'}) com foto anexada. Peça pronta para Expedição."
    )
    db.add(mov)
    db.commit()

    # Atualiza o relatório individual no banco com os dados da pintura
    construir_e_salvar_relatorio(db, cabecote)

    # Verifica se todo o lote terminou para liberar Expedição
    verificar_fechamento_lote(db, cabecote.lote_id)

    db.refresh(cabecote)
    return cabecote
