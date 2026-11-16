"""RF-ATV-14: espera separada das inscrições e da chamada, por origem externa."""
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .integracoes.participantes import obter_provedor
from .models import Atividade, Inscricao, EsperaAtividade, RegistroEsperaAtividade


def autorizar(usuario, permissao):
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        raise PermissionDenied
    autor = get_user_model().objects.filter(pk=usuario.pk, is_active=True).first()
    if autor is None or not autor.has_perm(permissao):
        raise PermissionDenied
    return autor


@transaction.atomic
def adicionar_espera(*, usuario, atividade_id, participante_referencia):
    autor = autorizar(usuario, "atividades.add_esperaatividade")
    if not isinstance(participante_referencia, str) or not participante_referencia or len(participante_referencia) > 64:
        raise ValidationError("Selecione um participante cadastrado.")
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    provedor = obter_provedor()
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


def validar_atendimento(*, usuario, atividade, provedor, participante, espera_id, vaga_confirmada):
    """Chamado dentro da transação/bloqueio de inscrever_participante."""
    fila = EsperaAtividade.objects.filter(atividade=atividade, origem_participante=provedor.origem, situacao="aguardando")
    primeiro = fila.first()
    if espera_id is None:
        if primeiro:
            raise ValidationError("Há uma lista de espera. Confirme a vaga e atenda o primeiro pela tela de espera.")
        return None
    autorizar(usuario, "atividades.change_esperaatividade")
    espera = EsperaAtividade.objects.get(pk=espera_id, atividade=atividade, origem_participante=provedor.origem)
    if espera.situacao != "aguardando":
        raise ValidationError("Este registro não está mais aguardando.")
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
    espera = EsperaAtividade.objects.get(pk=espera_id, atividade=atividade, origem_participante=provedor.origem)
    if espera.situacao != "aguardando":
        raise ValidationError("Este registro não está mais aguardando.")
    espera.situacao = "retirado"
    espera.save(update_fields=["situacao"])
    RegistroEsperaAtividade.objects.create(espera=espera, usuario=autor,
        anteriores={"situacao": "aguardando"}, novos={"situacao": "retirado"})
    return espera
