"""Decorators de acesso comuns às telas (RN-USR-01)."""

from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .perfis import e_administrador


def exige_administrador(mensagem="Somente administradores podem realizar esta ação."):
    """Anônimo vai para a tela de entrada; logado que não é administrador ativo recebe 403."""

    def decorator(view):
        @wraps(view)
        def envolvida(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not e_administrador(request.user):
                raise PermissionDenied(mensagem)
            return view(request, *args, **kwargs)

        return envolvida

    return decorator


administrador_required = exige_administrador()
