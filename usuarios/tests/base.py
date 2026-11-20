"""Apoio aos testes de colaboradores. Dados fictícios (RN-SEG-02)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group

from core.perfis import GRUPO_ADMINISTRADOR, GRUPO_EQUIPE

# Senha fictícia que passa nos AUTH_PASSWORD_VALIDATORS (10+ caracteres, não comum, não numérica).
SENHA_VALIDA = "Girassol-Ficticio-2026"
OUTRA_SENHA_VALIDA = "Jabuticaba-Ficticia-77"


def conta(username, *grupos, **extra):
    # RF-USR-05: toda conta tem e-mail (fictício), para poder recuperar a senha.
    extra.setdefault("email", f"{username}@example.org")
    usuario = get_user_model().objects.create_user(username=username, **extra)
    if grupos:
        usuario.groups.add(*Group.objects.filter(name__in=grupos))
    return usuario


def administrador(username="admin_colab_ficticio", **extra):
    return conta(username, GRUPO_ADMINISTRADOR, **{"first_name": "Beatriz"} | extra)


def equipe(username="equipe_colab_ficticia", **extra):
    return conta(username, GRUPO_EQUIPE, **{"first_name": "Carlos"} | extra)


def dados_cadastro(**alterar):
    return {"username": "nova_colab_ficticia", "first_name": "Maria", "last_name": "Fictícia",
            "email": "maria.ficticia@example.org", "perfil": GRUPO_EQUIPE, "senha": SENHA_VALIDA} | alterar
