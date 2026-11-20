"""Consultas de leitura de atividades para o histórico do participante (RF-PAR-10).

Somente leitura; não importa participantes: a pessoa é identificada pelo par
(origem, referência) gravado na inscrição (ver participantes/provedor.py).
"""

from django.db.models import Count, Q
from django.urls import reverse

from core.permissoes import autorizar

from .models import Aula, Frequencia, Inscricao

# Mesmas permissões exigidas por atividades:historico_participante.
PERMISSOES_HISTORICO_FREQUENCIA = (
    "atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao", "atividades.view_frequencia",
)

# Inscricao ainda não tem campo de situação (sem desligamento/cancelamento modelado):
# toda inscrição existente é exibida como vigente.
SITUACAO_INSCRICAO = "Inscrito(a)"


def _contar(situacao):
    # Como em consultar_historico_participante, só contam aulas realizadas.
    return Count("frequencias", filter=Q(frequencias__situacao=situacao,
                                          frequencias__aula__situacao=Aula.Situacao.REALIZADA))


def frequencia_do_participante(*, usuario, origem, referencia):
    """Totais de frequência por inscrição da pessoa (origem, referência), em uma única consulta agregada.

    Levanta PermissionDenied sem as permissões do histórico de frequência de atividades.
    """
    autorizar(usuario, *PERMISSOES_HISTORICO_FREQUENCIA,
              mensagem="Você não tem permissão para ver a frequência em atividades.")
    linhas = (Inscricao.objects
              .filter(origem_participante=origem, participante_referencia=str(referencia))
              .annotate(presentes=_contar(Frequencia.Situacao.PRESENTE),
                        ausentes=_contar(Frequencia.Situacao.AUSENTE),
                        justificados=_contar(Frequencia.Situacao.JUSTIFICADO))
              .order_by("atividade__nome", "atividade_id", "pk")
              .values("pk", "atividade_id", "atividade__nome", "cadastrada_em",
                      "presentes", "ausentes", "justificados"))
    return [{
        "inscricao_id": linha["pk"],
        "atividade_id": linha["atividade_id"],
        "atividade_nome": linha["atividade__nome"],
        "situacao": SITUACAO_INSCRICAO,
        "inscrita_em": linha["cadastrada_em"],
        "presentes": linha["presentes"],
        "ausentes": linha["ausentes"],
        "justificados": linha["justificados"],
        "total": linha["presentes"] + linha["ausentes"] + linha["justificados"],
        "url_historico": reverse("atividades:historico_participante", kwargs={
            "atividade_id": linha["atividade_id"], "inscricao_id": linha["pk"]}),
    } for linha in linhas]
