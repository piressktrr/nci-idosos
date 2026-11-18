"""RF-FMR-01: seleção validada do período; sem consultar ou calcular indicadores."""
from calendar import monthrange
from datetime import date

from django.core.exceptions import PermissionDenied, ValidationError

from .permissoes import pode_consultar_fmr


def consultar_periodo_fmr(*, usuario, ano, mes):
    if not pode_consultar_fmr(usuario):
        raise PermissionDenied("Você não tem acesso ao FMR.")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe um ano e mês válidos.")
    return {"inicio": date(ano, mes, 1), "fim": date(ano, mes, monthrange(ano, mes)[1])}
