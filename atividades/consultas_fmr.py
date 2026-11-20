"""Contrato de leitura de presenças para relatórios; não expõe cadastros pessoais."""

from calendar import monthrange
from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Count, Q

from core.permissoes import autorizar

from .integracoes.participantes import obter_provedor
from .models import Aula, Frequencia


def consultar_presencas_mensais(*, usuario, ano, mes):
    """RF-FMR-03: dias com aulas realizadas, ocorrências e pessoas distintas.

    A identidade é a referência estável do provedor ativo, compartilhada entre
    inscrições em diferentes atividades. O total de únicos do mês não é a soma
    dos únicos de cada dia. Não infere ausências ou dias de funcionamento.
    """
    autorizar(usuario, "atividades.view_atividade", "atividades.view_aula", "atividades.view_frequencia")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe um mês e ano válidos.")
    provedor = obter_provedor()
    intervalo = (date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1]))
    presentes = Q(frequencias__situacao=Frequencia.Situacao.PRESENTE,
                  frequencias__inscricao__origem_participante=provedor.origem)
    dias = list(Aula.objects.realizadas().filter(data__range=intervalo).order_by("data").values("data")
        .annotate(ocorrencias=Count("frequencias", filter=presentes),
                  participantes_unicos=Count("frequencias__inscricao__participante_referencia",
                                             filter=presentes, distinct=True)))
    unicos = Frequencia.objects.filter(
        aula__data__range=intervalo, aula__situacao=Aula.Situacao.REALIZADA,
        situacao=Frequencia.Situacao.PRESENTE, inscricao__origem_participante=provedor.origem,
    ).aggregate(total=Count("inscricao__participante_referencia", distinct=True))["total"]
    return {"dias": dias, "total_ocorrencias": sum(dia["ocorrencias"] for dia in dias),
            "total_participantes_unicos": unicos, "demonstracao": provedor.demonstracao}
