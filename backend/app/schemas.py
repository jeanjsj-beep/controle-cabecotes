from pydantic import BaseModel, ConfigDict, Field, BeforeValidator, StringConstraints
from typing import List, Optional, Any
from typing_extensions import Annotated
from datetime import datetime
import re as _re

# --- Tipos de entrada seguros (validação de comprimento, intervalo e limpeza de texto) ---
_CONTROLES = _re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def limpar_texto(valor):
    """Remove caracteres de controle e os delimitadores de tag HTML ('<' e '>') de qualquer texto digitado
    por usuários. É a defesa em profundidade no servidor; a defesa principal é o escape na saída (frontend)."""
    if isinstance(valor, str):
        return _CONTROLES.sub("", valor).replace("<", "").replace(">", "").strip()
    return valor


def _foto_para_none(valor):
    if isinstance(valor, str) and not valor.strip():
        return None
    return valor


def Texto(max_len: int, min_len: int = 0):
    return Annotated[str, BeforeValidator(limpar_texto), StringConstraints(min_length=min_len, max_length=max_len)]


# Somente caminhos internos gerados pelo endpoint /api/upload são aceitos como URL de foto
FotoUrl = Annotated[
    str,
    BeforeValidator(_foto_para_none),
    StringConstraints(pattern=r"^/uploads/[A-Za-z0-9_.-]{1,120}$"),
]
Medida = Annotated[float, Field(ge=0, le=1000, allow_inf_nan=False)]

# --- Cliente ---
class ClienteBase(BaseModel):
    nome: str
    cnpj: Optional[str] = None
    inscricao_estadual: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None

class ClienteCreate(BaseModel):
    nome: Texto(120, 2)
    cnpj: Optional[Texto(20)] = None
    inscricao_estadual: Optional[Texto(20)] = None
    email: Optional[Texto(120)] = None
    telefone: Optional[Texto(30)] = None

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
    cliente_nome: Texto(120, 2)
    nf_remessa: Texto(30)
    quantidade_estimada: int = Field(default=0, ge=0, le=1000)

class LoteCreate(LoteBase):
    pass

class EntradaLoteInput(BaseModel):
    cliente_id: Optional[int] = Field(default=None, ge=1)
    novo_cliente: Optional[ClienteCreate] = None
    quantidade: int = Field(ge=1, le=200)
    identificacoes_pecas: List[Texto(60)] = Field(min_length=1, max_length=200)

class LoteResumo(BaseModel):
    id: int
    codigo_lote: str
    cliente_nome: str
    status: str
    model_config = ConfigDict(from_attributes=True)

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
    foto_url: Optional[FotoUrl] = None
    checkbox: bool = True
    operador: Texto(80, 1)

class JateamentoInput(BaseModel):
    foto_url: Optional[FotoUrl] = None
    checkbox: bool = True
    operador: Texto(80, 1)

class EstanqueidadeInput(BaseModel):
    foto_url: Optional[FotoUrl] = None
    checkbox: bool = True
    aprovada: bool = True  # False = vazamento/trinca -> peça condenada
    pressao_aplicada: Medida
    operador: Texto(80, 1)

class FaceamentoInput(BaseModel):
    altura_entrada: Medida # Medida Inicial
    altura_saida: Medida   # Medida Final
    plana: bool = True
    condenado: bool = False
    operador: Texto(80, 1)

class LapidacaoInput(BaseModel):
    confirmacao_vacuo: Annotated[
        str,
        BeforeValidator(lambda v: v.strip().upper() if isinstance(v, str) else v),
        StringConstraints(pattern=r"^(APR|REP)$"),
    ]  # "APR" ou "REP"
    trocou_valvula: Optional[bool] = False
    trocou_sede: Optional[bool] = False
    operador: Texto(80, 1)

class MontagemInput(BaseModel):
    valvula_exaustao: bool = False
    valvula_admissao: bool = False
    sede_exaustao: bool = False
    sede_admissao: bool = False
    guia_exaustao: bool = False
    guia_admissao: bool = False
    operador: Texto(80, 1)

class QualidadeInput(BaseModel):
    aprovada: bool = True
    fotos_urls: List[FotoUrl] = Field(default_factory=list, max_length=10)
    observacoes: Optional[Texto(1000)] = None
    altura_cilindro: Optional[Medida] = None
    gerar_relatorio: bool = True
    tecnico: Texto(80, 1)

class PinturaInput(BaseModel):
    passa: bool = True
    operador: Texto(80, 1)
    foto_url: Optional[FotoUrl] = None

class ExpedicaoInput(BaseModel):
    foto_url: Optional[FotoUrl] = None
    nf_retorno: Texto(30, 1)
    veiculo: Texto(20, 1)
    motorista: Texto(80, 1)
    horario_saida: Optional[Annotated[str, StringConstraints(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")]] = None
    pallet_almoxarifado_final: Optional[Annotated[str, StringConstraints(pattern=r"^ALM-[AB]\d{2}$")]] = None

class FotoUploadInput(BaseModel):
    filename: Texto(120, 1)
    content_base64: str = Field(min_length=16, max_length=14_000_000)


# --- Autenticação & Usuários ---
class LoginInput(BaseModel):
    username: Annotated[str, StringConstraints(max_length=80)]
    password: Annotated[str, StringConstraints(max_length=256)]

class UsuarioCreate(BaseModel):
    username: Annotated[str, StringConstraints(max_length=40)]
    nome_completo: Texto(120, 3)
    cargo: Optional[Texto(80)] = "Operador"
    password: Annotated[str, StringConstraints(max_length=128)]
    is_admin: bool = False
    ativo: bool = True
    permissoes: List[Annotated[str, StringConstraints(max_length=30)]] = Field(default_factory=list, max_length=30)
    must_change_password: bool = False

class UsuarioUpdate(BaseModel):
    nome_completo: Optional[Texto(120, 3)] = None
    cargo: Optional[Texto(80)] = None
    password: Optional[Annotated[str, StringConstraints(max_length=128)]] = None
    is_admin: Optional[bool] = None
    ativo: Optional[bool] = None
    permissoes: Optional[List[Annotated[str, StringConstraints(max_length=30)]]] = Field(default=None, max_length=30)
    desbloquear: Optional[bool] = False
    must_change_password: Optional[bool] = None

class AlterarSenhaInput(BaseModel):
    senha_atual: Annotated[str, StringConstraints(max_length=256)]
    nova_senha: Annotated[str, StringConstraints(max_length=128)]

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
    must_change_password: bool = False
    model_config = ConfigDict(from_attributes=True)

class LoginResponse(BaseModel):
    # A sessão trafega somente em cookie HttpOnly; o token nunca é exposto ao JavaScript.
    access_token: Optional[str] = None
    token_type: str = "cookie"
    expira_em: datetime
    usuario: UsuarioResponse

import sys as _sys
_sys.modules.setdefault("schemas", _sys.modules[__name__])
_sys.modules.setdefault("app.schemas", _sys.modules[__name__])


