"""A seleção do período é leitura para os perfis NCI existentes, sem novos perfis."""
from django.contrib.auth import get_user_model
from django.db.models import Q

from core.perfis import GRUPO_ADMINISTRADOR, GRUPO_EQUIPE


def pode_consultar_fmr(usuario):
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        return False
    return (get_user_model().objects.filter(pk=usuario.pk, is_active=True)
            .filter(Q(is_superuser=True) | Q(groups__name__in=(GRUPO_EQUIPE, GRUPO_ADMINISTRADOR))).exists())
