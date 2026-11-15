"""Provedor real do contrato de participantes usado por atividades (atividades.integracoes.participantes).

Atividades guarda a inscrição como (origem="participantes", referencia=str(pk)) e só consulta
nome e identificador por aqui, sem acessar o modelo Participante diretamente.
"""

from atividades.integracoes.participantes import ParticipanteResumo

from .models import Participante


class ProvedorParticipantes:
    origem = "participantes"
    demonstracao = False

    def listar(self):
        return tuple(ParticipanteResumo(str(pk), nome)
                     for pk, nome in Participante.objects.order_by("nome_completo", "pk").values_list("pk", "nome_completo"))

    def obter(self, referencia):
        if not isinstance(referencia, str) or not referencia.isdecimal():
            return None
        participante = Participante.objects.filter(pk=int(referencia)).values_list("pk", "nome_completo").first()
        return ParticipanteResumo(str(participante[0]), participante[1]) if participante else None
