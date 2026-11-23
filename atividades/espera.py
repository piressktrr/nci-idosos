"""RF-ATV-14: espera separada das inscrições e da chamada, por origem externa.

NCI (21/11): o afastado sai da lista de espera e não é atendido enquanto estiver afastado.
"""
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.permissoes import autorizar
from .integracoes.participantes import obter_provedor
from .models import Atividade, Inscricao, EsperaAtividade, RegistroEsperaAtividade
from .situacao import exigir_atividade_ativa


def _situacoes_hoje(provedor):
    return getattr(provedor, "situacoes_em", lambda data: {})(timezone.localdate())


def primeiro_da_fila(*, atividade, provedor, estados=None):
    """Primeiro aguardando por ordem de entrada; quem está afastado hoje não é oferecido para atendimento."""
    estados = _situacoes_hoje(provedor) if estados is None else estados
    fila = EsperaAtividade.objects.filter(atividade=atividade, origem_participante=provedor.origem, situacao="aguardando")
    return next((item for item in fila if estados.get(item.participante_referencia) != "afastamento"), None)


@transaction.atomic
def adicionar_espera(*, usuario, atividade_id, participante_referencia):
    autor = autorizar(usuario, "atividades.add_esperaatividade")
    if not isinstance(participante_referencia, str) or not participante_referencia or len(participante_referencia) > 64:
        raise ValidationError("Selecione um participante cadastrado.")
    provedor = obter_provedor()
    # Bloqueia a pessoa antes da atividade, na mesma ordem da movimentação (que retira o afastado da espera).
    getattr(provedor, "bloquear", lambda referencias: None)([participante_referencia])
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    exigir_atividade_ativa(atividade)
    estado = _situacoes_hoje(provedor).get(participante_referencia)
    if estado == "desligamento":
        raise ValidationError("Reative o participante desligado antes de adicionar à espera.")
    if estado == "afastamento":
        raise ValidationError("Registre o retorno do participante afastado antes de adicionar à espera.")
    participante = provedor.obter(participante_referencia)
    if participante is None:
        raise ValidationError("Participante não encontrado no cadastro.")
    identidade = {"atividade": atividade, "origem_participante": provedor.origem,
                  "participante_referencia": participante.referencia}
    if Inscricao.objects.filter(**identidade).exists():
        raise ValidationError("Este participante já está inscrito na atividade.")
    if EsperaAtividade.objects.filter(**identidade, situacao="aguardando").exists():
        raise ValidationError("Este participante já está aguardando nesta atividade.")
    espera = EsperaAtividade(**identidade)
    espera.full_clean()
    espera.save()
    RegistroEsperaAtividade.objects.create(espera=espera, usuario=autor, anteriores=None,
        novos={"situacao": "aguardando", "origem": provedor.origem, "referencia": participante.referencia})
    return espera


def validar_atendimento(*, usuario, atividade, provedor, participante, espera_id, vaga_confirmada, estados=None):
    """Chamado dentro da transação/bloqueio de inscrever_participante."""
    estados = _situacoes_hoje(provedor) if estados is None else estados
    primeiro = primeiro_da_fila(atividade=atividade, provedor=provedor, estados=estados)
    if espera_id is None:
        if primeiro:
            raise ValidationError("Há uma lista de espera. Confirme a vaga e atenda o primeiro pela tela de espera.")
        return None
    autorizar(usuario, "atividades.change_esperaatividade")
    espera = EsperaAtividade.objects.select_for_update().get(pk=espera_id, atividade=atividade,
                                                             origem_participante=provedor.origem)
    if espera.situacao != "aguardando":
        raise ValidationError("Este registro não está mais aguardando.")
    if estados.get(espera.participante_referencia) == "afastamento":
        raise ValidationError("Participante afastado não pode ser atendido pela lista de espera. "
                              "Registre o retorno antes de inscrever.")
    if primeiro is None or primeiro.pk != espera.pk or espera.participante_referencia != participante.referencia:
        raise ValidationError("Atenda o primeiro participante por ordem de entrada.")
    if vaga_confirmada is not True:
        raise ValidationError("A equipe deve confirmar que existe uma vaga disponível.")
    return espera


def registrar_atendimento(*, espera, inscricao, usuario):
    espera.situacao, espera.inscricao = "inscrito", inscricao
    espera.save(update_fields=["situacao", "inscricao"])
    RegistroEsperaAtividade.objects.create(espera=espera, usuario=usuario, anteriores={"situacao": "aguardando"},
        novos={"situacao": "inscrito", "inscricao_id": inscricao.pk, "vaga_confirmada": True})


@transaction.atomic
def retirar_espera(*, usuario, atividade_id, espera_id):
    autor = autorizar(usuario, "atividades.change_esperaatividade")
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    provedor = obter_provedor()
    espera = EsperaAtividade.objects.select_for_update().get(pk=espera_id, atividade=atividade,
                                                             origem_participante=provedor.origem)
    if espera.situacao != "aguardando":
        raise ValidationError("Este registro não está mais aguardando.")
    espera.situacao = "retirado"
    espera.save(update_fields=["situacao"])
    RegistroEsperaAtividade.objects.create(espera=espera, usuario=autor,
        anteriores={"situacao": "aguardando"}, novos={"situacao": "retirado"})
    return espera


def retirar_afastado_das_esperas(*, autor, origem, referencia):
    """NCI 21/11: ao registrar o afastamento, a pessoa sai de todas as listas de espera em que aguardava.

    Chamado por `ajustes_afastamento.atualizar_ausencias`, na transação da movimentação (a pessoa já está bloqueada).
    Cada retirada fica auditada como as manuais, marcada como ajuste automático.
    """
    esperas = (EsperaAtividade.objects.select_for_update()
               .filter(origem_participante=origem, participante_referencia=referencia, situacao="aguardando")
               .order_by("pk"))
    retiradas = []
    for espera in esperas:
        espera.situacao = "retirado"
        espera.save(update_fields=["situacao"])
        RegistroEsperaAtividade.objects.create(espera=espera, usuario=autor, anteriores={"situacao": "aguardando"},
            novos={"situacao": "retirado", "ajuste_automatico": "afastamento"})
        retiradas.append(espera)
    return retiradas
