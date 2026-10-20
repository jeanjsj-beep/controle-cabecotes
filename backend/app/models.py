from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Float, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import expression
import datetime
import sys

try:
    from .database import Base
except ImportError:
    from database import Base

class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False, index=True)
    cnpj = Column(String, nullable=True)
    inscricao_estadual = Column(String, nullable=True)
    email = Column(String, nullable=True)
    telefone = Column(String, nullable=True)
    data_cadastro = Column(DateTime, default=datetime.datetime.utcnow)
    iniciais = Column(String, nullable=False)

    lotes = relationship("Lote", back_populates="cliente")

class Lote(Base):
    __tablename__ = "lotes"

    id = Column(Integer, primary_key=True, index=True)
    codigo_lote = Column(String, unique=True, index=True, nullable=False)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True)
    cliente_nome = Column(String, nullable=False)
    nf_remessa = Column(String, nullable=True)
    nf_retorno = Column(String, nullable=True)
    veiculo = Column(String, nullable=True)
    motorista = Column(String, nullable=True)
    expedicao_foto_url = Column(String, nullable=True)
    data_pre_cadastro = Column(DateTime, nullable=True, default=datetime.datetime.utcnow)
    data_entrada = Column(DateTime, nullable=True)
    data_saida = Column(DateTime, nullable=True)
    horario_saida = Column(String, nullable=True)
    status = Column(String, default="RECEBIDO", nullable=False) # PRE_CADASTRO, RECEBIDO, EM_PROCESSO, CONCLUIDO, EXPEDIDO
    data_estimada_entrega = Column(DateTime, nullable=True)
    pallet_almoxarifado_final = Column(String, nullable=True)

    cliente = relationship("Cliente", back_populates="lotes")
    cabecotes = relationship("Cabecote", back_populates="lote", cascade="all, delete-orphan")
    movimentacoes = relationship("Movimentacao", back_populates="lote", cascade="all, delete-orphan")

class Cabecote(Base):
    __tablename__ = "cabecotes"

    id = Column(Integer, primary_key=True, index=True)
    lote_id = Column(Integer, ForeignKey("lotes.id"), nullable=False)
    numero_serie = Column(String, unique=True, index=True, nullable=False) # Série exibida/agregada (ex: MDB-0001 (P-101))
    numero_serie_interno = Column(String, nullable=True) # Série gerada pelo sistema (ex: MDB-0001)
    numero_identificacao_peca = Column(String, nullable=True) # Número da peça informado pelo operador
    # Etapas: TRIAGEM, LAVAGEM, JATEAMENTO, ESTANQUEIDADE, FACEAMENTO, LAPIDACAO, MONTAGEM, QUALIDADE, PINTURA, CONDENADO, PRONTO
    status_etapa = Column(String, default="TRIAGEM", nullable=False)

    # Rota Flutuante (Checklist)
    requer_jateamento = Column(Boolean, default=True)
    requer_estanqueidade = Column(Boolean, default=True)
    requer_faceamento = Column(Boolean, default=True)
    requer_lapidacao = Column(Boolean, default=True)
    requer_montagem = Column(Boolean, default=True)
    requer_pintura = Column(Boolean, default=True)

    # 1. Lavagem
    lavagem_concluida = Column(Boolean, default=False)
    lavagem_checkbox = Column(Boolean, default=False)
    lavagem_foto_url = Column(String, nullable=True)
    lavagem_data = Column(DateTime, nullable=True)
    lavagem_operador = Column(String, nullable=True)

    # (Legado mantido por compatibilidade)
    limpeza_concluida = Column(Boolean, default=False)
    limpeza_data = Column(DateTime, nullable=True)
    limpeza_operador = Column(String, nullable=True)

    # 2. Jateamento
    jateamento_concluido = Column(Boolean, default=False)
    jateamento_checkbox = Column(Boolean, default=False)
    jateamento_foto_url = Column(String, nullable=True)
    jateamento_data = Column(DateTime, nullable=True)
    jateamento_operador = Column(String, nullable=True)

    # 3. Estanqueidade
    estanqueidade_concluida = Column(Boolean, default=False)
    estanqueidade_checkbox = Column(Boolean, default=False)
    estanqueidade_foto_url = Column(String, nullable=True)
    estanqueidade_pressao = Column(Float, nullable=True)
    estanqueidade_data = Column(DateTime, nullable=True)
    estanqueidade_operador = Column(String, nullable=True)

    # 4. Faceamento
    face_concluido = Column(Boolean, default=False)
    face_altura_entrada = Column(Float, nullable=True) # Medida Inicial
    face_altura_saida = Column(Float, nullable=True)   # Medida Final
    face_plana = Column(Boolean, default=True)
    face_condenado = Column(Boolean, default=False)
    face_data = Column(DateTime, nullable=True)
    face_operador = Column(String, nullable=True)

    # 5. Lapidação
    lapidacao_concluida = Column(Boolean, default=False)
    lapidacao_confirmacao_vacuo = Column(String, nullable=True) # 'APR' ou 'REP'
    lapidacao_tentativas_reprovadas = Column(Integer, default=0) # 0 = normal, 1 = Trocar Válvula e Testar, >=2 = Trocar Sede
    lapidacao_status_retrabalho = Column(String, nullable=True) # 'TROCAR_VALVULA', 'TROCAR_SEDE', 'APROVADO'
    lapidacao_trocou_valvula = Column(Boolean, default=False)
    lapidacao_trocou_sede = Column(Boolean, default=False)
    lapidacao_medida_entrada = Column(Float, nullable=True)
    lapidacao_medida_saida = Column(Float, nullable=True)
    lapidacao_data = Column(DateTime, nullable=True)
    lapidacao_operador = Column(String, nullable=True)

    # 6. Montagem
    montagem_concluida = Column(Boolean, default=False)
    montagem_valvula_exaustao = Column(Boolean, default=False)
    montagem_valvula_admissao = Column(Boolean, default=False)
    montagem_sede_exaustao = Column(Boolean, default=False)
    montagem_sede_admissao = Column(Boolean, default=False)
    montagem_guia_exaustao = Column(Boolean, default=False)
    montagem_guia_admissao = Column(Boolean, default=False)
    montagem_data = Column(DateTime, nullable=True)
    montagem_operador = Column(String, nullable=True)

    # 7. Qualidade
    qualidade_aprovada = Column(Boolean, nullable=True)
    qualidade_altura_cilindro = Column(Float, nullable=True)
    qualidade_fotos_json = Column(Text, nullable=True) # JSON list of photo URLs
    qualidade_observacoes = Column(Text, nullable=True)
    qualidade_data = Column(DateTime, nullable=True)
    qualidade_tecnico = Column(String, nullable=True)

    # Relatório Individual do Cabeçote (Salvo no Banco de Dados)
    relatorio_gerado = Column(Boolean, default=False)
    relatorio_data = Column(DateTime, nullable=True)
    relatorio_json = Column(Text, nullable=True)

    # 8. Pintura
    pintura_concluida = Column(Boolean, default=False)
    pintura_passa = Column(Boolean, nullable=True)
    pintura_operador = Column(String, nullable=True)
    pintura_data = Column(DateTime, nullable=True)
    pintura_foto_url = Column(String, nullable=True)

    lote = relationship("Lote", back_populates="cabecotes")

class Movimentacao(Base):
    __tablename__ = "movimentacoes"

    id = Column(Integer, primary_key=True, index=True)
    lote_id = Column(Integer, ForeignKey("lotes.id"), nullable=False)
    cabecote_id = Column(Integer, ForeignKey("cabecotes.id"), nullable=True)
    estagio_origem = Column(String, nullable=False)
    estagio_destino = Column(String, nullable=False)
    data_hora = Column(DateTime, default=datetime.datetime.utcnow)
    operador = Column(String, nullable=True)
    descricao = Column(Text, nullable=True)

    lote = relationship("Lote", back_populates="movimentacoes")


class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    nome_completo = Column(String, nullable=False)
    cargo = Column(String, nullable=True, default="Operador")
    senha_hash = Column(String, nullable=False)
    senha_salt = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False, nullable=False)
    ativo = Column(Boolean, default=True, nullable=False)
    permissoes_json = Column(Text, nullable=False, default="[]") # Lista JSON de módulos permitidos
    tentativas_falhas = Column(Integer, default=0, nullable=False)
    bloqueado_ate = Column(DateTime, nullable=True)
    ultimo_login = Column(DateTime, nullable=True)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)
    token_sessao = Column(String, nullable=True, index=True)
    token_expira_em = Column(DateTime, nullable=True)
    # Versão da sessão: incrementada em logout, troca/reset de senha e desativação (revoga todos os tokens emitidos)
    token_version = Column(Integer, default=0, nullable=False, server_default="0")
    # Força a troca da senha no próximo login (senha inicial / redefinida por administrador)
    must_change_password = Column(Boolean, default=False, nullable=False, server_default=expression.false())


class FotoArmazenada(Base):
    """Armazena as imagens comprimidas diretamente no Banco de Dados (PostgreSQL/SQLite)
    para garantir persistência total em ambientes Serverless como a Vercel."""
    __tablename__ = "fotos_armazenadas"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, unique=True, index=True, nullable=False)
    mime_type = Column(String, nullable=False, default="image/jpeg")
    content_base64 = Column(Text, nullable=False)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow)


class AuditoriaSeguranca(Base):
    """Registro imutável de auditoria, monitoramento e alertas de segurança (Item 20)."""
    __tablename__ = "auditoria_seguranca"

    id = Column(Integer, primary_key=True, index=True)
    data_hora = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    evento = Column(String, nullable=False, index=True)       # Ex: LOGIN_SUCESSO, LOGIN_FALHA, BLOQUEIO_CONTA, RATE_LIMIT, ACESSO_NEGADO, BACKUP_GERADO
    severidade = Column(String, nullable=False, default="INFO") # INFO, WARN, CRITICAL
    usuario = Column(String, nullable=True, index=True)
    ip_origem = Column(String, nullable=True)
    detalhes = Column(Text, nullable=True)


class BackupAutomatico(Base):
    """Snapshots automáticos e manuais de backup íntegro do banco (Item 19)."""
    __tablename__ = "backups_automaticos"

    id = Column(Integer, primary_key=True, index=True)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    tipo = Column(String, nullable=False, default="AUTOMATICO") # AUTOMATICO, MANUAL
    autor = Column(String, nullable=True, default="sistema")
    sha256_checksum = Column(String, nullable=False)
    resumo_registros = Column(String, nullable=True)
    payload_criptografado = Column(Text, nullable=False)


class TentativaLogin(Base):
    """Tentativas de login por IP/usuário. Armazenadas no banco para que o limite de tentativas
    funcione de forma consistente entre as várias instâncias Serverless (Vercel)."""
    __tablename__ = "tentativas_login"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String, nullable=False, index=True)
    username = Column(String, nullable=True, index=True)
    criado_em = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    sucesso = Column(Boolean, default=False, nullable=False)


class Configuracao(Base):
    """Configurações persistentes (chave/valor) compartilhadas entre instâncias."""
    __tablename__ = "configuracoes"

    chave = Column(String, primary_key=True)
    valor = Column(String, nullable=False)


class Contador(Base):
    """Contadores atômicos (códigos de lote e séries internas) sem condição de corrida."""
    __tablename__ = "contadores"

    nome = Column(String, primary_key=True)
    valor = Column(Integer, nullable=False, default=0)


sys.modules.setdefault("models", sys.modules[__name__])
sys.modules.setdefault("app.models", sys.modules[__name__])



