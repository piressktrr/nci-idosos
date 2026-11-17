"""Variáveis comuns aos templates."""

from django.utils.functional import SimpleLazyObject

from .perfis import e_administrador


def perfil(request):
    """`e_administrador` para o menu e o início (RN-USR-01); só consulta o banco se o template usar."""
    return {"e_administrador": SimpleLazyObject(lambda: e_administrador(getattr(request, "user", None)))}
