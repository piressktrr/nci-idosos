"""Serviços provisórios de atividades, grade e aulas, com autorização e auditoria."""

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .models import (
    Atividade, Aula, HorarioAtividade, RegistroCadastroAtividade,
    RegistroGradeAtividade, RegistroRealizacaoAula, RegistroCancelamentoAula,
)


@transaction.atomic
def cadastrar_atividade(*, usuario, nome, local, monitor):
    """Cadastra e audita em uma transação; exige atividades.add_atividade."""
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        raise PermissionDenied("É necessário um usuário autorizado para cadastrar atividades.")
    # Consulta atual evita autorizar contas desativadas ou permissões antigas em cache.
    autor = get_user_model().objects.filter(pk=usuario.pk, is_active=True).first()
    if autor is None or not autor.has_perm("atividades.add_atividade"):
        raise PermissionDenied("Você não tem permissão para cadastrar atividades.")

    dados = {"nome": nome, "local": local, "monitor": monitor}
    erros = {campo: "Informe um texto." for campo, valor in dados.items() if not isinstance(valor, str)}
    if erros:
        raise ValidationError(erros)
    dados = {campo: valor.strip() for campo, valor in dados.items()}
    atividade = Atividade(**dados)
    atividade.full_clean()
    atividade.save()
    RegistroCadastroAtividade.objects.create(atividade=atividade, usuario=autor, dados=dados)
    return atividade


def _autorizar_grade(usuario, permissao):
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        raise PermissionDenied("É necessário um usuário autorizado para gerenciar a grade.")
    autor = get_user_model().objects.filter(pk=usuario.pk, is_active=True).first()
    if autor is None or not autor.has_perm(permissao):
        raise PermissionDenied("Você não tem permissão para esta ação na grade.")
    return autor


def _dados_horario(horario):
    return {"dia_semana": horario.dia_semana, "inicio": horario.inicio.isoformat(), "fim": horario.fim.isoformat()}


@transaction.atomic
def cadastrar_horario(*, usuario, atividade_id, dia_semana, inicio, fim):
    """Contrato provisório RF-ATV-02: adiciona um intervalo semanal à atividade."""
    autor = _autorizar_grade(usuario, "atividades.add_horarioatividade")
    atividade = Atividade.objects.get(pk=atividade_id)
    horario = HorarioAtividade(atividade=atividade, dia_semana=dia_semana, inicio=inicio, fim=fim)
    horario.full_clean()
    horario.save()
    RegistroGradeAtividade.objects.create(
        horario=horario, usuario=autor, acao=RegistroGradeAtividade.Acao.CADASTRO,
        dados_anteriores=None, dados_novos=_dados_horario(horario),
    )
    return horario


@transaction.atomic
def alterar_horario(*, usuario, atividade_id, horario_id, dia_semana, inicio, fim):
    """Altera somente um horário da atividade indicada, com auditoria atômica."""
    autor = _autorizar_grade(usuario, "atividades.change_horarioatividade")
    horario = HorarioAtividade.objects.select_for_update().get(pk=horario_id, atividade_id=atividade_id)
    anteriores = _dados_horario(horario)
    horario.dia_semana, horario.inicio, horario.fim = dia_semana, inicio, fim
    horario.full_clean()
    horario.save(update_fields=["dia_semana", "inicio", "fim"])
    RegistroGradeAtividade.objects.create(
        horario=horario, usuario=autor, acao=RegistroGradeAtividade.Acao.ALTERACAO,
        dados_anteriores=anteriores, dados_novos=_dados_horario(horario),
    )
    return horario


@transaction.atomic
def registrar_aula(*, usuario, atividade_id, data, inicio, fim, tipo=Aula.Tipo.NAO_INFORMADO):
    """RF-ATV-03/04: registra a realização e seu tipo, independentemente da grade.

    O padrão mantém a compatibilidade com o contrato anterior, sem inferir um tipo.
    Novos formulários exigem a escolha entre regular, extra e remarcada.
    """
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        raise PermissionDenied("É necessário um usuário autorizado para registrar aulas.")
    autor = get_user_model().objects.filter(pk=usuario.pk, is_active=True).first()
    if autor is None or not autor.has_perm("atividades.add_aula"):
        raise PermissionDenied("Você não tem permissão para registrar aulas.")
    atividade = Atividade.objects.get(pk=atividade_id)
    aula = Aula(atividade=atividade, data=data, inicio=inicio, fim=fim, tipo=tipo)
    aula.full_clean()
    aula.save()
    RegistroRealizacaoAula.objects.create(aula=aula, usuario=autor, dados={
        "atividade_id": atividade.pk, "data": aula.data.isoformat(),
        "inicio": aula.inicio.isoformat(), "fim": aula.fim.isoformat(),
        "tipo": aula.tipo,
    })
    return aula


def _autorizar_cancelamento(usuario, cadastro=False):
    if not usuario or not usuario.is_authenticated or usuario.pk is None:
        raise PermissionDenied("É necessário um usuário autorizado para cancelar aulas.")
    autor = get_user_model().objects.filter(pk=usuario.pk, is_active=True).first()
    if autor is None or not autor.has_perm("atividades.cancelar_aula"):
        raise PermissionDenied("Você não tem permissão para cancelar aulas.")
    if cadastro and not autor.has_perm("atividades.add_aula"):
        raise PermissionDenied("Você não tem permissão para registrar aulas.")
    return autor


def _dados_aula(aula):
    return {
        "atividade_id": aula.atividade_id, "data": aula.data.isoformat(),
        "inicio": aula.inicio.isoformat(), "fim": aula.fim.isoformat(),
        "tipo": aula.tipo, "situacao": aula.situacao,
    }


@transaction.atomic
def cancelar_aula(*, usuario, atividade_id, aula_id):
    """Cancela uma ocorrência existente sem apagar seus dados ou auditoria original."""
    autor = _autorizar_cancelamento(usuario)
    aula = Aula.objects.select_for_update().get(pk=aula_id, atividade_id=atividade_id)
    if aula.situacao == Aula.Situacao.CANCELADA:
        raise ValidationError("Esta aula já está cancelada.")
    anteriores = _dados_aula(aula)
    aula.situacao = Aula.Situacao.CANCELADA
    aula.save(update_fields=["situacao"])
    RegistroCancelamentoAula.objects.create(
        aula=aula, usuario=autor, dados_anteriores=anteriores, dados_novos=_dados_aula(aula),
    )
    return aula


@transaction.atomic
def registrar_aula_cancelada(*, usuario, atividade_id, data, inicio, fim, tipo=Aula.Tipo.NAO_INFORMADO):
    """Registra diretamente uma aula que não ocorreu; horários indicam o previsto."""
    autor = _autorizar_cancelamento(usuario, cadastro=True)
    atividade = Atividade.objects.get(pk=atividade_id)
    aula = Aula(atividade=atividade, data=data, inicio=inicio, fim=fim, tipo=tipo, situacao=Aula.Situacao.CANCELADA)
    aula.full_clean()
    aula.save()
    RegistroCancelamentoAula.objects.create(
        aula=aula, usuario=autor, dados_anteriores=None, dados_novos=_dados_aula(aula),
    )
    return aula
