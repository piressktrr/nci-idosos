"""Perfis de acesso (RF-USR-02, RN-USR-02, RNF-SEG-04): grupos "Equipe" e "Administrador".

Os grupos são garantidos por `garantir_perfis`, chamada no `post_migrate` (ligado em CoreConfig.ready) e pelo
comando `manage.py garantir_perfis`. Não é data migration porque as permissões do Django só são criadas no
post_migrate. A rotina só acrescenta o mínimo de cada perfil: permissões dadas à mão aos grupos são mantidas.

Administrador recebe as permissões operacionais de participantes e atividades,
inclusive aulas, inscrições, frequência e lista de espera.

Critério de administrador: `e_administrador` (ativo e superusuário ou membro de "Administrador").
Isso não altera is_staff/is_superuser nem a proteção das contas de superusuários.
"""

from django.apps import apps as global_apps
from django.contrib.auth import get_user_model
from django.contrib.auth.management import create_permissions
from django.db import DEFAULT_DB_ALIAS, router, transaction
from django.db.models import Q

GRUPO_EQUIPE = "Equipe"
GRUPO_ADMINISTRADOR = "Administrador"

# Usuário comum: consulta, cadastra e corrige participantes (inclui situação social e histórico).
PERMISSOES_EQUIPE = (
    "participantes.view_participante",
    "participantes.add_participante",
    "participantes.change_participante",
)
# Administrador: todas as permissões destes apps (inclusive de modelos futuros) mais as listadas abaixo.
APPS_COMPLETOS_ADMINISTRADOR = ("participantes", "atividades")
# Contas e grupos sem "delete": desativar conta preserva o histórico (RF-USR-04).
PERMISSOES_ADMINISTRADOR = (
    "auth.view_user", "auth.add_user", "auth.change_user",
    "auth.view_group", "auth.add_group", "auth.change_group",
)

# grupo -> (apps com todas as permissões, permissões avulsas "app_label.codename")
PERFIS = {
    GRUPO_EQUIPE: ((), PERMISSOES_EQUIPE),
    GRUPO_ADMINISTRADOR: (APPS_COMPLETOS_ADMINISTRADOR, PERMISSOES_ADMINISTRADOR),
}


def _apps_envolvidos():
    rotulos = set()
    for apps_completos, permissoes in PERFIS.values():
        rotulos.update(apps_completos)
        rotulos.update(nome.split(".", 1)[0] for nome in permissoes)
    return sorted(rotulos)


def _permissoes(Permission, using, apps_completos, nomes):
    filtro = Q(content_type__app_label__in=apps_completos) if apps_completos else Q(pk__in=[])
    for nome in nomes:
        app_label, codename = nome.split(".", 1)
        filtro |= Q(content_type__app_label=app_label, codename=codename)
    encontradas = list(Permission.objects.using(using).filter(filtro).select_related("content_type"))
    faltando = set(nomes) - {f"{p.content_type.app_label}.{p.codename}" for p in encontradas}
    if faltando:
        raise LookupError(f"Permissões inexistentes nos perfis de acesso: {', '.join(sorted(faltando))}.")
    return encontradas


def garantir_perfis(*, using=DEFAULT_DB_ALIAS, apps=global_apps):
    """Cria os grupos que faltam e acrescenta as permissões mínimas de cada um (idempotente).

    Retorna {nome_do_grupo: (criado, quantidade_de_permissoes_acrescentadas)};
    {} se algum app dos perfis não estiver migrado.
    """
    try:
        Group = apps.get_model("auth", "Group")
        Permission = apps.get_model("auth", "Permission")
        for rotulo in _apps_envolvidos():
            apps.get_app_config(rotulo)
    except LookupError:  # migrate parcial: algum app dos perfis ainda não está no estado das migrations
        return {}
    if not router.allow_migrate_model(using, Group):
        return {}
    # O post_migrate do core roda antes do dos outros apps (ordem de INSTALLED_APPS): garante as permissões.
    for rotulo in _apps_envolvidos():
        create_permissions(global_apps.get_app_config(rotulo), verbosity=0, using=using, apps=apps)
    resultado = {}
    with transaction.atomic(using=using):
        for nome, (apps_completos, permissoes) in PERFIS.items():
            grupo, criado = Group.objects.using(using).get_or_create(name=nome)
            minimas = _permissoes(Permission, using, apps_completos, permissoes)
            atuais = set(grupo.permissions.values_list("pk", flat=True))
            novas = [p for p in minimas if p.pk not in atuais]
            grupo.permissions.add(*novas)
            resultado[nome] = (criado, len(novas))
    return resultado


def garantir_perfis_pos_migrate(sender, using=DEFAULT_DB_ALIAS, apps=global_apps, **kwargs):
    """Receptor de post_migrate (ligado só para o app core)."""
    garantir_perfis(using=using, apps=apps)


def e_administrador(usuario):
    """Critério único de administrador: conta ativa e superusuário ou membro do grupo Administrador.

    Reconsulta o banco, como core.permissoes.autorizar, para não aceitar conta desativada ou grupo removido.
    """
    if not usuario or not getattr(usuario, "is_authenticated", False) or usuario.pk is None:
        return False
    return (get_user_model().objects.filter(pk=usuario.pk, is_active=True)
            .filter(Q(is_superuser=True) | Q(groups__name=GRUPO_ADMINISTRADOR)).exists())
