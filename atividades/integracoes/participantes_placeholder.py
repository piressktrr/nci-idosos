"""Placeholder removível: somente leitura, dados fictícios e nenhuma tabela própria."""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .participantes import ParticipanteResumo


class ProvedorPlaceholder:
    origem = "placeholder"
    demonstracao = True
    participantes = (
        ParticipanteResumo("demo-1", "Participante fictício 1"),
        ParticipanteResumo("demo-2", "Participante fictício 2"),
        ParticipanteResumo("demo-3", "Participante fictício 3"),
    )

    def __init__(self):
        if not settings.DEBUG:
            raise ImproperlyConfigured("Configure NCI_PARTICIPANTES_PROVIDER com o provedor real fora do desenvolvimento.")

    def listar(self):
        return self.participantes

    def obter(self, referencia):
        return next((item for item in self.participantes if item.referencia == referencia), None)
