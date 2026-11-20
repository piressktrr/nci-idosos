"""Auditoria de participantes (RNF-SEG-07) na tabela única de eventos (core.EventoAuditoria)."""

from core.permissoes import autorizar

from .models import RegistroParticipante

PERMISSAO_HISTORICO = "participantes.change_participante"
# Campos auditados que não são do Participante nem da SituacaoSocial (a entrada fica na Movimentacao).
ROTULOS_EXTRAS = {"data_entrada": "Data de entrada", "perfil_vigente_desde": "Vigência do perfil no FMR"}


def registrar(*, participante, acao, usuario, novos, anteriores=None):
    """Grava o evento. Chamar dentro da mesma transação da alteração."""
    return RegistroParticipante.objects.create(alvo_id=participante.pk, acao=acao, usuario=usuario,
                                               anteriores=anteriores, novos=novos)


def historico(participante, *, usuario):
    """Eventos do participante, do mais antigo para o mais recente.

    Mostra dados sensíveis (antes e depois), por isso exige a mesma permissão de corrigir o cadastro.
    """
    autorizar(usuario, PERMISSAO_HISTORICO, mensagem="Você não tem permissão para ver o histórico de alterações.")
    # tipo + alvo_id, ordenado por registrado_em: atendido pelo índice core_evento_alvo_idx.
    return RegistroParticipante.objects.filter(alvo_id=participante.pk).select_related("usuario")


def _rotulo(campo):
    from django.core.exceptions import FieldDoesNotExist

    from .models import Participante, SituacaoSocial
    if campo in ROTULOS_EXTRAS:
        return ROTULOS_EXTRAS[campo]
    for modelo in (Participante, SituacaoSocial):
        try:
            return str(modelo._meta.get_field(campo).verbose_name).capitalize()
        except FieldDoesNotExist:
            continue
    return campo


def _exibir(valor):
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    return valor


def diferencas(evento):
    """Campos que mudaram em um evento: [(campo, antes, depois)]. No cadastro, antes é None."""
    anteriores = evento.anteriores or {}
    return [(_rotulo(campo), _exibir(anteriores.get(campo)), _exibir(valor)) for campo, valor in evento.novos.items()
            if evento.anteriores is None or anteriores.get(campo) != valor]
