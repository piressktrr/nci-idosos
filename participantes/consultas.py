"""Consultas de leitura de participantes em lote, para listas e relatórios (RN-PAR-05, RN-FMR-12)."""

from types import MappingProxyType
from typing import Mapping, NamedTuple

from django.db.models import QuerySet

from .models import Participante, SituacaoSocial

STATUS_COM_HISTORICO = ("ativo", "desligado", "afastado")
SITUACOES_PERMANENTES = ("entrada", "reativacao", "afastamento", "retorno")


def _anotar_entrada(consulta):
    from django.db.models import Exists, OuterRef
    from .models import Movimentacao
    entradas = Movimentacao.objects.filter(participante_id=OuterRef("pk"), tipo="entrada")
    return consulta.annotate(tem_entrada=Exists(entradas))


def cadastros_com_historico():
    """RN-FMR-12: base do FMR, os cadastros com movimentação de entrada e status ativo/desligado/afastado.

    Os demais (sem entrada, status legado Inativo ou Cancelado) são pendências a corrigir: ficam fora dos totais
    e são listados por `permanentes_com_pendencias`, sem conversão automática de status.
    """
    return _anotar_entrada(Participante.objects.all()).filter(status__in=STATUS_COM_HISTORICO, tem_entrada=True)


def permanentes_em(*, usuario, data_referencia):
    """Situação no fechamento pela última movimentação na data (inclusive).

    None sinaliza acervo incompleto/ambíguo; nunca pressupõe permanência a partir
    de status atual, presença ou ausência de registros de saída. Mantida por compatibilidade:
    o FMR usa `permanentes_com_pendencias`, que calcula com os cadastros completos e lista os pendentes.
    """
    resultado = permanentes_com_pendencias(usuario=usuario, data_referencia=data_referencia)
    return resultado.permanentes if resultado.completo else None


class PermanentesComPendencias(NamedTuple):
    """Resultado de `permanentes_com_pendencias`: permanentes calculáveis e cadastros que impedem o total."""

    permanentes: tuple  # ParticipanteResumo dos cadastros com histórico completo, permanentes na data
    pendentes: tuple  # ParticipanteResumo dos cadastros sem entrada ou com status legado (fora de `permanentes`)
    # referência -> motivos ("sem entrada", "status Inativo", "status Cancelado") de cada pendente
    motivos: Mapping = MappingProxyType({})

    @property
    def completo(self):
        """True se nenhum cadastro está pendente, ou seja, `permanentes` é o total real da data."""
        return not self.pendentes


def permanentes_com_pendencias(*, usuario, data_referencia):
    """Alternativa a `permanentes_em` que não descarta tudo por causa de um cadastro pendente.

    Mesma regra (última movimentação até a data, inclusive), aplicada só aos cadastros com histórico
    completo (`cadastros_com_historico`); os demais (sem movimentação de entrada ou com status fora de
    ativo/desligado/afastado) voltam em `pendentes`, com o motivo em `motivos`. O FMR calcula com os
    completos e mostra a lista a corrigir; `permanentes_em` continua devolvendo None nesses casos.
    """
    from datetime import date
    from django.core.exceptions import ValidationError
    from django.db.models import OuterRef, Subquery
    from core.integracoes import ParticipanteResumo
    from core.permissoes import autorizar
    from .categorias import StatusParticipante
    from .models import Movimentacao
    autorizar(usuario, "participantes.view_participante")
    if type(data_referencia) is not date:
        raise ValidationError("Informe uma data de referência válida.")
    ultimas = (Movimentacao.objects.filter(participante_id=OuterRef("pk"), data__lte=data_referencia)
               .order_by("-data", "-pk"))
    pessoas = (cadastros_com_historico().annotate(ultima_situacao=Subquery(ultimas.values("tipo")[:1]))
               .filter(ultima_situacao__in=SITUACOES_PERMANENTES).order_by("nome_completo", "pk"))
    permanentes = tuple(ParticipanteResumo(str(pk), nome) for pk, nome in pessoas.values_list("pk", "nome_completo"))
    pendentes, motivos = [], {}
    consulta = (_anotar_entrada(Participante.objects.all()).exclude(status__in=STATUS_COM_HISTORICO, tem_entrada=True)
                .order_by("nome_completo", "pk").values_list("pk", "nome_completo", "status", "tem_entrada"))
    for pk, nome, status, tem_entrada in consulta:
        pendentes.append(ParticipanteResumo(str(pk), nome))
        motivos[str(pk)] = tuple(
            ([] if tem_entrada else ["sem entrada"])
            + ([] if status in STATUS_COM_HISTORICO else [f"status {StatusParticipante(status).label}"]))
    return PermanentesComPendencias(permanentes, tuple(pendentes), MappingProxyType(motivos))


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
