"""Desativação operacional; aulas, inscrições e classificações anteriores são preservadas."""
from django.core.exceptions import ValidationError
from django.db import transaction
from usuarios.services import autorizar_administrador
from .models import Atividade, RegistroSituacaoAtividade


def exigir_atividade_ativa(atividade):
    if not atividade.ativa:
        raise ValidationError("Esta atividade está inativa. Reative-a para cadastrar novas aulas, inscrições ou espera.")


@transaction.atomic
def alterar_situacao_atividade(*, usuario, atividade_id, ativa):
    autor = autorizar_administrador(usuario)
    if type(ativa) is not bool:
        raise ValidationError("Informe uma situação válida.")
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    if atividade.ativa == ativa:
        return atividade
    anterior = atividade.ativa
    atividade.ativa = ativa
    atividade.save(update_fields=["ativa"])
    RegistroSituacaoAtividade.objects.create(atividade=atividade, usuario=autor,
        acao="ativacao" if ativa else "desativacao", anteriores={"ativa": anterior}, novos={"ativa": ativa})
    return atividade
