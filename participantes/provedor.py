"""Provedor real do contrato de participantes (core.integracoes.ProvedorParticipantes), consumido pelo app de atividades.

Atividades guarda a inscrição como (origem="participantes", referencia=str(pk)) e só consulta
nome e identificador por aqui, sem acessar o modelo Participante diretamente.
"""

from core.integracoes import ParticipanteResumo

from .models import Participante


class ProvedorParticipantes:
    origem = "participantes"
    demonstracao = False

    def bloquear(self, referencias):
        """Serializa lançamentos com mudanças de situação da mesma identidade."""
        pks = [int(ref) for ref in referencias if isinstance(ref, str) and ref.isdecimal()]
        list(Participante.objects.select_for_update().filter(pk__in=pks).order_by("pk"))

    def situacoes_em(self, data):
        """Situações explícitas na data; cadastros legados sem eventos ficam sem classificação."""
        from .models import Movimentacao
        ultimas = Movimentacao.objects.filter(data__lte=data).order_by("participante_id", "-data", "-pk").distinct("participante_id")
        estados = {str(pk): tipo for pk, tipo in ultimas.values_list("participante_id", "tipo")}
        for pk in Movimentacao.objects.filter(tipo="entrada", data__gt=data).values_list("participante_id", flat=True):
            estados.setdefault(str(pk), "nao_ingressou")
        return estados

    def listar(self):
        return tuple(ParticipanteResumo(str(pk), nome)
                     for pk, nome in Participante.objects.order_by("nome_completo", "pk").values_list("pk", "nome_completo"))

    def obter(self, referencia):
        if not isinstance(referencia, str) or not referencia.isdecimal():
            return None
        participante = Participante.objects.filter(pk=int(referencia)).values_list("pk", "nome_completo").first()
        return ParticipanteResumo(str(participante[0]), participante[1]) if participante else None
