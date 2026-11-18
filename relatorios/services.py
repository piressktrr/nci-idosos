"""Consultas mensais do FMR, usando os serviços de leitura das áreas de origem."""
from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError

from atividades.consultas_fmr import consultar_presencas_mensais
from atividades.services import consultar_frequencia_mensal
from core.permissoes import autorizar

from .integracoes import participantes as integracao_participantes
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
    resultado["permanentes"] = consultar_permanentes_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado["movimentacao_etaria"] = consultar_movimentacao_etaria_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado["desligamentos_motivo"] = consultar_desligamentos_motivo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado["tempo_permanencia"] = consultar_tempo_permanencia_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado["ingressantes_encaminhamento"] = consultar_ingressantes_encaminhamento_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado["perfil_demografico"] = consultar_perfil_demografico_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado["situacao_social"] = consultar_indicadores_sociais_fmr(usuario=usuario, ano=ano, mes=mes)
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
    resultado["presencas"] = consultar_presencas_fmr(usuario=usuario, ano=ano, mes=mes)
    return resultado


def consultar_permanentes_fmr(*, usuario, ano, mes):
    """RF-FMR-04: prepara o fechamento mensal sem presumir permanência histórica.

    A consulta real depende de contrato e histórico do módulo de participantes.
    Enquanto indisponível, total e lista permanecem ausentes, nunca zero.
    """
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"data_referencia": periodo["fim"], "participantes": None,
                 "total": None, "pendencia": None, "aviso": ""}
    try:
        autorizar(usuario, "participantes.view_participante")
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui permissão para consultar os participantes que permanecem no serviço."
        return resultado
    participantes = integracao_participantes.consultar_permanentes_na_data(
        usuario=usuario, data_referencia=periodo["fim"])
    if participantes is None:
        resultado["pendencia"] = {
            "codigo": "CONTRATO-PERMANENCIA",
            "aviso": "Faltam informações históricas para apresentar quem permanece no serviço.",
            "explicacao": (
                "Precisamos que o módulo de participantes tenha histórico completo de quem permanecia "
                "no serviço na data indicada, considerando entradas, desligamentos e reativações. "
                "Existem cadastros sem data de entrada ou com situações temporárias indefinidas; "
                "o tratamento dos status legados inativo e cancelado depende da definição do NCI (P02). "
                "O status atual e as presenças em aulas não substituem esse histórico. "
                "Até essa integração, a lista e o total não serão calculados."
            ),
        }
    else:
        resultado.update(participantes=participantes, total=len(participantes))
    return resultado


def consultar_tempo_permanencia_fmr(*, usuario, ano, mes):
    """RF-FMR-14: quatro faixas sem sobreposição, por saída do mês."""
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"periodo": periodo, "linhas": [], "total": None, "total_desligamentos": None,
                 "sem_periodo": None, "aviso": "", "pendencia": None}
    try:
        autorizar(usuario, "participantes.view_participante")
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui permissão para consultar o tempo de permanência dos desligados."
        return resultado
    resultado.update(integracao_participantes.consultar_tempo_permanencia_desligamentos(usuario=usuario, ano=ano, mes=mes))
    if resultado["sem_periodo"]:
        resultado["pendencia"] = {
            "codigo": "VINCULO", "aviso": "Falta histórico do vínculo para classificar o tempo de algumas saídas.",
            "explicacao": "É necessário identificar a entrada ou última reativação anterior a cada desligamento, "
                "na ordem das movimentações. Uma saída sem esse início ou com outra saída anterior sem reativação "
                "não tem período completo. As faixas não foram preenchidas com zero ou com totais parciais."}
    return resultado


def consultar_indicadores_sociais_fmr(*, usuario, ano, mes):
    """RF-FMR-09: moradia, apoio, deficiência e BPC sem presumir dados históricos."""
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"periodo": periodo, "aviso": "", "pendencia": None, "linhas": [],
                 "total_permanentes": None, "sem_situacao": None}
    try:
        autorizar(usuario, "participantes.view_participante")
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui permissão para consultar os indicadores de situação social."
        return resultado
    dados = integracao_participantes.consultar_indicadores_sociais(usuario=usuario, ano=ano, mes=mes)
    if dados is None:
        resultado["pendencia"] = {
            "codigo": "PERMANENCIA", "aviso": "Faltam informações históricas para calcular os indicadores sociais.",
            "explicacao": "É necessário completar as entradas e esclarecer situações legadas indefinidas para "
                "identificar quem permanecia no serviço no último dia do mês. A situação atual e as presenças "
                "em aulas não substituem o histórico de permanência."}
        return resultado
    resultado.update(total_permanentes=dados["total_permanentes"], sem_situacao=dados["sem_situacao"])
    if dados["sem_situacao"]:
        resultado["pendencia"] = {
            "codigo": "SITUACAO", "aviso": "Faltam informações de situação social vigentes no mês.",
            "explicacao": "Precisamos de situação social com vigência até o último dia do mês para todos os "
                "participantes que permanecem no serviço. Registros posteriores não completam meses anteriores. "
                "Ausência de informação não significa não morar sozinho, não ter apoio, não possuir deficiência "
                "ou não receber BPC; os totais não foram preenchidos com zero."}
    else:
        resultado["linhas"] = [{"codigo": codigo, "indicador": rotulo, "quantidade": dados["totais"][codigo]}
            for codigo, rotulo in (
                ("moram_sozinhos", "Pessoas que moram sozinhas"),
                ("moram_sozinhos_com_apoio", "Dessas pessoas, quantas contam com apoio da família/comunidade"),
                ("possuem_deficiencia", "Pessoas que possuem deficiência"),
                ("recebem_bpc", "Pessoas que recebem BPC"),
            )]
    return resultado


def consultar_perfil_demografico_fmr(*, usuario, ano, mes):
    """RF-FMR-08: somente dados com histórico; blocos pendentes não recebem estimativas."""
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"periodo": periodo, "aviso": "", "total_permanentes": None,
                 "imigrantes_refugiados": None, "sem_situacao": None,
                 "pendencia_imigrantes": None, "blocos_pendentes": []}
    try:
        autorizar(usuario, "participantes.view_participante")
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui permissão para consultar o perfil demográfico dos participantes."
        return resultado
    resultado["blocos_pendentes"] = [
        {"codigo": "RACA-COR", "titulo": "Sexo por raça/cor", "total": None,
         "primeira_coluna": "Sexo", "colunas": ["Branca", "Preta", "Pardo", "Amarela", "Indígena", "Não informada", "Total"],
         "linhas": [{"rotulo": sexo, "valores": [None] * 7} for sexo in ("Feminino", "Masculino", "Total")],
         "aviso": "Falta histórico de sexo e raça/cor para calcular esta tabela.",
         "explicacao": "As categorias do formulário FMR foram fornecidas pelo responsável. Precisamos disponibilizar "
             "sexo e raça/cor vigentes no mês. O cadastro permite correções sem vigência própria. "
             "O cadastro atual e a data da auditoria não substituem esse histórico; nenhum valor foi presumido."},
        {"codigo": "GENERO", "titulo": "Identidade de gênero", "total": None,
         "primeira_coluna": "Identidade de gênero", "colunas": ["Quantidade"],
         "linhas": [{"rotulo": genero, "valores": [None]} for genero in ("Cisgênero", "Transgênero", "Agênero", "Não declarado", "Total")],
         "aviso": "Falta histórico de identidade de gênero para calcular esta tabela.",
         "explicacao": "As categorias oficiais são Cisgênero, Transgênero, Agênero e Não declarado. Precisamos que "
             "o contrato de consulta represente essa autodeclaração com vigência no mês. "
             "O cadastro já oferece as quatro opções oficiais, mas suas correções ainda não possuem vigência própria. "
             "Não inferimos identidade de gênero pelo sexo nem reclassificamos meses anteriores pelo cadastro atual."},
        {"codigo": "REGIAO", "titulo": "Região de moradia", "linhas": None, "total": None,
         "aviso": "Faltam as regiões oficiais e o registro histórico da região de moradia.",
         "explicacao": "Precisamos da lista de regiões exigidas no FMR e de uma informação estruturada no cadastro, "
             "com data de vigência. O endereço livre não determina automaticamente a região; sem essa informação, "
             "as quantidades não são calculadas nem preenchidas com zero."},
    ]
    dados = integracao_participantes.consultar_imigrantes_refugiados(usuario=usuario, ano=ano, mes=mes)
    if dados is None:
        resultado["pendencia_imigrantes"] = {
            "codigo": "PERMANENCIA", "aviso": "Faltam informações históricas para identificar quem permanece no serviço.",
            "explicacao": "É necessário completar as entradas e esclarecer situações legadas indefinidas. "
                "A contagem de imigrantes/refugiados depende de quem permanecia no último dia do mês."}
    else:
        resultado.update(dados)
        if dados["sem_situacao"]:
            resultado["pendencia_imigrantes"] = {
                "codigo": "IMIGRANTE", "aviso": "Falta informação vigente de imigrante/refugiado para participantes do mês.",
                "explicacao": "Precisamos de situação social com vigência até o último dia do mês para todos os permanentes. "
                    "Sem registro, não é possível presumir que a pessoa não é imigrante/refugiada. "
                    "Registros que começam depois do fechamento não completam meses anteriores."}
    return resultado


def consultar_ingressantes_encaminhamento_fmr(*, usuario, ano, mes):
    """RF-FMR-07: novos ingressos por CRAS, CREAS e demais serviços da rede."""
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"periodo": periodo, "linhas": [], "total": None, "total_ingressantes": None,
                 "sem_origem": None, "outras_origens": None, "pendencias": [], "aviso": ""}
    try:
        autorizar(usuario, "participantes.view_participante")
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui permissão para consultar os ingressantes por encaminhamento."
        return resultado
    dados = integracao_participantes.consultar_ingressantes_encaminhamento(usuario=usuario, ano=ano, mes=mes)
    if dados is None:
        resultado["pendencias"] = [{"codigo": "ENTRADA",
            "aviso": "Faltam datas de entrada para calcular os ingressantes por encaminhamento.",
            "explicacao": "Existem participantes sem registro de entrada. É necessário informar a data de ingresso "
                "para identificar o mês correto; a data do cadastro e as presenças não substituem essa informação."}]
    else:
        resultado.update(dados)
        if dados["sem_origem"]:
            resultado["pendencias"] = [{"codigo": "ORIGEM-HISTORICA",
                "aviso": "Há ingressantes sem origem histórica do encaminhamento.",
                "explicacao": "A origem precisa estar registrada na entrada ou comprovada na auditoria do cadastro. "
                    "O valor atual não substitui o histórico. Enquanto houver origens desconhecidas neste mês, "
                    "as quantidades por origem e o total encaminhado pela rede não serão apresentados como completos."}]
    return resultado


def consultar_desligamentos_motivo_fmr(*, usuario, ano, mes):
    """RF-FMR-06: saídas por motivo registrado no evento, sem reclassificação retroativa."""
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"periodo": periodo, "linhas": [], "total": None, "pendencias": [], "aviso": ""}
    try:
        autorizar(usuario, "participantes.view_participante")
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui permissão para consultar os desligamentos por motivo."
        return resultado
    resultado.update(integracao_participantes.consultar_desligamentos_por_motivo(usuario=usuario, ano=ano, mes=mes))
    if any(not linha["descricao"].strip() for linha in resultado["linhas"]):
        resultado["pendencias"] = [{"codigo": "MOTIVO-HISTORICO",
            "aviso": "Há desligamentos sem descrição histórica do motivo.",
            "explicacao": "É necessário conferir a descrição do motivo na época desses desligamentos. "
                "Eles estão incluídos no total, mas não foram reclassificados usando o nome atual do catálogo."}]
    return resultado


def consultar_movimentacao_etaria_fmr(*, usuario, ano, mes):
    """RF-FMR-05: idade no dia 1 e retornos separados dos ingressos."""
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"periodo": periodo, "linhas": [], "totais": None, "pendencias": [], "aviso": ""}
    try:
        autorizar(usuario, "participantes.view_participante")
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui permissão para consultar a movimentação por faixa etária e sexo."
        return resultado
    dados = integracao_participantes.consultar_movimentacao_etaria(usuario=usuario, ano=ano, mes=mes)
    if dados is None:
        resultado["pendencias"] = [{"codigo": "HISTORICO", "aviso": "Faltam informações históricas para calcular a movimentação.",
            "explicacao": "Confira cadastros sem entrada ou com status legados ainda indefinidos. Nenhum total foi presumido."}]
    else:
        resultado.update(dados)
    return resultado



def consultar_presencas_fmr(*, usuario, ano, mes):
    """RF-FMR-03: calendário e média por datas com atendimento efetivamente registrado.

    NCI_FMR_CONTAGEM_DIARIA permite trocar a contagem principal de ocorrencias
    para participantes_unicos, caso haja orientação diferente (RN-FMR-09).
    As duas medidas continuam disponíveis e explicitamente identificadas.
    """
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    criterio = getattr(settings, "NCI_FMR_CONTAGEM_DIARIA", "ocorrencias")
    if criterio not in ("ocorrencias", "participantes_unicos"):
        raise ImproperlyConfigured("NCI_FMR_CONTAGEM_DIARIA deve ser ocorrencias ou participantes_unicos.")
    resultado = consultar_presencas_mensais(usuario=usuario, ano=ano, mes=mes)
    if resultado["demonstracao"]:
        raise ImproperlyConfigured("O FMR exige uma integração real de participantes.")
    por_data = {dia["data"]: dia for dia in resultado["dias"]}
    dias = [por_data.get(date(ano, mes, numero), {
        "data": date(ano, mes, numero), "ocorrencias": 0, "participantes_unicos": 0,
    }) for numero in range(1, periodo["fim"].day + 1)]
    funcionamento = sum(dia["ocorrencias"] > 0 for dia in dias)
    total = sum(dia[criterio] for dia in dias)
    return resultado | {"dias": dias, "criterio": criterio, "total_contagem_diaria": total,
        "dias_funcionamento": funcionamento,
        "media_diaria": Decimal(total) / Decimal(funcionamento) if funcionamento else None}
