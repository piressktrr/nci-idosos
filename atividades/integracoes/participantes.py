"""Contrato provisório de leitura, sem importar modelos privados de participantes.

Integração: implementar listar()/obter() no provedor real, com origem='participantes'
e demonstracao=False. Configurar NCI_PARTICIPANTES_PROVIDER com o caminho da classe
nos settings. O provedor real retorna a PK estável como string em referencia.
O placeholder pode então ser removido: serviços e telas usam apenas este contrato.

Inscricao guarda (origem, referencia), sem FK provisória para uma tabela fictícia.
Uma FK definitiva exige alinhar o modelo/PK e criar uma migration incremental.
Nunca mapear referências de demonstração para pessoas reais automaticamente.
"""

from dataclasses import dataclass
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class ParticipanteResumo:
    referencia: str
    nome: str


class ProvedorParticipantes(Protocol):
    origem: str
    demonstracao: bool

    def listar(self) -> tuple[ParticipanteResumo, ...]: ...

    def obter(self, referencia: str) -> ParticipanteResumo | None: ...


def obter_provedor() -> ProvedorParticipantes:
    caminho = getattr(settings, "NCI_PARTICIPANTES_PROVIDER", "atividades.integracoes.participantes_placeholder.ProvedorPlaceholder")
    return import_string(caminho)()
