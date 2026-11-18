"""Consultas agregadas do cadastro para o FMR; sem expor dados pessoais."""
from calendar import monthrange
from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Count, OuterRef, Subquery

from core.permissoes import autorizar
from .categorias import OrigemEncaminhamento
from .consultas import permanentes_em, situacoes_vigentes_em
from .models import MotivoDesligamento, Movimentacao, Participante
from .regras import idade_em


def imigrantes_refugiados_mensal(*, usuario, ano, mes):
    """Conta permanentes com informação social vigente no fechamento; desconhecido não é não."""
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    fim = date(ano, mes, monthrange(ano, mes)[1])
    permanentes = permanentes_em(usuario=usuario, data_referencia=fim)
    if permanentes is None:
        return None
    situacoes = situacoes_vigentes_em(fim, [int(pessoa.referencia) for pessoa in permanentes])
    sem_situacao = sum(situacao is None for situacao in situacoes.values())
    quantidade = sum(situacao.imigrante_refugiado for situacao in situacoes.values() if situacao is not None)
    return {"total_permanentes": len(permanentes), "imigrantes_refugiados": None if sem_situacao else quantidade,
            "sem_situacao": sem_situacao}


def ingressantes_por_encaminhamento_mensal(*, usuario, ano, mes):
    """Origem registrada na entrada; correções do cadastro não reclassificam o ingresso."""
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    if Participante.objects.exclude(movimentacoes__tipo="entrada").exists():
        return None
    inicio, fim = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    grupos = (Movimentacao.objects.filter(tipo="entrada", data__range=(inicio, fim))
              .values("origem_entrada").annotate(quantidade=Count("pk")).order_by("origem_entrada"))
    contagens = {grupo["origem_entrada"]: grupo["quantidade"] for grupo in grupos}
    sem_origem = contagens.get("", 0)
    linhas = [{"codigo": codigo, "origem": rotulo, "quantidade": contagens.get(codigo, 0)}
              for codigo, rotulo in OrigemEncaminhamento.choices if codigo != OrigemEncaminhamento.OUTRA]
    total = sum(linha["quantidade"] for linha in linhas)
    if sem_origem:
        for linha in linhas:
            linha["quantidade"] = None
    return {"linhas": linhas, "total": None if sem_origem else total,
            "total_ingressantes": sum(contagens.values()), "sem_origem": sem_origem,
            "outras_origens": None if sem_origem else contagens.get(OrigemEncaminhamento.OUTRA, 0)}


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
