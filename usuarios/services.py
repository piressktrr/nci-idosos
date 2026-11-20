"""Gestão de colaboradores (RF-USR-03, RN-USR-01): cadastro, correção e nova senha, com auditoria (RNF-SEG-07).

Só administradores (`core.perfis.e_administrador`) usam estes serviços. Cada gravação acontece numa transação
junto com o seu evento `RegistroConta`. A senha nunca vai para a auditoria (nem o hash): o evento "senha" só
registra que ela foi redefinida.

Recuperação de acesso (RF-USR-05) permanece pendente. Desativação autorizada pelo responsável.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q

from core.permissoes import autorizar_administrador as _autorizar_administrador
from core.perfis import GRUPO_ADMINISTRADOR, PERFIS

from .models import RegistroConta

# Grupos que são perfis de acesso; uma conta tem no máximo um (outros grupos dados à mão são mantidos).
NOMES_PERFIS = tuple(PERFIS)
CAMPOS_CORRECAO = ("first_name", "last_name", "email", "perfil")


def autorizar_administrador(usuario):
    """RN-USR-01: devolve o autor reconsultado no banco se for administrador ativo (critério do core)."""
    return _autorizar_administrador(usuario, "Somente administradores podem gerenciar contas de acesso.")


def _proteger_superusuario(conta, autor):
    """RN-USR-01: só um superusuário altera dados, senha ou situação de outro superusuário.

    Sem isso, um membro do grupo Administrador poderia definir a senha de um superusuário, entrar como ele e ganhar
    o /admin/ e o catálogo do FMR, com as ações atribuídas ao superusuário.
    """
    if conta.is_superuser and not autor.is_superuser:
        raise PermissionDenied("Somente um superusuário pode alterar a conta de outro superusuário.")


def perfil_de(conta):
    """Nome do perfil (grupo) da conta, ou "" se não tiver. Com os dois grupos, vale Administrador."""
    grupos = {grupo.name for grupo in conta.groups.all()}  # aproveita prefetch_related("groups")
    for nome in (GRUPO_ADMINISTRADOR, *NOMES_PERFIS):
        if nome in grupos:
            return nome
    return ""


def _dados(conta, perfil):
    """Dados auditados da conta (sem senha)."""
    return {"username": conta.username, "first_name": conta.first_name, "last_name": conta.last_name,
            "email": conta.email, "perfil": perfil}


def _registrar(*, conta, acao, autor, novos, anteriores=None):
    return RegistroConta.objects.create(alvo_id=conta.pk, acao=acao, usuario=autor, anteriores=anteriores,
                                        novos=novos)


def _erros_dados(conta, **opcoes):
    """Erros do full_clean da conta; o nome é obrigatório aqui, embora o modelo do Django o aceite vazio."""
    erros = {}
    try:
        conta.full_clean(**opcoes)
    except ValidationError as erro:
        erros.update(erro.message_dict)
    if not conta.first_name:
        erros.setdefault("first_name", []).append("Informe o nome.")
    if not conta.email:  # RF-USR-05: sem e-mail não há como recuperar a senha
        erros.setdefault("email", []).append("Informe o e-mail.")
    return erros


def _validar_perfil(perfil):
    if perfil not in NOMES_PERFIS:
        raise ValidationError({"perfil": "Escolha um perfil válido."})


def _definir_perfil(conta, perfil):
    conta.groups.remove(*Group.objects.filter(name__in=NOMES_PERFIS).exclude(name=perfil))
    conta.groups.add(Group.objects.get(name=perfil))


def _validar_senha(senha, conta):
    try:
        validate_password(senha, conta)
    except ValidationError as erro:
        raise ValidationError({"senha": erro.messages}) from None


def garantir_administrador_restante(conta, novo_perfil):
    """Recusa a mudança se, depois dela, nenhuma conta ativa for administradora.

    Trava a linha do grupo Administrador para serializar mudanças de perfil concorrentes.
    """
    Group.objects.select_for_update().filter(name=GRUPO_ADMINISTRADOR).first()
    continua = conta.is_active and (conta.is_superuser or novo_perfil == GRUPO_ADMINISTRADOR)
    outros = (get_user_model().objects.filter(is_active=True).exclude(pk=conta.pk)
              .filter(Q(is_superuser=True) | Q(groups__name=GRUPO_ADMINISTRADOR)).exists())
    if not (continua or outros):
        raise ValidationError({"perfil": "O sistema precisa ter pelo menos um administrador ativo."})


@transaction.atomic
def cadastrar_colaborador(*, usuario, username, first_name, last_name, email, perfil, senha):
    """Cria a conta ativa, com um perfil e a senha inicial validada pelos AUTH_PASSWORD_VALIDATORS."""
    autor = autorizar_administrador(usuario)
    Usuario = get_user_model()
    conta = Usuario(username=Usuario.normalize_username((username or "").strip()), first_name=first_name.strip(),
                    last_name=last_name.strip(), email=Usuario.objects.normalize_email(email.strip()),
                    is_active=True)
    # A senha é validada à parte; o hash só é calculado depois de tudo validado.
    erros = _erros_dados(conta, exclude=["password"])
    if conta.username and Usuario.objects.filter(username__iexact=conta.username).exists():
        erros.setdefault("username", []).append("Já existe uma conta com este usuário.")
    if perfil not in NOMES_PERFIS:
        erros["perfil"] = ["Escolha um perfil válido."]
    try:
        _validar_senha(senha, conta)
    except ValidationError as erro:
        erros.update(erro.message_dict)
    if erros:
        raise ValidationError(erros)
    conta.set_password(senha)
    conta.save()
    _definir_perfil(conta, perfil)
    _registrar(conta=conta, acao="cadastro", autor=autor, novos=_dados(conta, perfil))
    return conta


@transaction.atomic
def corrigir_colaborador(*, usuario, conta_id, first_name, last_name, email, perfil):
    """Corrige nome, sobrenome, e-mail e perfil. Audita só os campos que mudaram (nada muda, nada grava).

    O administrador não altera o próprio perfil, e nenhuma mudança pode deixar o sistema sem administrador ativo.
    """
    autorizar_administrador(usuario)
    Usuario = get_user_model()
    Group.objects.select_for_update().get(name=GRUPO_ADMINISTRADOR)
    conta = Usuario.objects.select_for_update().get(pk=conta_id)
    autor = autorizar_administrador(usuario)  # de novo sob o lock: o autor pode ter sido rebaixado nesse meio-tempo
    _proteger_superusuario(conta, autor)
    perfil_atual = perfil_de(conta)
    anteriores = _dados(conta, perfil_atual)
    conta.first_name, conta.last_name = first_name.strip(), last_name.strip()
    conta.email = Usuario.objects.normalize_email(email.strip())
    erros = _erros_dados(conta, exclude=["password", "username"], validate_unique=False)
    if erros:
        raise ValidationError(erros)
    if perfil != perfil_atual:
        if conta.pk == autor.pk:
            raise ValidationError({"perfil": "Você não pode alterar o seu próprio perfil."})
        _validar_perfil(perfil)
        garantir_administrador_restante(conta, perfil)
    novos = _dados(conta, perfil)
    mudou = [campo for campo in CAMPOS_CORRECAO if novos[campo] != anteriores[campo]]
    if not mudou:
        return conta
    campos_conta = [campo for campo in mudou if campo != "perfil"]
    if campos_conta:
        conta.save(update_fields=campos_conta)
    if "perfil" in mudou:
        _definir_perfil(conta, perfil)
    _registrar(conta=conta, acao="correcao", autor=autor, anteriores={campo: anteriores[campo] for campo in mudou},
               novos={campo: novos[campo] for campo in mudou})
    return conta


@transaction.atomic
def definir_senha(*, usuario, conta_id, senha):
    """O administrador define uma nova senha para a conta (validada). A auditoria não guarda senha nem hash.

    Trocar a senha encerra as outras sessões da conta (o Django invalida o hash de sessão antigo).
    """
    autorizar_administrador(usuario)
    Group.objects.select_for_update().get(name=GRUPO_ADMINISTRADOR)
    conta = get_user_model().objects.select_for_update().get(pk=conta_id)
    autor = autorizar_administrador(usuario)  # de novo sob o lock
    _proteger_superusuario(conta, autor)
    _validar_senha(senha, conta)
    conta.set_password(senha)
    conta.save(update_fields=["password"])
    _registrar(conta=conta, acao="senha", autor=autor, novos={"senha": "redefinida"})
    return conta


@transaction.atomic
def alterar_situacao_conta(*, usuario, conta_id, ativo):
    """Desativa/reativa preservando ações e revogando as sessões da conta desativada."""
    from django.contrib.sessions.models import Session
    from django.utils import timezone

    autorizar_administrador(usuario)
    if type(ativo) is not bool:
        raise ValidationError("Informe uma situação válida.")
    Group.objects.select_for_update().get(name=GRUPO_ADMINISTRADOR)
    conta = get_user_model().objects.select_for_update().get(pk=conta_id)
    autor = autorizar_administrador(usuario)
    _proteger_superusuario(conta, autor)
    if conta.pk == autor.pk and not ativo:
        raise ValidationError("Você não pode desativar a própria conta.")
    anterior = conta.is_active
    if anterior == ativo:
        return conta
    conta.is_active = ativo
    garantir_administrador_restante(conta, perfil_de(conta))
    conta.save(update_fields=["is_active"])
    if not ativo:
        for sessao in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
            if str(sessao.get_decoded().get("_auth_user_id")) == str(conta.pk):
                sessao.delete()
    _registrar(conta=conta, acao="ativacao" if ativo else "desativacao", autor=autor,
               anteriores={"is_active": anterior}, novos={"is_active": ativo})
    return conta
