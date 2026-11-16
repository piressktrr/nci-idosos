"""Contratos de leitura entre apps, sem que um importe os modelos do outro.

`ParticipanteResumo`/`ProvedorParticipantes`: participantes implementa (participantes.provedor) e
atividades consome via atividades.integracoes.participantes.obter_provedor().
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ParticipanteResumo:
    referencia: str
    nome: str


class ProvedorParticipantes(Protocol):
    origem: str
    demonstracao: bool

    def listar(self) -> tuple[ParticipanteResumo, ...]: ...

    def obter(self, referencia: str) -> ParticipanteResumo | None: ...
