"""RF-ATV-13: classificação temporal; contrato aditivo provisório para FMR.

Aula.objects.com_categoria_fmr() anota categoria_fmr_id/categoria_fmr_nome
pela data de ocorrência. Consumidores de totais devem usar .realizadas().
"""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import OuterRef, Subquery

from core.permissoes import autorizar, autorizar_administrador

from .models import (Atividade, CategoriaFMR, ClassificacaoAtividade,
                     RegistroCategoriaFMR, RegistroClassificacaoAtividade)


def com_categoria_vigente(atividades, data):
    vigencia = ClassificacaoAtividade.objects.filter(atividade_id=OuterRef("pk"), inicio__lte=data).order_by("-inicio")
    return atividades.annotate(classificacao_atual_id=Subquery(vigencia.values("pk")[:1]),
        categoria_atual_id=Subquery(vigencia.values("categoria_id")[:1]),
        categoria_atual_nome=Subquery(vigencia.values("categoria_nome")[:1]))


@transaction.atomic
def salvar_categoria(*, usuario, nome, ativa=True, categoria_id=None):
    autor = autorizar_administrador(usuario)
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
    autor = autorizar(usuario, "atividades.change_atividade")
    if type(inicio) is not date:
        raise ValidationError("Informe uma data de início válida.")
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    categoria = CategoriaFMR.objects.select_for_update().filter(pk=categoria_id).first()
    if categoria is None:
        raise ValidationError("Categoria inexistente.")
    vigente = ClassificacaoAtividade.objects.filter(atividade=atividade, inicio__lte=inicio).first()
    if vigente and vigente.categoria_id == categoria.pk:
        raise ValidationError("Esta atividade já pertence a essa categoria na data escolhida. Selecione outra categoria.")
    classificacao = ClassificacaoAtividade.objects.filter(atividade=atividade, inicio=inicio).first()
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
