"""Criação da aula e lançamento de sua chamada na mesma transação."""
from django.core.exceptions import ValidationError
from django.db import transaction

from core.permissoes import autorizar
from .integracoes.participantes import obter_provedor
from .models import Atividade
from .services import registrar_aula, registrar_frequencias

PERMISSOES = ("atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao",
              "atividades.view_frequencia", "atividades.add_aula", "atividades.add_frequencia")


def preparar_chamada(*, usuario, atividade_id, data=None):
    autorizar(usuario, *PERMISSOES)
    atividade = Atividade.objects.get(pk=atividade_id)
    provedor = obter_provedor()
    nomes = {p.referencia: p.nome for p in provedor.listar()}
    from django.utils import timezone
    estados = getattr(provedor, "situacoes_em", lambda data: {})(data or timezone.localdate())
    participantes = [{"inscricao_id": i.pk, "referencia": i.participante_referencia,
        "nome": nomes.get(i.participante_referencia, "Participante indisponível"),
        "afastado": estados.get(i.participante_referencia) == "afastamento",
        "disponivel": i.participante_referencia in nomes, "frequencia": None}
        for i in atividade.inscricoes.filter(origem_participante=provedor.origem)
        if estados.get(i.participante_referencia) not in ("desligamento", "nao_ingressou")]
    participantes.sort(key=lambda p: (p["nome"].casefold(), p["referencia"]))
    return atividade, participantes, provedor.demonstracao


@transaction.atomic
def salvar_chamada(*, usuario, atividade_id, dados_aula, registros, justificativas=None):
    """RF-ATV-03/07: cria a aula realizada e lança a chamada na mesma transação.

    `registros` pode omitir inscrições: na chamada retroativa, quem ainda não fazia parte da turma na data fica sem
    situação e não recebe frequência. As situações informadas precisam ser de inscrições listadas nesta chamada.
    """
    autorizar(usuario, *PERMISSOES)
    Atividade.objects.select_for_update().get(pk=atividade_id)
    _, participantes, _ = preparar_chamada(usuario=usuario, atividade_id=atividade_id, data=dados_aula.get("data"))
    if not participantes:
        raise ValidationError("Inscreva participantes nesta atividade antes de realizar a chamada.")
    if any(not p["disponivel"] for p in participantes):
        raise ValidationError("Há participante indisponível. Confira as inscrições antes de salvar.")
    if not isinstance(registros, dict) or not set(registros) <= {p["inscricao_id"] for p in participantes}:
        raise ValidationError("Confira a situação de todos os participantes. As inscrições podem ter mudado; atualize a tela.")
    if not registros:
        raise ValidationError("Selecione a situação de ao menos um participante.")
    aula = registrar_aula(usuario=usuario, atividade_id=atividade_id, **dados_aula)
    registrar_frequencias(usuario=usuario, atividade_id=atividade_id, aula_id=aula.pk,
        registros=registros, justificativas=justificativas)
    return aula
