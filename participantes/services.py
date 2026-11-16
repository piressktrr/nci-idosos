"""Serviços do cadastro de participantes (RF-PAR-01, RN-PAR-01), com autorização e auditoria."""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.permissoes import autorizar

from .auditoria import registrar
from .models import Participante
from .regras import chave_nome

CAMPOS_CADASTRO = ("nome_completo", "data_nascimento", "sexo", "raca_cor", "identidade_genero")


def _dados(participante):
    return {
        "nome_completo": participante.nome_completo,
        "data_nascimento": participante.data_nascimento.isoformat(),
        "sexo": participante.sexo,
        "raca_cor": participante.raca_cor,
        "identidade_genero": participante.identidade_genero,
    }


def possiveis_duplicados(*, nome_completo, data_nascimento, excluir_id=None):
    """RN-PAR-01: mesmos nome (sem acento/caixa) e data de nascimento.

    É só um alerta: o documento para identificar duplicidade ainda será escolhido pelo NCI (P18).
    """
    if not isinstance(nome_completo, str) or not data_nascimento:
        return []
    chave = chave_nome(nome_completo)
    candidatos = Participante.objects.filter(data_nascimento=data_nascimento).exclude(pk=excluir_id)
    return [item for item in candidatos if chave_nome(item.nome_completo) == chave]


def _verificar_duplicidade(participante, confirmar_duplicidade, excluir_id=None):
    duplicados = possiveis_duplicados(nome_completo=participante.nome_completo,
                                      data_nascimento=participante.data_nascimento, excluir_id=excluir_id)
    if duplicados and confirmar_duplicidade is not True:
        raise ValidationError(
            "Já existe participante com o mesmo nome e data de nascimento. Confira se é a mesma pessoa; "
            "quem retorna ao serviço deve manter o cadastro existente.",
            code="possivel_duplicado",
        )


@transaction.atomic
def cadastrar_participante(*, usuario, confirmar_duplicidade=False, **dados):
    """RF-PAR-01: cadastra a pessoa uma única vez e audita na mesma transação."""
    autor = autorizar(usuario, "participantes.add_participante",
                      mensagem="Você não tem permissão para cadastrar participantes.")
    if set(dados) != set(CAMPOS_CADASTRO):
        raise ValidationError("Dados de cadastro incompletos ou inválidos.")
    participante = Participante(**dados)
    participante.full_clean()
    _verificar_duplicidade(participante, confirmar_duplicidade)
    participante.save()
    registrar(participante=participante, acao="cadastro", usuario=autor, novos=_dados(participante))
    return participante


@transaction.atomic
def corrigir_participante(*, usuario, participante_id, confirmar_duplicidade=False, **dados):
    """Corrige o cadastro (inclusive raça/cor e identidade de gênero), guardando antes e depois."""
    autor = autorizar(usuario, "participantes.change_participante",
                      mensagem="Você não tem permissão para corrigir participantes.")
    if set(dados) != set(CAMPOS_CADASTRO):
        raise ValidationError("Dados de cadastro incompletos ou inválidos.")
    participante = Participante.objects.select_for_update().get(pk=participante_id)
    anteriores = _dados(participante)
    for campo, valor in dados.items():
        setattr(participante, campo, valor)
    participante.full_clean()
    if _dados(participante) == anteriores:
        return participante
    _verificar_duplicidade(participante, confirmar_duplicidade, excluir_id=participante.pk)
    participante.save(update_fields=list(CAMPOS_CADASTRO))
    registrar(participante=participante, acao="correcao", usuario=autor,
              anteriores=anteriores, novos=_dados(participante))
    return participante
