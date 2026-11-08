"""RF-ATV-13: classificação temporal; contrato aditivo provisório para FMR.

Aula.objects.com_categoria_fmr() anota categoria_fmr_id/categoria_fmr_nome
pela data de ocorrência. Consumidores de totais devem usar .realizadas().
"""
from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import (Atividade, CategoriaFMR, ClassificacaoAtividade,
                     RegistroCategoriaFMR, RegistroClassificacaoAtividade)


def autorizar(usuario, *, catalogo=False):
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        raise PermissionDenied
    autor = get_user_model().objects.filter(pk=usuario.pk, is_active=True).first()
    if autor is None or (not autor.is_superuser if catalogo else not autor.has_perm("atividades.change_atividade")):
        raise PermissionDenied
    return autor


@transaction.atomic
def salvar_categoria(*, usuario, nome, ativa=True, categoria_id=None):
    autor = autorizar(usuario, catalogo=True)
    if not isinstance(nome, str) or not nome.strip() or len(nome.strip()) > 150 or type(ativa) is not bool:
        raise ValidationError("Informe nome válido (até 150 caracteres) e situação da categoria.")
    categoria = CategoriaFMR.objects.select_for_update().get(pk=categoria_id) if categoria_id is not None else CategoriaFMR()
    anteriores = {"nome": categoria.nome, "ativa": categoria.ativa} if categoria.pk else None
    novos = {"nome": nome.strip(), "ativa": ativa}
    if anteriores == novos:
        return categoria
    categoria.nome, categoria.ativa = novos["nome"], ativa
    categoria.full_clean()
    categoria.save()
    RegistroCategoriaFMR.objects.create(categoria=categoria, usuario=autor, anteriores=anteriores, novos=novos)
    return categoria


@transaction.atomic
def classificar_atividade(*, usuario, atividade_id, categoria_id, inicio):
    autor = autorizar(usuario)
    if type(inicio) is not date:
        raise ValidationError("Informe uma data de início válida.")
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    categoria = CategoriaFMR.objects.select_for_update().filter(pk=categoria_id).first()
    if categoria is None:
        raise ValidationError("Categoria inexistente.")
    classificacao = ClassificacaoAtividade.objects.filter(atividade=atividade, inicio=inicio).first()
    if classificacao and classificacao.categoria_id == categoria.pk:
        return classificacao
    if not categoria.ativa:
        raise ValidationError("Selecione uma categoria ativa para o novo vínculo.")
    anteriores = None if classificacao is None else {
        "categoria_id": classificacao.categoria_id, "categoria_nome": classificacao.categoria_nome,
        "inicio": classificacao.inicio.isoformat()}
    if classificacao is None:
        classificacao = ClassificacaoAtividade(atividade=atividade, inicio=inicio)
    classificacao.categoria, classificacao.categoria_nome = categoria, categoria.nome
    classificacao.full_clean()
    classificacao.save()
    RegistroClassificacaoAtividade.objects.create(classificacao=classificacao, usuario=autor, anteriores=anteriores,
        novos={"categoria_id": categoria.pk, "categoria_nome": categoria.nome, "inicio": inicio.isoformat()})
    return classificacao
