"""Consultas de leitura de participantes em lote, para listas e relatórios (RN-PAR-05, RN-FMR-12)."""

from typing import NamedTuple

from django.db.models import QuerySet

from .models import Participante, SituacaoSocial

STATUS_COM_HISTORICO = ("ativo", "desligado", "afastado")
SITUACOES_PERMANENTES = ("entrada", "reativacao", "afastamento", "retorno")


def permanentes_em(*, usuario, data_referencia):
    """Situação no fechamento pela última movimentação na data (inclusive).

    None sinaliza acervo incompleto/ambíguo; nunca pressupõe permanência a partir
    de status atual, presença ou ausência de registros de saída.
    """
    from datetime import date
    from django.core.exceptions import ValidationError
    from django.db.models import OuterRef, Subquery
    from core.integracoes import ParticipanteResumo
    from core.permissoes import autorizar
    from .models import Movimentacao
    autorizar(usuario, "participantes.view_participante")
    if type(data_referencia) is not date:
        raise ValidationError("Informe uma data de referência válida.")
    if (Participante.objects.exclude(status__in=("ativo", "desligado", "afastado")).exists()
            or Participante.objects.exclude(movimentacoes__tipo="entrada").exists()):
        return None
    ultimas = Movimentacao.objects.filter(participante_id=OuterRef("pk"), data__lte=data_referencia).order_by("-data", "-pk")
    pessoas = Participante.objects.annotate(ultima_situacao=Subquery(ultimas.values("tipo")[:1])).filter(
        ultima_situacao__in=("entrada", "reativacao", "afastamento", "retorno")).order_by("nome_completo", "pk")
    return tuple(ParticipanteResumo(str(pk), nome) for pk, nome in pessoas.values_list("pk", "nome_completo"))


class PermanentesComPendencias(NamedTuple):
    """Resultado de `permanentes_com_pendencias`: permanentes calculáveis e cadastros que impedem o total."""

    permanentes: tuple  # ParticipanteResumo dos cadastros com histórico completo, permanentes na data
    pendentes: tuple  # ParticipanteResumo dos cadastros sem entrada ou com status legado (fora de `permanentes`)

    @property
    def completo(self):
        """True se nenhum cadastro está pendente, ou seja, `permanentes` é o total real da data."""
        return not self.pendentes


def permanentes_com_pendencias(*, usuario, data_referencia):
    """Alternativa a `permanentes_em` que não descarta tudo por causa de um cadastro pendente.

    Mesma regra (última movimentação até a data, inclusive), aplicada só aos cadastros com histórico
    completo; os demais (sem movimentação de entrada ou com status fora de ativo/desligado/afastado) voltam em
    `pendentes`, para quem chama decidir: mostrar o total parcial com a lista a corrigir ou recusar o total.
    `permanentes_em` continua devolvendo None nesses casos (contrato usado pelo FMR).
    """
    from datetime import date
    from django.core.exceptions import ValidationError
    from django.db.models import Exists, OuterRef, Q, Subquery
    from core.integracoes import ParticipanteResumo
    from core.permissoes import autorizar
    from .models import Movimentacao
    autorizar(usuario, "participantes.view_participante")
    if type(data_referencia) is not date:
        raise ValidationError("Informe uma data de referência válida.")
    com_entrada = Exists(Movimentacao.objects.filter(participante_id=OuterRef("pk"), tipo="entrada"))
    pendente = ~Q(status__in=STATUS_COM_HISTORICO) | ~Q(tem_entrada=True)
    base = Participante.objects.annotate(tem_entrada=com_entrada)
    ultimas = Movimentacao.objects.filter(participante_id=OuterRef("pk"), data__lte=data_referencia).order_by("-data", "-pk")
    pessoas = (base.exclude(pendente).annotate(ultima_situacao=Subquery(ultimas.values("tipo")[:1]))
               .filter(ultima_situacao__in=SITUACOES_PERMANENTES).order_by("nome_completo", "pk"))

    def resumos(consulta):
        return tuple(ParticipanteResumo(str(pk), nome)
                     for pk, nome in consulta.order_by("nome_completo", "pk").values_list("pk", "nome_completo"))

    return PermanentesComPendencias(resumos(pessoas), resumos(base.filter(pendente)))


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
