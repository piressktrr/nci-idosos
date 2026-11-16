"""Consultas de leitura de participantes em lote, para listas e relatórios (RN-PAR-05, RN-FMR-12)."""

from django.db.models import QuerySet

from .models import Participante, SituacaoSocial


def _pks(participantes):
    if participantes is None:
        return list(Participante.objects.values_list("pk", flat=True))
    if isinstance(participantes, QuerySet):
        return list(participantes.values_list("pk", flat=True))
    return [getattr(item, "pk", item) for item in participantes]


def situacoes_vigentes_em(data, participantes=None):
    """Situação social que valia na data para cada participante: {pk: SituacaoSocial ou None}.

    Mesma regra de `SituacaoSocial.vigente_em` (a de maior `vigente_desde` até a data), em no máximo duas
    consultas, qualquer que seja o número de participantes. `participantes` pode ser um queryset, uma lista de
    participantes ou de pks; sem ele, considera todos os cadastrados. None = ainda sem registro na data.
    """
    pks = _pks(participantes)
    if not pks:
        return {}
    # DISTINCT ON (PostgreSQL): a primeira linha de cada participante na ordem de vigência decrescente.
    vigentes = (SituacaoSocial.objects.filter(participante_id__in=pks, vigente_desde__lte=data)
                .order_by("participante_id", "-vigente_desde").distinct("participante_id"))
    resultado = dict.fromkeys(pks)
    resultado.update({situacao.participante_id: situacao for situacao in vigentes})
    return resultado
