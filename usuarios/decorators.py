"""Acesso às telas de colaboradores (RN-USR-01)."""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from core.perfis import e_administrador


def administrador_required(view):
    """Anônimo vai para a tela de entrada; logado que não é administrador ativo recebe 403."""

    @wraps(view)
    def envolvida(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        if not e_administrador(request.user):
            raise PermissionDenied("Somente administradores podem gerenciar contas de acesso.")
        return view(request, *args, **kwargs)

    return envolvida
