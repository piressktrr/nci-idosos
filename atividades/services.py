"""Contrato provisório do cadastro RF-ATV-01; usar este serviço para criar atividades."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import Atividade, RegistroCadastroAtividade


@transaction.atomic
def cadastrar_atividade(*, usuario, nome, local, monitor):
    """Cadastra e audita em uma transação; exige atividades.add_atividade."""
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        raise PermissionDenied("É necessário um usuário autorizado para cadastrar atividades.")
    # Consulta atual evita autorizar contas desativadas ou permissões antigas em cache.
    autor = get_user_model().objects.filter(pk=usuario.pk, is_active=True).first()
    if autor is None or not autor.has_perm("atividades.add_atividade"):
        raise PermissionDenied("Você não tem permissão para cadastrar atividades.")

    dados = {"nome": nome, "local": local, "monitor": monitor}
    erros = {campo: "Informe um texto." for campo, valor in dados.items() if not isinstance(valor, str)}
    if erros:
        raise ValidationError(erros)
    dados = {campo: valor.strip() for campo, valor in dados.items()}
    atividade = Atividade(**dados)
    atividade.full_clean()
    atividade.save()
    RegistroCadastroAtividade.objects.create(atividade=atividade, usuario=autor, dados=dados)
    return atividade
