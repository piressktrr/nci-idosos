"""Consultas mensais do FMR, usando os serviços de leitura das áreas de origem."""
from calendar import monthrange
from collections import Counter
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError

from atividades.consultas_fmr import consultar_presencas_mensais
from atividades.services import consultar_frequencia_mensal
from core.permissoes import autorizar

from .integracoes import atividades as integracao_atividades
from .integracoes import participantes as integracao_participantes
from .permissoes import pode_consultar_fmr
from .cobertura import identificar_campos_indisponiveis
from .consistencia import verificar_consistencia


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
    else:
        if frequencia["demonstracao"]:
            resultado["aviso"] = "Os indicadores precisam da integração real de participantes; dados de demonstração não são utilizados no FMR."
        else:
            totais = frequencia["totais"]
            resultado["indicadores"] = [
                {"codigo": "aulas_realizadas", "nome": "Aulas realizadas", "valor": totais["aulas_realizadas"],
                 "descricao": "Aulas realizadas no mês, excluindo as canceladas."},
                {"codigo": "participacoes", "nome": "Participações por presença", "valor": totais["presentes"],
                 "descricao": "Uma ocorrência por presença em aula; a mesma pessoa pode contar mais de uma vez no mês."},
            ]
            resultado["presencas"] = consultar_presencas_fmr(usuario=usuario, ano=ano, mes=mes)
            resultado["categorias_atividades"] = consultar_categorias_atividades_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado["campos_indisponiveis"] = identificar_campos_indisponiveis(resultado)
    resultado["avisos_consistencia"] = verificar_consistencia(resultado)
    return resultado


def consultar_permanentes_fmr(*, usuario, ano, mes):
    """RF-FMR-04: prepara o fechamento mensal sem presumir permanência histórica.

    RN-FMR-12: o total usa só os cadastros completos. Os pendentes (sem entrada, status Inativo ou Cancelado)
    não anulam o mês: voltam em `cadastros_pendentes`, com o motivo, e a tela avisa que todos os totais os
    excluem. Nenhum status é convertido aqui. Se a integração não responder (None), total e lista ficam
    ausentes, nunca zero.
    """
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"data_referencia": periodo["fim"], "participantes": None, "total": None, "pendencia": None,
                 "pendencias": [], "cadastros_pendentes": [], "motivos_pendentes": [], "aviso": ""}
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
                "O status atual e as presenças em aulas não substituem esse histórico. "
                "Até essa integração, a lista e o total não serão calculados."
            ),
        }
        return resultado
    resultado.update(participantes=participantes.permanentes, total=len(participantes.permanentes))
    if participantes.pendentes:
        motivos = participantes.motivos
        resultado["cadastros_pendentes"] = [
            {"referencia": pessoa.referencia, "nome": pessoa.nome,
             "motivo": "; ".join(motivos.get(pessoa.referencia, ())) or "histórico incompleto"}
            for pessoa in participantes.pendentes]
        contagem = Counter(motivo for pessoa in participantes.pendentes for motivo in motivos.get(pessoa.referencia, ()))
        resultado["motivos_pendentes"] = [{"motivo": motivo, "quantidade": quantidade}
                                          for motivo, quantidade in sorted(contagem.items())]
        resultado["pendencias"] = [{
            "codigo": "CADASTROS-PENDENTES",
            "aviso": f"{len(participantes.pendentes)} cadastro(s) fora do cálculo: sem entrada ou com status "
                     "Inativo/Cancelado.",
            "explicacao": "Os totais do FMR usam só cadastros com movimentação de entrada e status Ativo, Afastado "
                "ou Desligado. Os demais ficam fora de todos os totais até a correção do cadastro (registrar a "
                "entrada, ou a movimentação que corresponde aos status legados Inativo e Cancelado). "
                "Nenhum status é convertido automaticamente."}]
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
                 "pendencia_imigrantes": None, "blocos_pendentes": [], "blocos": []}
    try:
        autorizar(usuario, "participantes.view_participante")
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui permissão para consultar o perfil demográfico dos participantes."
        return resultado
    resultado["blocos"] = [
        {"codigo": "RACA-COR", "titulo": "Sexo por raça/cor", "total": None,
         "primeira_coluna": "Sexo", "colunas": ["Branca", "Preta", "Pardo", "Amarela", "Indígena", "Não informada", "Total"],
         "linhas": [{"rotulo": sexo, "valores": [None] * 7} for sexo in ("Feminino", "Masculino", "Total")],
         "aviso": "Falta histórico de sexo e raça/cor para calcular esta tabela.",
         "explicacao": "Confirme a permanência e registre no cadastro de cada participante a data a partir da qual "
             "sexo e raça/cor valiam, até o fechamento do mês."},
        {"codigo": "GENERO", "titulo": "Identidade de gênero", "total": None,
         "primeira_coluna": "Identidade de gênero", "colunas": ["Quantidade"],
         "linhas": [{"rotulo": genero, "valores": [None]} for genero in ("Cisgênero", "Transgênero", "Agênero", "Não declarado", "Total")],
         "aviso": "Falta histórico de identidade de gênero para calcular esta tabela.",
         "explicacao": "Confirme a permanência e registre no cadastro de cada participante a data a partir da qual "
             "a identidade de gênero autodeclarada valia, até o fechamento do mês."},
        {"codigo": "REGIAO", "titulo": "Região de moradia", "linhas": None, "total": None,
         "aviso": "Faltam as regiões oficiais e o registro histórico da região de moradia.",
         "explicacao": "O NCI decidiu (Q6, 20/11) registrar por ora só o endereço completo, sem região. "
             "O endereço livre não determina automaticamente a região; sem uma informação estruturada com data de "
             "vigência, as quantidades não são calculadas nem preenchidas com zero."},
    ]
    perfil = integracao_participantes.consultar_sexo_raca_genero(usuario=usuario, data=periodo["fim"])
    if perfil is not None:
        por_sexo_raca, por_genero = perfil["sexo_raca"], perfil["genero"]
        raca, genero, _ = resultado["blocos"]
        codigos_raca = ("branca", "preta", "parda", "amarela", "indigena", "nao_informado")
        feminino, masculino = ([por_sexo_raca[sexo, codigo] for codigo in codigos_raca] for sexo in ("F", "M"))
        totais = [f + m for f, m in zip(feminino, masculino, strict=True)]
        for linha, valores in zip(raca["linhas"], (feminino, masculino, totais), strict=True):
            linha["valores"] = [*valores, sum(valores)]
        raca.update(total=sum(totais), aviso="")
        valores_genero = [por_genero[codigo] for codigo in ("cisgenero", "transgenero", "agenero", "nao_declarado")]
        for linha, quantidade in zip(genero["linhas"], (*valores_genero, sum(valores_genero)), strict=True):
            linha["valores"] = [quantidade]
        genero.update(total=sum(valores_genero), aviso="")
    resultado["blocos_pendentes"] = [bloco for bloco in resultado["blocos"] if bloco["aviso"]]
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
        return resultado
    resultado.update(dados)
    # RF-FMR-13 (Q4, NCI): no portal da SMADS o reativado entra em "ingressaram". Aqui as colunas seguem
    # separadas (RN-PAR-08) e a soma a lançar no portal vem pronta em `ingressaram_portal`.
    for valores in (*resultado["linhas"], resultado["totais"], resultado["fora_faixas"]):
        ingressos, reativados = valores["ingressaram"], valores["reativados"]
        valores["ingressaram_portal"] = None if None in (ingressos, reativados) else ingressos + reativados
    if dados.get("sem_perfil"):
        resultado["pendencias"] = [{"codigo": "PERFIL",
            "aviso": f"Falta o sexo vigente no fim do mês para {dados['sem_perfil']} participante(s) da tabela.",
            "explicacao": "O sexo de cada pessoa vem do perfil demográfico vigente no último dia do mês, a mesma "
                "referência da tabela Sexo por raça/cor. Sem esse registro, a pessoa não pode ser colocada em uma "
                "linha de sexo; as quantidades não foram calculadas nem preenchidas com zero."}]
    return resultado



def dias_uteis(ano, mes):
    """RN-FMR-14 (P06, NCI 21/11): dias de funcionamento = dias úteis do calendário, de segunda a sexta.

    Feriados não são descontados: o sistema não tem calendário de feriados. Em mês com feriado em dia útil,
    a equipe ajusta o divisor na transcrição (a tela avisa isso).
    """
    return sum(date(ano, mes, dia).weekday() < 5 for dia in range(1, monthrange(ano, mes)[1] + 1))


def consultar_presencas_fmr(*, usuario, ano, mes):
    """RF-FMR-03: presenças por data, total mensal e média diária pelos dias úteis do mês (RN-FMR-14).

    NCI_FMR_CONTAGEM_DIARIA permite trocar a contagem principal de ocorrencias
    para participantes_unicos, caso haja orientação diferente (RN-FMR-09).
    As duas medidas continuam disponíveis e explicitamente identificadas.
    `dias_com_atendimento` (datas com alguma presença) é só informativo; não entra na média.
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
    funcionamento = dias_uteis(ano, mes)
    total = sum(dia[criterio] for dia in dias)
    return resultado | {"dias": dias, "criterio": criterio, "total_contagem_diaria": total,
        "dias_funcionamento": funcionamento, "dias_com_atendimento": sum(dia["ocorrencias"] > 0 for dia in dias),
        "media_diaria": Decimal(total) / Decimal(funcionamento) if funcionamento else None}


def consultar_categorias_atividades_fmr(*, usuario, ano, mes):
    """RF-FMR-10: aulas realizadas e participações (presenças) por categoria do FMR no mês.

    A categoria é a da atividade inteira (P04, NCI 21/11), vigente na data de cada aula. Aulas de atividades
    sem categoria vigente impedem o fechamento por categoria: as quantidades ficam ausentes, nunca zero.
    """
    periodo = consultar_periodo_fmr(usuario=usuario, ano=ano, mes=mes)
    resultado = {"periodo": periodo, "linhas": [], "total_aulas": None, "total_participacoes": None,
                 "sem_categoria": None, "pendencias": [], "aviso": ""}
    try:
        dados = integracao_atividades.consultar_aulas_por_categoria(usuario=usuario, ano=ano, mes=mes)
    except PermissionDenied:
        resultado["aviso"] = "Seu perfil não possui as permissões para consultar as aulas por categoria do FMR."
        return resultado
    if dados["demonstracao"]:
        raise ImproperlyConfigured("O FMR exige uma integração real de participantes.")
    linhas, sem_categoria = dados["linhas"], dados["sem_categoria"]
    resultado.update(linhas=linhas, sem_categoria=sem_categoria)
    if sem_categoria["aulas"]:
        for linha in linhas:
            linha.update(aulas=None, participacoes=None)
        resultado["pendencias"] = [{"codigo": "CATEGORIA",
            "aviso": f"{sem_categoria['aulas']} aula(s) realizada(s) de atividades sem categoria do FMR na data.",
            "explicacao": "Cada atividade precisa estar classificada em uma categoria do FMR com vigência até a "
                "data da aula (catálogo do FMR, em Atividades). Sem isso não se sabe em que linha entram a aula e "
                "as presenças; as quantidades por categoria não foram calculadas nem preenchidas com zero."}]
    else:
        resultado.update(total_aulas=sum(linha["aulas"] for linha in linhas),
                         total_participacoes=sum(linha["participacoes"] for linha in linhas))
    return resultado
