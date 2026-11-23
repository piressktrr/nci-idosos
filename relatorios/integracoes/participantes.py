"""Adaptador do contrato histórico de participantes para o fechamento do FMR."""

from datetime import date


def consultar_tempo_permanencia_desligamentos(*, usuario, ano, mes):
    from participantes.relatorios import tempo_permanencia_desligamentos_mensal
    return tempo_permanencia_desligamentos_mensal(usuario=usuario, ano=ano, mes=mes)


def consultar_indicadores_sociais(*, usuario, ano, mes):
    from participantes.relatorios import indicadores_sociais_mensal
    return indicadores_sociais_mensal(usuario=usuario, ano=ano, mes=mes)


def consultar_imigrantes_refugiados(*, usuario, ano, mes):
    from participantes.relatorios import imigrantes_refugiados_mensal
    return imigrantes_refugiados_mensal(usuario=usuario, ano=ano, mes=mes)


def consultar_sexo_raca_genero(*, usuario, data):
    from participantes.relatorios import perfil_demografico_em
    return perfil_demografico_em(usuario=usuario, data=data)


def consultar_ingressantes_encaminhamento(*, usuario, ano, mes):
    from participantes.relatorios import ingressantes_por_encaminhamento_mensal
    return ingressantes_por_encaminhamento_mensal(usuario=usuario, ano=ano, mes=mes)


def consultar_desligamentos_por_motivo(*, usuario, ano, mes):
    from participantes.relatorios import desligamentos_por_motivo_mensal
    return desligamentos_por_motivo_mensal(usuario=usuario, ano=ano, mes=mes)


def consultar_movimentacao_etaria(*, usuario, ano, mes):
    from participantes.relatorios import movimentacao_etaria_mensal
    return movimentacao_etaria_mensal(usuario=usuario, ano=ano, mes=mes)


def consultar_permanentes_na_data(*, usuario, data_referencia: date):
    """RN-FMR-12: `PermanentesComPendencias` de participantes na data (último dia do mês).

    `permanentes` usa só os cadastros completos; `pendentes` (com `motivos`: sem entrada, status Inativo ou
    Cancelado) ficam fora de todos os totais do FMR e são listados na tela, sem conversão de status.
    A API de participantes aplica suas permissões e devolve identidades estáveis, sem duplicatas.
    Não presume que cadastros atualmente ativos permaneciam em meses anteriores.
    """
    from participantes.consultas import permanentes_com_pendencias
    return permanentes_com_pendencias(usuario=usuario, data_referencia=data_referencia)
