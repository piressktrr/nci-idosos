"""Desligamentos e retornos explícitos, sem confundir situações temporárias com saídas."""
from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from core.permissoes import autorizar, autorizar_administrador
from .auditoria import registrar
from .categorias import TipoMovimentacao
from .models import Participante, Movimentacao, MotivoDesligamento, RegistroMotivoDesligamento


@transaction.atomic
def salvar_motivo(*, usuario, descricao, ativo=True, motivo_id=None):
    autor = autorizar_administrador(usuario)
    if not isinstance(descricao, str) or type(ativo) is not bool:
        raise ValidationError("Informe descrição e situação válidas.")
    motivo = (MotivoDesligamento.objects.select_for_update().get(pk=motivo_id)
              if motivo_id is not None else MotivoDesligamento())
    antes = {"descricao": motivo.descricao, "ativo": motivo.ativo} if motivo.pk else None
    motivo.descricao, motivo.ativo = descricao.strip(), ativo
    motivo.full_clean()
    novos = {"descricao": motivo.descricao, "ativo": motivo.ativo}
    if antes == novos:
        return motivo
    motivo.save()
    RegistroMotivoDesligamento.objects.create(motivo_desligamento=motivo, usuario=autor,
        acao="correcao" if antes else "cadastro", anteriores=antes, novos=novos)
    return motivo


@transaction.atomic
def movimentar_participante(*, usuario, participante_id, tipo, data, motivo_id=None):
    autor = autorizar(usuario, "participantes.change_participante")
    pessoa = Participante.objects.select_for_update().get(pk=participante_id)
    if tipo not in ("desligamento", "reativacao", "afastamento", "retorno"):
        raise ValidationError("Escolha uma movimentação válida.")
    if type(data) is not date or data > timezone.localdate():
        raise ValidationError("Informe uma data válida, até hoje.")
    ultimo = pessoa.movimentacoes.order_by("-data", "-pk").first()
    if ultimo is None:
        raise ValidationError("Registre a data de entrada na correção do cadastro antes de movimentar.")
    if data < ultimo.data:
        raise ValidationError("A data não pode ser anterior à última movimentação.")
    if pessoa.status not in ("ativo", "desligado", "afastado"):
        raise ValidationError("A situação temporária deste cadastro precisa ser definida antes de movimentar (P02).")
    estado = {"entrada": "ativo", "reativacao": "ativo", "retorno": "ativo",
              "desligamento": "desligado", "afastamento": "afastado"}[ultimo.tipo]
    permitidos = {"ativo": ("desligamento", "afastamento"), "afastado": ("retorno", "desligamento"),
                  "desligado": ("reativacao",)}
    if tipo not in permitidos[estado]:
        raise ValidationError("A movimentação não é compatível com a situação atual.")
    motivo = None
    if tipo == TipoMovimentacao.DESLIGAMENTO:
        if type(motivo_id) is not int or motivo_id <= 0:
            raise ValidationError("Selecione um motivo de desligamento ativo cadastrado pelo administrador.")
        motivo = MotivoDesligamento.objects.select_for_update().filter(pk=motivo_id, ativo=True).first()
        if motivo is None:
            raise ValidationError("Selecione um motivo de desligamento ativo cadastrado pelo administrador.")
    elif motivo_id is not None:
        raise ValidationError("Somente desligamento deve ter motivo de desligamento.")
    movimento = Movimentacao(participante=pessoa, tipo=tipo, data=data, usuario=autor,
                             motivo=motivo, motivo_descricao=motivo.descricao if motivo else "")
    movimento.full_clean()
    movimento.save()
    anterior = pessoa.status
    pessoa.status = {"desligamento": "desligado", "afastamento": "afastado"}.get(tipo, "ativo")
    pessoa.save(update_fields=["status"])
    registrar(participante=pessoa, acao={"desligamento": "desligar", "reativacao": "reativar", "afastamento": "afastar", "retorno": "retornar"}[tipo], usuario=autor,
        anteriores={"status": anterior}, novos={"status": pessoa.status, "tipo": tipo,
            "data": data.isoformat(), "motivo": movimento.motivo_descricao})
    if tipo in ("afastamento", "retorno"):
        from django.conf import settings
        from django.utils.module_loading import import_string
        caminho = getattr(settings, "NCI_AJUSTE_AFASTAMENTO", "")
        if caminho:
            import_string(caminho)(usuario=autor, origem="participantes", referencia=str(pessoa.pk), desde=data)
    return movimento
