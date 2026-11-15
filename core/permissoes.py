"""Autorização comum aos serviços (RNF-SEG-03 e RNF-SEG-04)."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied


def autorizar(usuario, *permissoes, mensagem="Você não tem permissão para esta ação."):
    """Retorna o usuário ativo, reconsultado no banco, se tiver todas as permissões do Django.

    A nova consulta evita autorizar contas desativadas ou permissões antigas em cache.
    """
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        raise PermissionDenied("É necessário entrar com um usuário autorizado.")
    autor = get_user_model().objects.filter(pk=usuario.pk, is_active=True).first()
    if autor is None or not autor.has_perms(permissoes):
        raise PermissionDenied(mensagem)
    return autor
