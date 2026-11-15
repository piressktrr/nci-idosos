"""Consultas à auditoria única (core.RegistroAuditoria) usadas pelos testes de atividades."""

from django.contrib.contenttypes.models import ContentType

from core.models import RegistroAuditoria


def registros(modelo, acao=None):
    """Registros de todos os objetos de um modelo, opcionalmente de uma ação."""
    consulta = RegistroAuditoria.objects.filter(content_type=ContentType.objects.get_for_model(modelo))
    return consulta.filter(acao=acao) if acao else consulta


def registros_de(objeto, acao=None):
    """Registros de um objeto, do mais antigo para o mais recente."""
    return registros(type(objeto), acao).filter(object_id=str(objeto.pk))


def registro_unico(objeto, acao):
    """Registro de uma ação única do objeto (ex.: cadastro, realizacao, lancamento)."""
    return registros_de(objeto, acao).get()
