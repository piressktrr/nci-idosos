"""Leitura de aulas por categoria do FMR (RF-FMR-10); só consulta, sem gravar em atividades."""

from calendar import monthrange
from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from core.permissoes import autorizar


def consultar_aulas_por_categoria(*, usuario, ano, mes):
    """RF-FMR-10 (P04, NCI 21/11: a categoria vale para a atividade inteira).

    Cada aula realizada no mês conta na categoria da `ClassificacaoAtividade` vigente na data da aula
    (`Aula.objects.com_categoria_fmr()`, contrato de atividades para o FMR). Participações = presenças
    da origem do provedor ativo, como em `consultar_presencas_mensais`. Aulas canceladas não contam.
    Devolve as linhas por (categoria, nome histórico) e, à parte, as aulas sem categoria vigente.
    """
    from atividades.integracoes.participantes import obter_provedor
    from atividades.models import Aula, CategoriaFMR, Frequencia

    autorizar(usuario, "atividades.view_atividade", "atividades.view_aula", "atividades.view_frequencia")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe um mês e ano válidos.")
    provedor = obter_provedor()
    intervalo = (date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1]))
    presentes = Q(frequencias__situacao=Frequencia.Situacao.PRESENTE,
                  frequencias__inscricao__origem_participante=provedor.origem)
    grupos = (Aula.objects.realizadas().filter(data__range=intervalo).com_categoria_fmr()
              .values("categoria_fmr_id", "categoria_fmr_nome")
              .annotate(aulas=Count("pk", distinct=True), participacoes=Count("frequencias", filter=presentes))
              .order_by("categoria_fmr_nome", "categoria_fmr_id"))
    linhas, sem_categoria = [], {"aulas": 0, "participacoes": 0}
    for grupo in grupos:
        if grupo["categoria_fmr_id"] is None:
            sem_categoria = {"aulas": grupo["aulas"], "participacoes": grupo["participacoes"]}
        else:
            linhas.append({"categoria_id": grupo["categoria_fmr_id"], "categoria": grupo["categoria_fmr_nome"],
                           "aulas": grupo["aulas"], "participacoes": grupo["participacoes"]})
    registradas = {(linha["categoria_id"], linha["categoria"]) for linha in linhas}
    for pk, nome in CategoriaFMR.objects.filter(ativa=True).values_list("pk", "nome"):
        if (pk, nome) not in registradas:
            linhas.append({"categoria_id": pk, "categoria": nome, "aulas": 0, "participacoes": 0})
    linhas.sort(key=lambda linha: (linha["categoria"], linha["categoria_id"]))
    return {"linhas": linhas, "sem_categoria": sem_categoria, "demonstracao": provedor.demonstracao}
