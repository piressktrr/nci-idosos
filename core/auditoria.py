"""Gravação e consulta da auditoria comum a todos os apps."""

from django.contrib.contenttypes.models import ContentType

from .models import RegistroAuditoria


def registrar(*, objeto, acao, usuario, novos, anteriores=None):
    """Grava um registro de auditoria. Chamar dentro da mesma transação da alteração."""
    return RegistroAuditoria.objects.create(
        content_type=ContentType.objects.get_for_model(objeto, for_concrete_model=True),
        object_id=str(objeto.pk), acao=acao, usuario=usuario, anteriores=anteriores, novos=novos,
    )


def historico(objeto):
    """Registros de um objeto, do mais antigo para o mais recente."""
    return RegistroAuditoria.objects.filter(
        content_type=ContentType.objects.get_for_model(objeto, for_concrete_model=True), object_id=str(objeto.pk),
    ).select_related("usuario")


def diferencas(registro):
    """Campos que mudaram em um registro: [(campo, antes, depois)]. No cadastro, antes é None."""
    anteriores = registro.anteriores or {}
    return [(campo, anteriores.get(campo), valor) for campo, valor in registro.novos.items()
            if registro.anteriores is None or anteriores.get(campo) != valor]
