"""Adaptador do contrato histórico de participantes para o fechamento do FMR."""

from datetime import date

from core.integracoes import ParticipanteResumo


def consultar_permanentes_na_data(*, usuario, data_referencia: date) -> tuple[ParticipanteResumo, ...] | None:
    """None = consulta histórica indisponível; tupla vazia = consulta válida sem permanentes.

    A API de participantes aplica suas permissões e devolve identidades estáveis,
    sem duplicatas. Acervos incompletos/ambíguos retornam None explicitamente.
    Chamado pelo serviço FMR após validar perfil, permissão e mês de referência.
    Não presume que cadastros atualmente ativos permaneciam em meses anteriores.
    """
    from participantes.consultas import permanentes_em
    return permanentes_em(usuario=usuario, data_referencia=data_referencia)
