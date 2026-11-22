"""Consultas agregadas do cadastro para o FMR; sem expor dados pessoais."""
from calendar import monthrange
from collections import Counter
from datetime import date

from django.core.exceptions import ValidationError
from django.db.models import Count, OuterRef, Q, Subquery

from core.permissoes import autorizar
from .categorias import OrigemEncaminhamento
from .consultas import cadastros_com_historico, permanentes_com_pendencias, situacoes_vigentes_em
from .models import MotivoDesligamento, Movimentacao, PerfilDemografico
from .regras import idade_em


def _ate_meses(inicio, fim, meses):
    indice = (inicio.year - 1) * 12 + inicio.month - 1 + meses
    ano, mes = divmod(indice, 12)
    ano, mes = ano + 1, mes + 1
    if ano > 9999:
        return True
    limite = date(ano, mes, min(inicio.day, monthrange(ano, mes)[1]))
    return fim <= limite


def _permanentes_completos(usuario, data):
    """RN-FMR-12: permanentes entre os cadastros completos; os pendentes são listados pelo FMR, não anulam o mês."""
    return permanentes_com_pendencias(usuario=usuario, data_referencia=data).permanentes


def tempo_permanencia_desligamentos_mensal(*, usuario, ano, mes):
    """RF-FMR-14: meses de calendário no vínculo encerrado, sem somar ciclos anteriores."""
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    inicio, fim = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    anteriores = (Movimentacao.objects.filter(participante_id=OuterRef("participante_id"),
                    tipo__in=("entrada", "reativacao", "desligamento"))
        .filter(Q(data__lt=OuterRef("data")) | Q(data=OuterRef("data"), pk__lt=OuterRef("pk")))
        .order_by("-data", "-pk"))
    saidas = list(Movimentacao.objects.filter(tipo="desligamento", data__range=(inicio, fim))
        .annotate(inicio_vinculo=Subquery(anteriores.values("data")[:1]),
                  tipo_anterior=Subquery(anteriores.values("tipo")[:1]))
        .order_by("data", "pk").values("data", "inicio_vinculo", "tipo_anterior"))
    linhas = [{"faixa": faixa, "quantidade": 0} for faixa in (
        "Até 6 meses", "Entre 6 meses a 1 ano", "Entre 1 ano a 3 anos", "Mais de 3 anos")]
    sem_periodo = 0
    for saida in saidas:
        if saida["tipo_anterior"] not in ("entrada", "reativacao") or saida["inicio_vinculo"] is None:
            sem_periodo += 1
            continue
        faixa = next((indice for indice, meses in enumerate((6, 12, 36))
                      if _ate_meses(saida["inicio_vinculo"], saida["data"], meses)), 3)
        linhas[faixa]["quantidade"] += 1
    if sem_periodo:
        for linha in linhas:
            linha["quantidade"] = None
    return {"linhas": linhas, "total": None if sem_periodo else len(saidas),
            "total_desligamentos": len(saidas), "sem_periodo": sem_periodo}


def indicadores_sociais_mensal(*, usuario, ano, mes):
    """RF-FMR-09: pessoas permanentes e situação social vigente no fechamento."""
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    fim = date(ano, mes, monthrange(ano, mes)[1])
    permanentes = _permanentes_completos(usuario, fim)
    situacoes = situacoes_vigentes_em(fim, [int(pessoa.referencia) for pessoa in permanentes])
    sem_situacao = sum(situacao is None for situacao in situacoes.values())
    totais = dict.fromkeys(("moram_sozinhos", "moram_sozinhos_com_apoio", "possuem_deficiencia", "recebem_bpc"), None)
    if not sem_situacao:
        valores = list(situacoes.values())
        totais = {
            "moram_sozinhos": sum(s.mora_sozinho for s in valores),
            "moram_sozinhos_com_apoio": sum(s.mora_sozinho and s.tem_apoio for s in valores),
            "possuem_deficiencia": sum(s.possui_deficiencia for s in valores),
            "recebem_bpc": sum(s.recebe_bpc for s in valores),
        }
    return {"total_permanentes": len(permanentes), "sem_situacao": sem_situacao, "totais": totais}


def perfil_demografico_em(*, usuario, data):
    """Conta os perfis vigentes no fechamento, preservando meses com histórico incompleto."""
    permanentes = _permanentes_completos(usuario, data)
    perfis = list(PerfilDemografico.objects.filter(
        participante_id__in=[int(pessoa.referencia) for pessoa in permanentes], vigente_desde__lte=data)
        .order_by("participante_id", "-vigente_desde").distinct("participante_id")
        .values_list("sexo", "raca_cor", "identidade_genero"))
    if len(perfis) != len(permanentes):
        return None
    return {
        "sexo_raca": Counter((sexo, raca) for sexo, raca, _ in perfis),
        "genero": Counter(genero for _, _, genero in perfis),
    }


def imigrantes_refugiados_mensal(*, usuario, ano, mes):
    """Conta permanentes com informação social vigente no fechamento; desconhecido não é não."""
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    fim = date(ano, mes, monthrange(ano, mes)[1])
    permanentes = _permanentes_completos(usuario, fim)
    situacoes = situacoes_vigentes_em(fim, [int(pessoa.referencia) for pessoa in permanentes])
    sem_situacao = sum(situacao is None for situacao in situacoes.values())
    quantidade = sum(situacao.imigrante_refugiado for situacao in situacoes.values() if situacao is not None)
    return {"total_permanentes": len(permanentes), "imigrantes_refugiados": None if sem_situacao else quantidade,
            "sem_situacao": sem_situacao}


def ingressantes_por_encaminhamento_mensal(*, usuario, ano, mes):
    """Origem registrada na entrada; correções do cadastro não reclassificam o ingresso.

    RN-FMR-12: só os cadastros completos (`cadastros_com_historico`), a mesma base dos demais blocos do FMR;
    os pendentes (sem entrada, Inativo, Cancelado) são listados na tela em vez de anular o mês.
    """
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    inicio, fim = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    grupos = (Movimentacao.objects.filter(tipo="entrada", data__range=(inicio, fim),
                                          participante__in=cadastros_com_historico().values("pk"))
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
    """RF-FMR-05: idade no dia 1; saídas/reativações contam eventos para preservar o balanço.

    - Sexo: o do `PerfilDemografico` vigente no último dia do mês, a mesma data da tabela Sexo×Raça
      (`perfil_demografico_em`), não o sexo atual do cadastro (RN-FMR-12). Se faltar perfil vigente para alguém
      que entra na tabela, as células ficam None (pendência), nunca zero (`sem_perfil`).
    - Menores de 60 anos no dia 1 não têm faixa no FMR: vão para `fora_faixas` (provável erro de cadastro,
      `menores_60` pessoas) e continuam nos demais blocos; tabela + fora = total dos outros blocos.
    - Base: só os cadastros completos (`cadastros_com_historico`); os pendentes são listados pelo FMR.
    """
    autorizar(usuario, "participantes.view_participante")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe ano e mês válidos.")
    inicio, fim = date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])
    base = cadastros_com_historico()
    campos = ("vieram_mes_anterior", "ingressaram", "reativados", "sairam", "permanecem")
    faixas = ("60–64", "65–69", "70–74", "75 anos ou mais")
    linhas = [{"faixa": faixa, "sexo_codigo": codigo, "sexo": sexo, **dict.fromkeys(campos, 0)}
              for faixa in faixas for codigo, sexo in (("M", "Masculino"), ("F", "Feminino"))]
    grupos = {(linha["faixa"], linha["sexo_codigo"]): linha for linha in linhas}
    movimentos = {}
    for pessoa, tipo in (Movimentacao.objects.filter(data__range=(inicio, fim), participante__in=base.values("pk"))
                         .values_list("participante_id", "tipo")):
        contagens = movimentos.setdefault(pessoa, dict.fromkeys(campos, 0))
        campo = {"entrada": "ingressaram", "reativacao": "reativados", "desligamento": "sairam"}.get(tipo)
        if campo:
            contagens[campo] += 1
    eventos = Movimentacao.objects.filter(participante_id=OuterRef("pk")).order_by("-data", "-pk")
    perfil = (PerfilDemografico.objects.filter(participante_id=OuterRef("pk"), vigente_desde__lte=fim)
              .order_by("-vigente_desde"))
    pessoas = base.annotate(
        antes=Subquery(eventos.filter(data__lt=inicio).values("tipo")[:1]),
        depois=Subquery(eventos.filter(data__lte=fim).values("tipo")[:1]),
        sexo_vigente=Subquery(perfil.values("sexo")[:1]),
    ).values("pk", "data_nascimento", "sexo_vigente", "antes", "depois")
    ativos = {"entrada", "reativacao", "afastamento", "retorno"}
    fora = dict.fromkeys(campos, 0)
    menores_60 = sem_perfil = 0
    for pessoa in pessoas:
        valores = movimentos.get(pessoa["pk"], dict.fromkeys(campos, 0)).copy()
        valores["vieram_mes_anterior"] = int(pessoa["antes"] in ativos)
        valores["permanecem"] = int(pessoa["depois"] in ativos)
        if not any(valores.values()):
            continue  # Sem vínculo nem movimentação no mês: não entra no FMR.
        idade = idade_em(pessoa["data_nascimento"], inicio)
        faixa = next((rotulo for limite, rotulo in ((75, faixas[3]), (70, faixas[2]), (65, faixas[1]), (60, faixas[0]))
                      if idade >= limite), None)
        if faixa is None:
            menores_60 += 1
            destino = fora
        elif pessoa["sexo_vigente"] not in ("M", "F"):
            sem_perfil += 1
            continue
        else:
            destino = grupos[(faixa, pessoa["sexo_vigente"])]
        for campo in campos:
            destino[campo] += valores[campo]
    if sem_perfil:
        for linha in linhas:
            linha.update(dict.fromkeys(campos))
        totais = dict.fromkeys(campos)
    else:
        totais = {campo: sum(linha[campo] for linha in linhas) for campo in campos}
    return {"linhas": linhas, "totais": totais, "fora_faixas": fora, "menores_60": menores_60,
            "sem_perfil": sem_perfil, "data_referencia_idade": inicio, "data_referencia_sexo": fim}
