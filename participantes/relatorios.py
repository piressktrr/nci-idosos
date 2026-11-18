"""Consultas agregadas do cadastro para o FMR; sem expor dados pessoais."""
from calendar import monthrange
from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Count, OuterRef, Subquery

from core.permissoes import autorizar
from .models import MotivoDesligamento, Movimentacao, Participante
from .regras import idade_em


def desligamentos_por_motivo_mensal(*, usuario, ano, mes):
    """Conta eventos pela data efetiva e descrição histórica, inclusive motivos inativos."""
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    inicio, fim = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    grupos = (Movimentacao.objects.filter(tipo="desligamento", data__range=(inicio, fim))
              .values("motivo_id", "motivo_descricao").annotate(quantidade=Count("pk"))
              .order_by("motivo_descricao", "motivo_id"))
    linhas = [{"motivo_id": grupo["motivo_id"], "descricao": grupo["motivo_descricao"],
               "quantidade": grupo["quantidade"]} for grupo in grupos]
    registrados = {(linha["motivo_id"], linha["descricao"]) for linha in linhas}
    for motivo in MotivoDesligamento.objects.filter(ativo=True).values("pk", "descricao"):
        if (motivo["pk"], motivo["descricao"]) not in registrados:
            linhas.append({"motivo_id": motivo["pk"], "descricao": motivo["descricao"], "quantidade": 0})
    linhas.sort(key=lambda linha: (linha["descricao"], linha["motivo_id"]))
    return {"linhas": linhas, "total": sum(linha["quantidade"] for linha in linhas)}


def movimentacao_etaria_mensal(*, usuario, ano, mes):
    """Idade no primeiro dia; saídas/reativações contam eventos para preservar o balanço."""
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    inicio, fim = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    if (Participante.objects.exclude(status__in=("ativo", "afastado", "desligado")).exists()
            or Participante.objects.exclude(movimentacoes__tipo="entrada").exists()):
        return None
    campos = ("vieram_mes_anterior", "ingressaram", "reativados", "sairam", "permanecem")
    faixas = ("60–64", "65–69", "70–74", "75 anos ou mais")
    linhas = [{"faixa": faixa, "sexo_codigo": codigo, "sexo": sexo, **dict.fromkeys(campos, 0)}
              for faixa in faixas for codigo, sexo in (("M", "Masculino"), ("F", "Feminino"))]
    grupos = {(linha["faixa"], linha["sexo_codigo"]): linha for linha in linhas}
    movimentos = {}
    for pessoa, tipo in Movimentacao.objects.filter(data__range=(inicio, fim)).values_list("participante_id", "tipo"):
        contagens = movimentos.setdefault(pessoa, dict.fromkeys(campos, 0))
        campo = {"entrada": "ingressaram", "reativacao": "reativados", "desligamento": "sairam"}.get(tipo)
        if campo:
            contagens[campo] += 1
    eventos = Movimentacao.objects.filter(participante_id=OuterRef("pk")).order_by("-data", "-pk")
    pessoas = Participante.objects.annotate(
        antes=Subquery(eventos.filter(data__lt=inicio).values("tipo")[:1]),
        depois=Subquery(eventos.filter(data__lte=fim).values("tipo")[:1]),
    ).values("pk", "data_nascimento", "sexo", "antes", "depois")
    ativos = {"entrada", "reativacao", "afastamento", "retorno"}
    fora = dict.fromkeys(campos, 0)
    for pessoa in pessoas:
        idade = idade_em(pessoa["data_nascimento"], inicio)
        faixa = next((rotulo for limite, rotulo in ((75, faixas[3]), (70, faixas[2]), (65, faixas[1]), (60, faixas[0]))
                      if idade >= limite), None)
        valores = movimentos.get(pessoa["pk"], dict.fromkeys(campos, 0)).copy()
        valores["vieram_mes_anterior"] = int(pessoa["antes"] in ativos)
        valores["permanecem"] = int(pessoa["depois"] in ativos)
        destino = grupos[(faixa, pessoa["sexo"])] if faixa else fora
        for campo in campos:
            destino[campo] += valores[campo]
    return {"linhas": linhas, "totais": {campo: sum(linha[campo] for linha in linhas) for campo in campos},
            "fora_faixas": fora, "data_referencia_idade": inicio}
