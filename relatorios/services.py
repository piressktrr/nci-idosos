"""Consultas mensais do FMR, usando os serviços de leitura das áreas de origem."""
from calendar import monthrange
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError

from atividades.services import consultar_frequencia_mensal

from .permissoes import pode_consultar_fmr


def consultar_periodo_fmr(*, usuario, ano, mes):
    if not pode_consultar_fmr(usuario):
        raise PermissionDenied("Você não tem acesso ao FMR.")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe um ano e mês válidos.")
    return {"inicio": date(ano, mes, 1), "fim": date(ano, mes, monthrange(ano, mes)[1])}


def consultar_indicadores_fmr(*, usuario, ano, mes):
    """RF-FMR-02: compõe somente totais já disponíveis, sem acessar modelos externos.

    Conserva a autorização do serviço de frequência e não publica dados do
    placeholder como indicadores. Ausência de acesso/dados reais não vira zero.
    """
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"periodo": periodo, "indicadores": [], "aviso": ""}
    try:
        frequencia = consultar_frequencia_mensal(usuario=usuario, ano=ano, mes=mes)
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui as permissões para consultar os indicadores de frequência."
        return resultado
    if frequencia["demonstracao"]:
        resultado["aviso"] = "Os indicadores precisam da integração real de participantes; dados de demonstração não são utilizados no FMR."
        return resultado
    totais = frequencia["totais"]
    resultado["indicadores"] = [
        {"codigo": "aulas_realizadas", "nome": "Aulas realizadas", "valor": totais["aulas_realizadas"],
         "descricao": "Aulas realizadas no mês, excluindo as canceladas."},
        {"codigo": "participacoes", "nome": "Participações por presença", "valor": totais["presentes"],
         "descricao": "Uma ocorrência por presença em aula; a mesma pessoa pode contar mais de uma vez no mês."},
    ]
    return resultado
