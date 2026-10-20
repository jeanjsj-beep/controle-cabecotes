from pydantic import BaseModel, ConfigDict
from typing import List, Optional, Any
from datetime import datetime

# --- Cliente ---
class ClienteBase(BaseModel):
    nome: str
    cnpj: Optional[str] = None
    inscricao_estadual: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None

class ClienteCreate(ClienteBase):
    pass

class ClienteResponse(ClienteBase):
    id: int
    iniciais: str
    data_cadastro: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

# --- Movimentações ---
class MovimentacaoBase(BaseModel):
    estagio_origem: str
    estagio_destino: str
    operador: Optional[str] = None
    descricao: Optional[str] = None

class MovimentacaoResponse(MovimentacaoBase):
    id: int
    lote_id: int
    cabecote_id: Optional[int] = None
    data_hora: datetime
    model_config = ConfigDict(from_attributes=True)

# --- Cabeçote ---
class CabecoteBase(BaseModel):
    numero_serie: str

class CabecoteCreate(CabecoteBase):
    pass

class CabecoteUpdateChecklist(BaseModel):
    requer_jateamento: bool = True
    requer_estanqueidade: bool = True
    requer_faceamento: bool = True
    requer_lapidacao: bool = True
    requer_montagem: bool = True
    requer_pintura: bool = True

class CabecoteResponse(CabecoteBase):
    id: int
    lote_id: int
    numero_serie_interno: Optional[str] = None
    numero_identificacao_peca: Optional[str] = None
    status_etapa: str

    requer_jateamento: Optional[bool] = True
    requer_estanqueidade: Optional[bool] = True
    requer_faceamento: bool
    requer_lapidacao: bool
    requer_montagem: bool
    requer_pintura: bool

    # 1. Lavagem
    lavagem_concluida: Optional[bool] = False
    lavagem_checkbox: Optional[bool] = False
    lavagem_foto_url: Optional[str] = None
    lavagem_data: Optional[datetime] = None
    lavagem_operador: Optional[str] = None

    # 2. Jateamento
    jateamento_concluido: Optional[bool] = False
    jateamento_checkbox: Optional[bool] = False
    jateamento_foto_url: Optional[str] = None
    jateamento_data: Optional[datetime] = None
    jateamento_operador: Optional[str] = None

    # 3. Estanqueidade
    estanqueidade_concluida: Optional[bool] = False
    estanqueidade_checkbox: Optional[bool] = False
    estanqueidade_foto_url: Optional[str] = None
    estanqueidade_pressao: Optional[float] = None
    estanqueidade_data: Optional[datetime] = None
    estanqueidade_operador: Optional[str] = None

    # 4. Faceamento
    face_concluido: bool
    face_altura_entrada: Optional[float] = None
    face_altura_saida: Optional[float] = None
    face_plana: bool
    face_condenado: bool
    face_data: Optional[datetime] = None
    face_operador: Optional[str] = None

    # 5. Lapidação
    lapidacao_concluida: bool
    lapidacao_confirmacao_vacuo: Optional[str] = None
    lapidacao_tentativas_reprovadas: Optional[int] = 0
    lapidacao_status_retrabalho: Optional[str] = None
    lapidacao_trocou_valvula: Optional[bool] = False
    lapidacao_trocou_sede: Optional[bool] = False
    lapidacao_medida_entrada: Optional[float] = None
    lapidacao_medida_saida: Optional[float] = None
    lapidacao_data: Optional[datetime] = None
    lapidacao_operador: Optional[str] = None

    # 6. Montagem
    montagem_concluida: bool
    montagem_valvula_exaustao: Optional[bool] = False
    montagem_valvula_admissao: Optional[bool] = False
    montagem_sede_exaustao: Optional[bool] = False
    montagem_sede_admissao: Optional[bool] = False
    montagem_guia_exaustao: Optional[bool] = False
    montagem_guia_admissao: Optional[bool] = False
    montagem_data: Optional[datetime] = None
    montagem_operador: Optional[str] = None

    # 7. Qualidade & Relatório Individual
    qualidade_aprovada: Optional[bool] = None
    qualidade_altura_cilindro: Optional[float] = None
    qualidade_fotos_json: Optional[str] = None
    qualidade_observacoes: Optional[str] = None
    qualidade_data: Optional[datetime] = None
    qualidade_tecnico: Optional[str] = None

    relatorio_gerado: Optional[bool] = False
    relatorio_data: Optional[datetime] = None
    relatorio_json: Optional[str] = None

    # 8. Pintura
    pintura_concluida: bool
    pintura_passa: Optional[bool] = None
    pintura_operador: Optional[str] = None
    pintura_data: Optional[datetime] = None
    pintura_foto_url: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

# --- Lotes ---
class LoteBase(BaseModel):
    codigo_lote: str
    cliente_nome: str
    nf_remessa: Optional[str] = None

class LotePreCadastro(BaseModel):
    cliente_nome: str
    nf_remessa: str
    quantidade_estimada: int

class LoteCreate(LoteBase):
    pass

class EntradaLoteInput(BaseModel):
    cliente_id: Optional[int] = None
    novo_cliente: Optional[ClienteCreate] = None
    quantidade: int
    identificacoes_pecas: List[str]

class LoteResponse(LoteBase):
    id: int
    cliente_id: Optional[int] = None
    nf_retorno: Optional[str] = None
    veiculo: Optional[str] = None
    motorista: Optional[str] = None
    expedicao_foto_url: Optional[str] = None
    data_pre_cadastro: Optional[datetime] = None
    data_entrada: Optional[datetime] = None
    data_saida: Optional[datetime] = None
    horario_saida: Optional[str] = None
    status: str
    data_estimada_entrega: Optional[datetime] = None
    pallet_almoxarifado_final: Optional[str] = None
    cabecotes: List[CabecoteResponse] = []
    model_config = ConfigDict(from_attributes=True)

# --- Entradas de Etapas ---
class LavagemInput(BaseModel):
    foto_url: Optional[str] = None
    checkbox: bool = True
    operador: str

class JateamentoInput(BaseModel):
    foto_url: Optional[str] = None
    checkbox: bool = True
    operador: str

class EstanqueidadeInput(BaseModel):
    foto_url: Optional[str] = None
    checkbox: bool = True
    pressao_aplicada: float
    operador: str

class FaceamentoInput(BaseModel):
    altura_entrada: float # Medida Inicial
    altura_saida: float   # Medida Final
    plana: bool = True
    condenado: bool = False
    operador: str

class LapidacaoInput(BaseModel):
    confirmacao_vacuo: str # "APR" ou "REP"
    trocou_valvula: Optional[bool] = False
    trocou_sede: Optional[bool] = False
    operador: str

class MontagemInput(BaseModel):
    valvula_exaustao: bool = False
    valvula_admissao: bool = False
    sede_exaustao: bool = False
    sede_admissao: bool = False
    guia_exaustao: bool = False
    guia_admissao: bool = False
    operador: str

class QualidadeInput(BaseModel):
    aprovada: bool = True
    fotos_urls: List[str] = []
    observacoes: Optional[str] = None
    altura_cilindro: Optional[float] = None
    gerar_relatorio: bool = True
    tecnico: str

class PinturaInput(BaseModel):
    passa: bool = True
    operador: str
    foto_url: Optional[str] = None

class ExpedicaoInput(BaseModel):
    foto_url: Optional[str] = None
    nf_retorno: str
    veiculo: str
    motorista: str
    horario_saida: Optional[str] = None
    pallet_almoxarifado_final: Optional[str] = None

class FotoUploadInput(BaseModel):
    filename: str
    content_base64: str


# --- Autenticação & Usuários ---
class LoginInput(BaseModel):
    username: str
    password: str

class UsuarioCreate(BaseModel):
    username: str
    nome_completo: str
    cargo: Optional[str] = "Operador"
    password: str
    is_admin: bool = False
    ativo: bool = True
    permissoes: List[str] = []

class UsuarioUpdate(BaseModel):
    nome_completo: Optional[str] = None
    cargo: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    ativo: Optional[bool] = None
    permissoes: Optional[List[str]] = None
    desbloquear: Optional[bool] = False

class AlterarSenhaInput(BaseModel):
    senha_atual: str
    nova_senha: str

class UsuarioResponse(BaseModel):
    id: int
    username: str
    nome_completo: str
    cargo: Optional[str] = None
    is_admin: bool
    ativo: bool
    permissoes: List[str] = []
    tentativas_falhas: int = 0
    bloqueado_ate: Optional[datetime] = None
    ultimo_login: Optional[datetime] = None
    criado_em: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expira_em: datetime
    usuario: UsuarioResponse

