from __future__ import annotations
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
try:
    from ..database import get_db
    from .. import models
except ImportError:
    from database import get_db
    import models
from .auth import obter_usuario_atual, requer_permissao, requer_qualquer_permissao
import datetime

MODULOS_OPERACIONAIS = [
    "entrada", "recebimento", "lavagem", "jateamento", "estanqueidade",
    "faceamento", "lapidacao", "montagem", "qualidade", "pintura",
    "expedicao", "relatorios", "dashboard"
]

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"], dependencies=[Depends(obter_usuario_atual)])

# Espaços pré-definidos do Almoxarifado Randômico
SPACES_ALMOXARIFADO = [
    f"ALM-A{i:02d}" for i in range(1, 13)
] + [
    f"ALM-B{i:02d}" for i in range(1, 13)
]

ETAPAS_PROCESSO = [
    "TRIAGEM", "LAVAGEM", "JATEAMENTO", "ESTANQUEIDADE",
    "FACEAMENTO", "LAPIDACAO", "MONTAGEM", "QUALIDADE", "PINTURA"
]

@router.get("/stats", dependencies=[Depends(requer_permissao("dashboard"))])
def obter_metricas_dashboard(db: Session = Depends(get_db)):
    todos_lotes = db.query(models.Lote).all()
    todos_cabecotes = db.query(models.Cabecote).all()

    total_lotes = len(todos_lotes)
    total_cabecotes = len(todos_cabecotes)

    status_lotes = {
        "PRE_CADASTRO": 0,
        "RECEBIDO": 0,
        "EM_PROCESSO": 0,
        "CONCLUIDO": 0,
        "EXPEDIDO": 0
    }
    for l in todos_lotes:
        status_lotes[l.status] = status_lotes.get(l.status, 0) + 1

    etapas_cabecotes = {
        "TRIAGEM": 0,
        "LAVAGEM": 0,
        "JATEAMENTO": 0,
        "ESTANQUEIDADE": 0,
        "FACEAMENTO": 0,
        "LAPIDACAO": 0,
        "MONTAGEM": 0,
        "QUALIDADE": 0,
        "PINTURA": 0,
        "CONDENADO": 0,
        "PRONTO": 0
    }
    for c in todos_cabecotes:
        etapa_key = "LAVAGEM" if c.status_etapa == "LIMPEZA" else ("PRONTO" if c.status_etapa == "EMBALAGEM" else c.status_etapa)
        etapas_cabecotes[etapa_key] = etapas_cabecotes.get(etapa_key, 0) + 1

    total_condenados = etapas_cabecotes.get("CONDENADO", 0)
    total_prontos = etapas_cabecotes.get("PRONTO", 0)

    taxa_aprovacao = round((1.0 - (total_condenados / max(1, total_cabecotes))) * 100, 1) if total_cabecotes > 0 else 100.0

    lotes_estocados = db.query(models.Lote).filter(
        models.Lote.pallet_almoxarifado_final.isnot(None),
        models.Lote.status != "EXPEDIDO"
    ).all()

    pallets_dict = {}
    for sp in SPACES_ALMOXARIFADO:
        pallets_dict[sp] = {"codigo": sp, "status": "LIVRE", "lote_codigo": None, "cliente_nome": None, "total_pecas": 0}

    for l in lotes_estocados:
        if l.pallet_almoxarifado_final in pallets_dict:
            pallets_dict[l.pallet_almoxarifado_final] = {
                "codigo": l.pallet_almoxarifado_final,
                "status": "OCUPADO",
                "lote_codigo": l.codigo_lote,
                "cliente_nome": l.cliente_nome,
                "total_pecas": len(l.cabecotes)
            }

    espacos_ocupados = [k for k, v in pallets_dict.items() if v["status"] == "OCUPADO"]
    espacos_ociosos = [k for k, v in pallets_dict.items() if v["status"] == "LIVRE"]
    taxa_ocupacao_almoxarifado = round((len(espacos_ocupados) / max(1, len(SPACES_ALMOXARIFADO))) * 100, 1)

    # 1. Contagem real da fila em cada etapa do processo
    gargalos_fila = {etapa: etapas_cabecotes.get(etapa, 0) for etapa in ETAPAS_PROCESSO}

    # 2. Cálculo dinâmico do tempo médio em cada etapa a partir do histórico de movimentações
    tempos_acumulados = {etapa: [] for etapa in ETAPAS_PROCESSO}
    try:
        movs_cabecote = db.query(models.Movimentacao).filter(
            models.Movimentacao.cabecote_id.isnot(None)
        ).order_by(models.Movimentacao.cabecote_id, models.Movimentacao.data_hora.asc()).all()

        movs_por_cab = {}
        for m in movs_cabecote:
            movs_por_cab.setdefault(m.cabecote_id, []).append(m)

        for cid, lista in movs_por_cab.items():
            for idx in range(len(lista) - 1):
                m_atual = lista[idx]
                m_prox = lista[idx + 1]
                etapa = m_atual.estagio_destino
                if etapa in tempos_acumulados and m_prox.data_hora and m_atual.data_hora:
                    delta_horas = (m_prox.data_hora - m_atual.data_hora).total_seconds() / 3600.0
                    if 0 < delta_horas < 720: # ignora outliers acima de 30 dias
                        tempos_acumulados[etapa].append(delta_horas)
    except Exception:
        pass

    gargalos_tempo_medio = {}
    for etapa in ETAPAS_PROCESSO:
        amostras = tempos_acumulados[etapa]
        gargalos_tempo_medio[etapa] = round(sum(amostras) / len(amostras), 1) if amostras else 0.0

    # 3. Identificação do posto gargalo (prioriza tamanho da fila, depois tempo médio)
    max_fila = max(gargalos_fila.values()) if gargalos_fila else 0
    if max_fila > 0:
        posto_gargalo = max(gargalos_fila.items(), key=lambda x: (x[1], gargalos_tempo_medio.get(x[0], 0)))[0]
    else:
        max_tempo = max(gargalos_tempo_medio.values()) if gargalos_tempo_medio else 0
        if max_tempo > 0:
            posto_gargalo = max(gargalos_tempo_medio.items(), key=lambda x: x[1])[0]
        else:
            posto_gargalo = "Sem gargalos"

    now = datetime.datetime.utcnow()
    lotes_com_prazo = [l for l in todos_lotes if l.data_estimada_entrega is not None]
    lotes_no_prazo = sum(1 for l in lotes_com_prazo if l.status == "EXPEDIDO" or l.data_estimada_entrega >= now)
    porcentagem_sla_global = round((lotes_no_prazo / max(1, len(lotes_com_prazo))) * 100, 1) if lotes_com_prazo else 100.0

    sla_clientes = []
    clientes = db.query(models.Cliente).all()
    for cli in clientes:
        lotes_cli = [l for l in todos_lotes if l.cliente_id == cli.id]
        if lotes_cli:
            com_prazo = [l for l in lotes_cli if l.data_estimada_entrega is not None]
            no_prazo = sum(1 for l in com_prazo if l.status == "EXPEDIDO" or l.data_estimada_entrega >= now)
            pct = round((no_prazo / max(1, len(com_prazo))) * 100, 1) if com_prazo else 100.0
            sla_clientes.append({
                "cliente_id": cli.id,
                "cliente_nome": cli.nome,
                "total_lotes": len(lotes_cli),
                "no_prazo": no_prazo,
                "atrasados": len(com_prazo) - no_prazo,
                "porcentagem_sla": pct
            })

    alertas_reposicao = []
    lotes_ativos = db.query(models.Lote).filter(models.Lote.status == "EM_PROCESSO").all()
    for l in lotes_ativos:
        condenadas = sum(1 for c in l.cabecotes if c.status_etapa == "CONDENADO")
        if condenadas > 0:
            alertas_reposicao.append({
                "lote_id": l.id,
                "codigo_lote": l.codigo_lote,
                "cliente_nome": l.cliente_nome,
                "quantidade_condenada": condenadas,
                "mensagem": f"Lote {l.codigo_lote} ({l.cliente_nome}) possui {condenadas} peça(s) condenada(s). Solicitar reposição ao cliente."
            })

    ultimas_mov = db.query(models.Movimentacao).order_by(models.Movimentacao.data_hora.desc()).limit(12).all()
    mov_list = []
    for m in ultimas_mov:
        cab_serial = "Lote Geral"
        if m.cabecote_id:
            cab_obj = db.query(models.Cabecote).filter(models.Cabecote.id == m.cabecote_id).first()
            if cab_obj:
                cab_serial = cab_obj.numero_serie
        elif m.lote and m.lote.cabecotes:
            cab_serial = m.lote.cabecotes[0].numero_serie

        mov_list.append({
            "id": m.id,
            "lote_codigo": m.lote.codigo_lote if m.lote else "N/A",
            "cabecote_serial": cab_serial,
            "estagio_origem": m.estagio_origem,
            "estagio_destino": m.estagio_destino,
            "operador": m.operador or "Operador SCRC",
            "data_hora": m.data_hora.strftime("%d/%m/%Y %H:%M:%S"),
            "descricao": m.descricao
        })

    return {
        "total_lotes": total_lotes,
        "total_cabecotes": total_cabecotes,
        "total_condenados": total_condenados,
        "total_prontos": total_prontos,
        "taxa_aprovacao": taxa_aprovacao,
        "porcentagem_sla_global": porcentagem_sla_global,
        "status_lotes": status_lotes,
        "etapas_cabecotes": etapas_cabecotes,
        "posto_gargalo": posto_gargalo,
        "gargalos_tempo_medio_horas": gargalos_tempo_medio,
        "gargalos_fila": gargalos_fila,
        "pallets_detalhados": list(pallets_dict.values()),
        "almoxarifado_espacos_ociosos": espacos_ociosos,
        "almoxarifado_espacos_ocupados": espacos_ocupados,
        "taxa_ocupacao_almoxarifado": taxa_ocupacao_almoxarifado,
        "sla_clientes": sla_clientes,
        "alertas_reposicao": alertas_reposicao,
        "ultimas_movimentacoes": mov_list
    }


@router.get("/sala/{nome_etapa}", dependencies=[Depends(requer_permissao("dashboard"))])
def obter_detalhes_sala(nome_etapa: str, db: Session = Depends(get_db)):
    nome_upper = nome_etapa.upper()
    cabecotes = db.query(models.Cabecote).filter(models.Cabecote.status_etapa == nome_upper).all()

    resultado = []
    for c in cabecotes:
        lote = c.lote
        resultado.append({
            "id": c.id,
            "numero_serie": c.numero_serie,
            "numero_serie_interno": c.numero_serie_interno,
            "numero_identificacao_peca": c.numero_identificacao_peca,
            "status_etapa": c.status_etapa,
            "lote_id": lote.id,
            "codigo_lote": lote.codigo_lote,
            "cliente_nome": lote.cliente_nome,
            "nf_remessa": lote.nf_remessa,
            "lavagem_concluida": c.lavagem_concluida,
            "jateamento_concluido": c.jateamento_concluido,
            "estanqueidade_concluida": c.estanqueidade_concluida,
            "estanqueidade_pressao": c.estanqueidade_pressao,
            "face_concluido": c.face_concluido,
            "face_altura_entrada": c.face_altura_entrada,
            "face_altura_saida": c.face_altura_saida,
            "lapidacao_concluida": c.lapidacao_concluida,
            "lapidacao_confirmacao_vacuo": c.lapidacao_confirmacao_vacuo,
            "lapidacao_status_retrabalho": c.lapidacao_status_retrabalho,
            "montagem_concluida": c.montagem_concluida,
            "qualidade_aprovada": c.qualidade_aprovada,
            "relatorio_gerado": c.relatorio_gerado,
            "pintura_concluida": c.pintura_concluida,
            "data_entrada": lote.data_entrada.strftime("%d/%m/%Y %H:%M") if lote.data_entrada else "N/A"
        })

    return {
        "sala": nome_upper,
        "total_pecas": len(resultado),
        "pecas": resultado
    }


@router.get("/buscar", dependencies=[Depends(requer_qualquer_permissao(MODULOS_OPERACIONAIS))])
def buscar_global(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    termo = f"%{q.strip()}%"

    lotes = db.query(models.Lote).filter(
        or_(
            models.Lote.codigo_lote.ilike(termo),
            models.Lote.cliente_nome.ilike(termo),
            models.Lote.nf_remessa.ilike(termo),
            models.Lote.nf_retorno.ilike(termo)
        )
    ).limit(6).all()

    cabecotes = db.query(models.Cabecote).filter(
        or_(
            models.Cabecote.numero_serie.ilike(termo),
            models.Cabecote.numero_serie_interno.ilike(termo),
            models.Cabecote.numero_identificacao_peca.ilike(termo)
        )
    ).limit(8).all()

    res_lotes = [{
        "id": l.id,
        "codigo_lote": l.codigo_lote,
        "cliente_nome": l.cliente_nome,
        "nf_remessa": l.nf_remessa,
        "status": l.status,
        "total_pecas": len(l.cabecotes)
    } for l in lotes]

    res_cabecotes = [{
        "id": c.id,
        "numero_serie": c.numero_serie,
        "numero_identificacao_peca": c.numero_identificacao_peca,
        "status_etapa": c.status_etapa,
        "codigo_lote": c.lote.codigo_lote,
        "cliente_nome": c.lote.cliente_nome,
        "relatorio_gerado": bool(c.relatorio_gerado)
    } for c in cabecotes]

    return {
        "query": q,
        "lotes": res_lotes,
        "cabecotes": res_cabecotes
    }
