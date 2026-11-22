"""Efeito auditado de afastamentos sobre ausências já lançadas e sobre a lista de espera; não cria chamadas."""
from django.db import transaction
from django.utils import timezone
from core.permissoes import autorizar
from .espera import retirar_afastado_das_esperas
from .integracoes.participantes import obter_provedor
from .models import EsperaAtividade, Frequencia, RegistroCorrecaoFrequencia
from .services import _snapshot_frequencia


@transaction.atomic
def atualizar_ausencias(*, usuario, origem, referencia, desde):
    """Chamado por participantes (NCI_AJUSTE_AFASTAMENTO) a cada afastamento ou retorno, já gravado na transação.

    - Ausências desde `desde`: "ausente" de afastado vira justificado automático; no retorno, só as justificativas
      automáticas (`justificada_por_afastamento`) voltam a "ausente". Justificativas da equipe ficam como estão.
    - Se a pessoa está afastada hoje (o afastamento acabou de ser registrado), sai das listas de espera.
    """
    autor = autorizar(usuario, "participantes.change_participante")
    provedor = obter_provedor()
    if provedor.origem != origem:
        return
    aguardando = EsperaAtividade.objects.filter(origem_participante=origem, participante_referencia=referencia,
                                                situacao="aguardando")
    if aguardando.exists() and provedor.situacoes_em(timezone.localdate()).get(referencia) == "afastamento":
        retirar_afastado_das_esperas(autor=autor, origem=origem, referencia=referencia)
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
        elif (not afastado and frequencia.justificada_por_afastamento
              and frequencia.motivo_id is None and not frequencia.observacao):
            # Motivo ou observação indicam escolha da equipe (registros anteriores à correção também tinham a marca).
            frequencia.situacao = "ausente"
            frequencia.motivo_descricao = ""
            frequencia.justificada_por_afastamento = False
        else:
            continue
        frequencia.versao += 1
        frequencia.save(update_fields=["situacao", "motivo_descricao", "justificada_por_afastamento", "versao"])
        RegistroCorrecaoFrequencia.objects.create(frequencia=frequencia, usuario=autor,
            anteriores=antes, novos=_snapshot_frequencia(frequencia) | {"ajuste_automatico": "afastamento"})
