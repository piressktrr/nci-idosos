"""Efeito auditado de afastamentos sobre ausências já lançadas; não cria chamadas."""
from django.db import transaction
from core.permissoes import autorizar
from .integracoes.participantes import obter_provedor
from .models import Frequencia, RegistroCorrecaoFrequencia
from .services import _snapshot_frequencia


@transaction.atomic
def atualizar_ausencias(*, usuario, origem, referencia, desde):
    autor = autorizar(usuario, "participantes.change_participante")
    provedor = obter_provedor()
    if provedor.origem != origem:
        return
    estados_por_data = {}
    registros = (Frequencia.objects.select_for_update(of=("self",)).select_related("aula")
        .filter(inscricao__origem_participante=origem, inscricao__participante_referencia=referencia,
                aula__data__gte=desde, aula__situacao="realizada")
        .order_by("pk"))
    for frequencia in registros:
        data = frequencia.aula.data
        if data not in estados_por_data:
            estados_por_data[data] = provedor.situacoes_em(data).get(referencia)
        afastado = estados_por_data[data] == "afastamento"
        antes = _snapshot_frequencia(frequencia)
        if afastado and frequencia.situacao == "ausente":
            frequencia.situacao = "ausente_justificado"
            frequencia.motivo_descricao = "Afastamento"
            frequencia.justificada_por_afastamento = True
        elif not afastado and frequencia.justificada_por_afastamento:
            frequencia.situacao = "ausente"
            frequencia.motivo_descricao = ""
            frequencia.justificada_por_afastamento = False
        else:
            continue
        frequencia.versao += 1
        frequencia.save(update_fields=["situacao", "motivo_descricao", "justificada_por_afastamento", "versao"])
        RegistroCorrecaoFrequencia.objects.create(frequencia=frequencia, usuario=autor,
            anteriores=antes, novos=_snapshot_frequencia(frequencia) | {"ajuste_automatico": "afastamento"})
