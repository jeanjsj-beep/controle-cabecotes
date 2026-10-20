from fastapi import APIRouter, Depends, HTTPException, status, Header, Request
from sqlalchemy.orm import Session
from typing import List, Optional
try:
    from ..database import get_db
    from .. import models, schemas
except ImportError:
    from database import get_db
    import models, schemas
import datetime
import hashlib
import hmac
import secrets
import json
import re

router = APIRouter(prefix="/api", tags=["Autenticação & Segurança"])

# Lista oficial de módulos/permissões do sistema
TODOS_MODULOS_PERMISSOES = [
    "dashboard",
    "entrada",
    "recebimento",
    "lavagem",
    "jateamento",
    "estanqueidade",
    "faceamento",
    "lapidacao",
    "montagem",
    "qualidade",
    "pintura",
    "expedicao",
    "relatorios",
    "configuracoes"
]

# Configurações de Segurança
PBKDF2_ITERATIONS = 200_000
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_MINUTES = 5
SESSION_DURATION_HOURS = 24
TOKEN_SIGNING_SECRET = "scrc-hmac-sha256-session-key-2026-v3"

# Rate limiter em memória por IP para mitigar ataques de força bruta distribuídos
_IP_ATTEMPTS: dict[str, list[datetime.datetime]] = {}
MAX_IP_ATTEMPTS_PER_MINUTE = 15


def verificar_rate_limit_ip(ip: str):
    agora = datetime.datetime.utcnow()
    janela = agora - datetime.timedelta(minutes=1)
    historico = [t for t in _IP_ATTEMPTS.get(ip, []) if t > janela]
    if len(historico) >= MAX_IP_ATTEMPTS_PER_MINUTE:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas tentativas de acesso a partir deste endereço. Aguarde 1 minuto e tente novamente."
        )
    historico.append(agora)
    _IP_ATTEMPTS[ip] = historico


def gerar_hash_senha(password: str, salt_hex: Optional[str] = None) -> tuple[str, str]:
    """Gera hash seguro PBKDF2-HMAC-SHA256 com 200.000 iterações e salt criptográfico."""
    if not salt_hex:
        salt_hex = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS
    )
    return dk.hex(), salt_hex


def verificar_senha(password: str, hash_armazenado: str, salt_hex: str) -> bool:
    """Compara a senha em tempo constante (constant-time) para evitar timing attacks."""
    try:
        dk_calculado, _ = gerar_hash_senha(password, salt_hex)
        return hmac.compare_digest(dk_calculado, hash_armazenado)
    except Exception:
        return False


def hash_token_sessao(raw_token: str) -> str:
    """Armazena apenas o hash SHA-256 do token de sessão no banco de dados."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def gerar_token_sessao_assinado(usuario: models.Usuario, expira_em: datetime.datetime) -> str:
    """Gera um token Bearer assinado via HMAC-SHA256 (suporta múltiplas abas/dispositivos simultâneos
    sem desconectar sessões ativas e invalida automaticamente se a senha ou status mudar)."""
    exp_ts = int(expira_em.replace(tzinfo=datetime.timezone.utc).timestamp())
    nonce = secrets.token_hex(8)
    payload = f"s1.{usuario.id}.{exp_ts}.{nonce}"
    chave = f"{TOKEN_SIGNING_SECRET}:{usuario.senha_salt}:{usuario.senha_hash[:24]}".encode("utf-8")
    assinatura = hmac.new(chave, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{assinatura}"


def validar_token_sessao_assinado(raw_token: str, db: Session) -> Optional[models.Usuario]:
    """Valida token HMAC-SHA256 em tempo constante."""
    try:
        partes = raw_token.split(".")
        if len(partes) != 5 or partes[0] != "s1":
            return None
        _, uid_str, exp_str, nonce, assinatura_recebida = partes
        uid = int(uid_str)
        exp_ts = int(exp_str)
        agora_ts = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        if exp_ts < agora_ts:
            return None
        usuario = db.query(models.Usuario).filter(models.Usuario.id == uid).first()
        if not usuario:
            return None
        payload = f"s1.{uid}.{exp_ts}.{nonce}"
        chave = f"{TOKEN_SIGNING_SECRET}:{usuario.senha_salt}:{usuario.senha_hash[:24]}".encode("utf-8")
        assinatura_esperada = hmac.new(chave, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(assinatura_recebida, assinatura_esperada):
            return None
        return usuario
    except Exception:
        return None


def validar_username(username: str) -> str:
    u = (username or "").strip().lower()
    if len(u) < 3 or len(u) > 40:
        raise HTTPException(status_code=400, detail="O login deve ter entre 3 e 40 caracteres.")
    if not re.match(r"^[a-z0-9._-]+$", u):
        raise HTTPException(
            status_code=400,
            detail="O login só pode conter letras sem acento, números, ponto (.), hífen (-) ou sublinhado (_)."
        )
    return u


def validar_forca_senha(password: str):
    if not password or len(password) < 8:
        raise HTTPException(status_code=400, detail="A senha deve conter no mínimo 8 caracteres.")
    if len(password) > 128:
        raise HTTPException(status_code=400, detail="A senha não pode exceder 128 caracteres.")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="A senha deve conter pelo menos uma letra maiúscula (A-Z).")
    if not re.search(r"[a-z]", password):
        raise HTTPException(status_code=400, detail="A senha deve conter pelo menos uma letra minúscula (a-z).")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="A senha deve conter pelo menos um número (0-9).")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=400, detail="A senha deve conter pelo menos um caractere especial (ex: @, #, $, !, %, &).")


def serializar_usuario(u: models.Usuario) -> schemas.UsuarioResponse:
    try:
        perms = json.loads(u.permissoes_json) if u.permissoes_json else []
    except Exception:
        perms = []
    if u.is_admin:
        perms = list(TODOS_MODULOS_PERMISSOES)
    return schemas.UsuarioResponse(
        id=u.id,
        username=u.username,
        nome_completo=u.nome_completo,
        cargo=u.cargo,
        is_admin=bool(u.is_admin),
        ativo=bool(u.ativo),
        permissoes=perms,
        tentativas_falhas=u.tentativas_falhas or 0,
        bloqueado_ate=u.bloqueado_ate,
        ultimo_login=u.ultimo_login,
        criado_em=u.criado_em
    )


def garantir_admin_padrao(db: Session):
    """Garante que o usuário Administrador principal exista no banco de dados."""
    admin = db.query(models.Usuario).filter(models.Usuario.username == "admin").first()
    if not admin:
        senha_hash, senha_salt = gerar_hash_senha("Admin@2026")
        admin = models.Usuario(
            username="admin",
            nome_completo="Administrador Geral",
            cargo="Administrador do Sistema",
            senha_hash=senha_hash,
            senha_salt=senha_salt,
            is_admin=True,
            ativo=True,
            permissoes_json=json.dumps(TODOS_MODULOS_PERMISSOES)
        )
        db.add(admin)
        db.commit()


# --- DEPENDÊNCIAS DE SEGURANÇA E PERMISSÕES ---
def obter_usuario_atual(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db)
) -> models.Usuario:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão não autenticada. Faça login para continuar."
        )

    raw_token = authorization.split(" ", 1)[1].strip()
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso ausente ou inválido."
        )

    # 1. Validar token assinado HMAC-SHA256 (multi-aba / Serverless)
    if raw_token.startswith("s1."):
        usuario = validar_token_sessao_assinado(raw_token, db)
        if not usuario:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Sessão inválida ou expirada. Faça login novamente."
            )
        if not usuario.ativo:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sua conta de usuário está desativada. Contate o Administrador."
            )
        return usuario

    # 2. Fallback para tokens legados salvos em banco
    token_hash = hash_token_sessao(raw_token)
    usuario = db.query(models.Usuario).filter(models.Usuario.token_sessao == token_hash).first()

    if not usuario:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sessão inválida ou expirada. Faça login novamente."
        )

    if not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sua conta de usuário está desativada. Contate o Administrador."
        )

    agora = datetime.datetime.utcnow()
    if not usuario.token_expira_em or usuario.token_expira_em < agora:
        usuario.token_sessao = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sua sessão expirou por segurança. Faça login novamente."
        )

    return usuario


def requer_admin(usuario: models.Usuario = Depends(obter_usuario_atual)) -> models.Usuario:
    if not usuario.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: esta operação exige privilégios de Administrador."
        )
    return usuario


def verificar_permissao_usuario(usuario: models.Usuario, modulo: str):
    if usuario.is_admin:
        return True
    try:
        perms = json.loads(usuario.permissoes_json) if usuario.permissoes_json else []
    except Exception:
        perms = []
    if modulo not in perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Acesso negado: seu perfil não possui permissão para o módulo '{modulo.upper()}'."
        )
    return True


def requer_permissao(modulo: str):
    def _dep(usuario: models.Usuario = Depends(obter_usuario_atual)) -> models.Usuario:
        verificar_permissao_usuario(usuario, modulo)
        return usuario
    return _dep


# --- ENDPOINTS DE AUTENTICAÇÃO ---
@router.post("/auth/login", response_model=schemas.LoginResponse)
def login(dados: schemas.LoginInput, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    verificar_rate_limit_ip(client_ip)

    garantir_admin_padrao(db)

    username = (dados.username or "").strip().lower()
    password = dados.password or ""

    if not username or not password:
        raise HTTPException(status_code=400, detail="Informe o usuário e a senha.")

    usuario = db.query(models.Usuario).filter(models.Usuario.username == username).first()

    # Mensagem genérica padrão para evitar enumeração de usuários
    erro_credenciais = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Usuário ou senha inválidos."
    )

    if not usuario:
        # Executa PBKDF2 dummy para manter tempo de resposta constante contra enumeração por timing
        gerar_hash_senha(password, "00" * 16)
        raise erro_credenciais

    if not usuario.ativo:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Esta conta está desativada pelo Administrador."
        )

    agora = datetime.datetime.utcnow()
    if usuario.bloqueado_ate and usuario.bloqueado_ate > agora:
        segundos_restantes = int((usuario.bloqueado_ate - agora).total_seconds())
        minutos_restantes = max(1, (segundos_restantes + 59) // 60)
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Conta temporariamente bloqueada por excesso de tentativas incorretas. Tente novamente em {minutos_restantes} minuto(s) ou solicite desbloqueio ao Administrador."
        )

    senha_correta = verificar_senha(password, usuario.senha_hash, usuario.senha_salt)
    if not senha_correta:
        tentativas = (usuario.tentativas_falhas or 0) + 1
        usuario.tentativas_falhas = tentativas
        if tentativas >= MAX_LOGIN_ATTEMPTS:
            usuario.bloqueado_ate = agora + datetime.timedelta(minutes=LOCKOUT_MINUTES)
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Conta bloqueada por {LOCKOUT_MINUTES} minutos após {MAX_LOGIN_ATTEMPTS} tentativas de senha incorretas."
            )
        db.commit()
        restantes = MAX_LOGIN_ATTEMPTS - tentativas
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Usuário ou senha inválidos. ({restantes} tentativa(s) restante(s) antes do bloqueio de segurança)."
        )

    # Login bem-sucedido: limpa contador de falhas e gera token criptográfico assinado (HMAC-SHA256)
    expira_em = agora + datetime.timedelta(hours=SESSION_DURATION_HOURS)
    raw_token = gerar_token_sessao_assinado(usuario, expira_em)

    usuario.tentativas_falhas = 0
    usuario.bloqueado_ate = None
    usuario.ultimo_login = agora
    usuario.token_sessao = hash_token_sessao(raw_token)
    usuario.token_expira_em = expira_em

    db.commit()
    db.refresh(usuario)

    return schemas.LoginResponse(
        access_token=raw_token,
        token_type="bearer",
        expira_em=expira_em,
        usuario=serializar_usuario(usuario)
    )


@router.post("/auth/logout")
def logout(usuario: models.Usuario = Depends(obter_usuario_atual), db: Session = Depends(get_db)):
    usuario.token_sessao = None
    usuario.token_expira_em = None
    db.commit()
    return {"message": "Sessão encerrada com segurança."}


@router.get("/auth/me", response_model=schemas.UsuarioResponse)
def obter_perfil_logado(usuario: models.Usuario = Depends(obter_usuario_atual)):
    return serializar_usuario(usuario)


@router.post("/auth/alterar-senha")
def alterar_propria_senha(
    dados: schemas.AlterarSenhaInput,
    usuario: models.Usuario = Depends(obter_usuario_atual),
    db: Session = Depends(get_db)
):
    if not verificar_senha(dados.senha_atual, usuario.senha_hash, usuario.senha_salt):
        raise HTTPException(status_code=400, detail="A senha atual informada está incorreta.")

    if dados.senha_atual == dados.nova_senha:
        raise HTTPException(status_code=400, detail="A nova senha deve ser diferente da senha atual.")

    validar_forca_senha(dados.nova_senha)
    novo_hash, novo_salt = gerar_hash_senha(dados.nova_senha)
    usuario.senha_hash = novo_hash
    usuario.senha_salt = novo_salt
    db.commit()
    return {"message": "Senha alterada com sucesso!"}


# --- GESTÃO DE USUÁRIOS E PERMISSÕES (EXCLUSIVO ADMINISTRADOR) ---
@router.get("/usuarios", response_model=List[schemas.UsuarioResponse])
def listar_usuarios(
    _: models.Usuario = Depends(requer_admin),
    db: Session = Depends(get_db)
):
    usuarios = db.query(models.Usuario).order_by(models.Usuario.is_admin.desc(), models.Usuario.nome_completo.asc()).all()
    return [serializar_usuario(u) for u in usuarios]


@router.post("/usuarios", response_model=schemas.UsuarioResponse, status_code=status.HTTP_201_CREATED)
def criar_usuario(
    dados: schemas.UsuarioCreate,
    _: models.Usuario = Depends(requer_admin),
    db: Session = Depends(get_db)
):
    username = validar_username(dados.username)
    nome = (dados.nome_completo or "").strip()
    if len(nome) < 3:
        raise HTTPException(status_code=400, detail="Informe o nome completo do usuário (mínimo 3 caracteres).")

    existente = db.query(models.Usuario).filter(models.Usuario.username == username).first()
    if existente:
        raise HTTPException(status_code=400, detail=f"O login '{username}' já está em uso por outro usuário.")

    validar_forca_senha(dados.password)
    senha_hash, senha_salt = gerar_hash_senha(dados.password)

    perms_validas = [p for p in dados.permissoes if p in TODOS_MODULOS_PERMISSOES]
    if dados.is_admin:
        perms_validas = list(TODOS_MODULOS_PERMISSOES)

    novo = models.Usuario(
        username=username,
        nome_completo=nome,
        cargo=(dados.cargo or "Operador").strip(),
        senha_hash=senha_hash,
        senha_salt=senha_salt,
        is_admin=dados.is_admin,
        ativo=dados.ativo,
        permissoes_json=json.dumps(perms_validas)
    )
    db.add(novo)
    db.commit()
    db.refresh(novo)
    return serializar_usuario(novo)


@router.put("/usuarios/{usuario_id}", response_model=schemas.UsuarioResponse)
def atualizar_usuario(
    usuario_id: int,
    dados: schemas.UsuarioUpdate,
    admin_logado: models.Usuario = Depends(requer_admin),
    db: Session = Depends(get_db)
):
    u = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    # Impedir que o único administrador remova seu próprio privilégio de admin ou se desative
    if u.id == admin_logado.id:
        if dados.is_admin is False:
            raise HTTPException(status_code=400, detail="Você não pode remover seu próprio privilégio de Administrador.")
        if dados.ativo is False:
            raise HTTPException(status_code=400, detail="Você não pode desativar sua própria conta.")

    if dados.nome_completo is not None:
        nome = dados.nome_completo.strip()
        if len(nome) < 3:
            raise HTTPException(status_code=400, detail="Nome completo inválido.")
        u.nome_completo = nome

    if dados.cargo is not None:
        u.cargo = dados.cargo.strip()

    if dados.is_admin is not None:
        u.is_admin = dados.is_admin

    if dados.ativo is not None:
        u.ativo = dados.ativo
        if not dados.ativo:
            u.token_sessao = None # Derruba sessão ativa imediatamente

    if dados.permissoes is not None:
        perms_validas = [p for p in dados.permissoes if p in TODOS_MODULOS_PERMISSOES]
        if u.is_admin:
            perms_validas = list(TODOS_MODULOS_PERMISSOES)
        u.permissoes_json = json.dumps(perms_validas)

    if dados.password:
        validar_forca_senha(dados.password)
        novo_hash, novo_salt = gerar_hash_senha(dados.password)
        u.senha_hash = novo_hash
        u.senha_salt = novo_salt
        u.token_sessao = None # Força novo login quando a senha é redefinida

    if dados.desbloquear:
        u.tentativas_falhas = 0
        u.bloqueado_ate = None

    db.commit()
    db.refresh(u)
    return serializar_usuario(u)


@router.delete("/usuarios/{usuario_id}")
def excluir_usuario(
    usuario_id: int,
    admin_logado: models.Usuario = Depends(requer_admin),
    db: Session = Depends(get_db)
):
    u = db.query(models.Usuario).filter(models.Usuario.id == usuario_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")

    if u.id == admin_logado.id:
        raise HTTPException(status_code=400, detail="Você não pode excluir sua própria conta logada.")

    if u.username == "admin":
        raise HTTPException(status_code=400, detail="A conta principal 'admin' não pode ser excluída.")

    db.delete(u)
    db.commit()
    return {"message": f"Usuário '{u.username}' removido com sucesso."}
