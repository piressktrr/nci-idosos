"""Auditoria de participantes (RNF-SEG-07) na tabela única de eventos (atividades.EventoAuditoria)."""

from atividades.models import RegistroParticipante


def registrar(*, participante, acao, usuario, novos, anteriores=None):
    """Grava o evento. Chamar dentro da mesma transação da alteração."""
    return RegistroParticipante.objects.create(participante=participante, acao=acao, usuario=usuario,
                                               anteriores=anteriores, novos=novos)


def historico(participante):
    """Eventos do participante, do mais antigo para o mais recente."""
    return RegistroParticipante.objects.filter(participante=participante).select_related("usuario")


def diferencas(evento):
    """Campos que mudaram em um evento: [(campo, antes, depois)]. No cadastro, antes é None."""
    anteriores = evento.anteriores or {}
    return [(campo, anteriores.get(campo), valor) for campo, valor in evento.novos.items()
            if evento.anteriores is None or anteriores.get(campo) != valor]
