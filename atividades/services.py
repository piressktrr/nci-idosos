"""Serviços provisórios de atividades, grade e aulas, com autorização e auditoria."""

from calendar import monthrange
from datetime import date, time

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from core.permissoes import autorizar
from .models import (
    MENSAGEM_AULA_DUPLICADA, Atividade, Aula, HorarioAtividade, RegistroCadastroAtividade,
    RegistroGradeAtividade, RegistroRealizacaoAula, RegistroCancelamentoAula, Inscricao,
    Frequencia, RegistroLancamentoFrequencia, MotivoFalta, RegistroMotivoFalta, RegistroCorrecaoFrequencia,
)
from .integracoes.participantes import obter_provedor
from .situacao import exigir_atividade_ativa


def consultar_frequencia_mensal(*, usuario, ano, mes, atividade_id=None):
    """RF-ATV-11: totais de lançamentos atuais por ocorrência, sem inferir faltas.

    Consulta operacional local; não representa indicadores ou classificação FMR.
    A origem do contrato provisório separa frequências fictícias das reais.
    """
    autorizar(usuario, "atividades.view_atividade", "atividades.view_aula", "atividades.view_frequencia")
    if type(ano) is not int or type(mes) is not int or not 1 <= ano <= 9999 or not 1 <= mes <= 12:
        raise ValidationError("Informe um mês e ano válidos.")
    atividades = Atividade.objects.all()
    if atividade_id is not None:
        atividade = atividades.get(pk=atividade_id)
        atividades = atividades.filter(pk=atividade.pk)
    provedor = obter_provedor()
    periodo = Q(aulas__data__range=(date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])),
                aulas__situacao=Aula.Situacao.REALIZADA)
    origem = Q(aulas__frequencias__inscricao__origem_participante=provedor.origem)
    contagens = {"aulas_realizadas": Count("aulas", filter=periodo, distinct=True)}
    for chave, situacao in (("presentes", "presente"), ("ausentes", "ausente"),
                            ("justificados", "ausente_justificado")):
        contagens[chave] = Count("aulas__frequencias", distinct=True,
            filter=periodo & origem & Q(aulas__frequencias__situacao=situacao))
    linhas = list(atividades.order_by("nome", "pk").annotate(**contagens))
    totais = {chave: sum(getattr(item, chave) for item in linhas) for chave in contagens}
    for item in linhas:
        item.total_registros = item.presentes + item.ausentes + item.justificados
    totais["total_registros"] = totais["presentes"] + totais["ausentes"] + totais["justificados"]
    return {"linhas": linhas, "totais": totais, "demonstracao": provedor.demonstracao}


@transaction.atomic
def cadastrar_atividade(*, usuario, nome, local, monitor):
    """Cadastra e audita em uma transação; exige atividades.add_atividade."""
    autor = autorizar(usuario, "atividades.add_atividade", mensagem="Você não tem permissão para cadastrar atividades.")

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
    return autorizar(usuario, permissao, mensagem="Você não tem permissão para esta ação na grade.")


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
    Aula realizada não pode ter data futura nem repetir data e início de outra realizada da mesma atividade.
    """
    autor = autorizar(usuario, "atividades.add_aula", mensagem="Você não tem permissão para registrar aulas.")
    # O bloqueio da atividade serializa registros concorrentes (ex.: duplo clique em "Salvar chamada").
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    exigir_atividade_ativa(atividade)
    if type(data) is date and data > timezone.localdate():
        raise ValidationError({"data": "Aula realizada não pode ter data futura. Registre-a depois que acontecer."})
    if type(data) is date and type(inicio) is time and Aula.objects.realizadas().filter(
            atividade=atividade, data=data, inicio=inicio).exists():
        raise ValidationError(MENSAGEM_AULA_DUPLICADA)
    aula = Aula(atividade=atividade, data=data, inicio=inicio, fim=fim, tipo=tipo)
    aula.full_clean()  # Também valida a constraint aula_realizada_unica, já sob o bloqueio.
    aula.save()
    RegistroRealizacaoAula.objects.create(aula=aula, usuario=autor, dados={
        "atividade_id": atividade.pk, "data": aula.data.isoformat(),
        "inicio": aula.inicio.isoformat(), "fim": aula.fim.isoformat(),
        "tipo": aula.tipo,
    })
    return aula


def _autorizar_cancelamento(usuario, cadastro=False):
    autor = autorizar(usuario, "atividades.cancelar_aula", mensagem="Você não tem permissão para cancelar aulas.")
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
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    exigir_atividade_ativa(atividade)
    aula = Aula(atividade=atividade, data=data, inicio=inicio, fim=fim, tipo=tipo, situacao=Aula.Situacao.CANCELADA)
    aula.full_clean()
    aula.save()
    RegistroCancelamentoAula.objects.create(
        aula=aula, usuario=autor, dados_anteriores=None, dados_novos=_dados_aula(aula),
    )
    return aula


@transaction.atomic
def inscrever_participante(*, usuario, atividade_id, participante_referencia, espera_id=None, vaga_confirmada=False):
    """RF-ATV-06: valida a identidade no provedor e grava o vínculo com autoria."""
    autor = autorizar(usuario, "atividades.add_inscricao", mensagem="Você não tem permissão para registrar inscrições.")
    if not isinstance(participante_referencia, str) or not participante_referencia.strip() or len(participante_referencia) > 64:
        raise ValidationError({"participante_referencia": "Selecione um participante cadastrado."})
    # Serializa inscrições da mesma atividade, inclusive a verificação de duplicação.
    atividade = Atividade.objects.select_for_update().get(pk=atividade_id)
    exigir_atividade_ativa(atividade)
    provedor = obter_provedor()
    estados = getattr(provedor, "situacoes_em", lambda data: {})(timezone.localdate())
    if estados.get(participante_referencia) == "desligamento":
        raise ValidationError("Participante desligado. Registre a reativação antes de inscrever.")
    participante = provedor.obter(participante_referencia)
    if participante is None:
        raise ValidationError({"participante_referencia": "Participante não encontrado no cadastro."})
    if Inscricao.objects.filter(atividade=atividade, origem_participante=provedor.origem,
                               participante_referencia=participante.referencia).exists():
        raise ValidationError({"participante_referencia": "Este participante já está inscrito nesta atividade."})
    from .espera import validar_atendimento, registrar_atendimento
    espera = validar_atendimento(usuario=autor, atividade=atividade, provedor=provedor, participante=participante,
        espera_id=espera_id, vaga_confirmada=vaga_confirmada, estados=estados)
    inscricao = Inscricao(
        atividade=atividade, origem_participante=provedor.origem,
        participante_referencia=participante.referencia, cadastrada_por=autor,
    )
    inscricao.full_clean()
    inscricao.save()
    if espera is not None:
        registrar_atendimento(espera=espera, inscricao=inscricao, usuario=autor)
    return inscricao


def obter_lista_chamada(*, usuario, atividade_id, aula_id):
    """RF-ATV-07: consulta vínculos atuais; não infere frequência nem vigência histórica."""
    autor = autorizar(usuario, "atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao",
                      mensagem="Você não tem permissão para consultar a chamada.")
    aula = Aula.objects.select_related("atividade").get(pk=aula_id, atividade_id=atividade_id)
    if aula.situacao == Aula.Situacao.CANCELADA:
        raise ValidationError("Esta aula está cancelada e não possui chamada.")
    provedor = obter_provedor()
    nomes = {item.referencia: item.nome for item in provedor.listar()}
    estados = getattr(provedor, "situacoes_em", lambda data: {})(aula.data)
    inscricoes_com_registro = set(aula.frequencias.values_list("inscricao_id", flat=True))
    participantes = [{
        "inscricao_id": inscricao.pk,
        "referencia": inscricao.participante_referencia,
        "nome": nomes.get(inscricao.participante_referencia, "Participante indisponível"),
        "disponivel": inscricao.participante_referencia in nomes,
        "afastado": estados.get(inscricao.participante_referencia) == "afastamento",
    } for inscricao in aula.atividade.inscricoes.filter(origem_participante=provedor.origem)
       if estados.get(inscricao.participante_referencia) not in ("desligamento", "nao_ingressou")
       or inscricao.pk in inscricoes_com_registro]
    participantes.sort(key=lambda item: (item["nome"].casefold(), item["referencia"]))
    pode_ver = autor.has_perm("atividades.view_frequencia")
    frequencias = {item.inscricao_id: item for item in aula.frequencias.all()} if pode_ver else {}
    for participante in participantes:
        participante["frequencia"] = frequencias.get(participante["inscricao_id"])
    return {
        "aula": aula, "participantes": participantes, "demonstracao": provedor.demonstracao,
        "pode_ver_frequencia": pode_ver,
        "pode_registrar_frequencia": pode_ver and autor.has_perm("atividades.add_frequencia"),
    }


@transaction.atomic
def registrar_frequencias(*, usuario, atividade_id, aula_id, registros, justificativas=None):
    """Lançamento inicial explícito por inscrição; lote atômico, sem correção implícita.

    Só recebem frequência as inscrições em `registros`: quem fica sem situação (por exemplo, quem ainda não fazia
    parte da turma numa chamada retroativa) não ganha registro.
    """
    autor = autorizar(usuario, "atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao",
                      "atividades.view_frequencia", "atividades.add_frequencia",
                      mensagem="Você não tem permissão para lançar frequência.")
    if not isinstance(registros, dict) or not registros:
        raise ValidationError("Selecione ao menos uma situação para lançar.")
    for identificador, situacao in registros.items():
        if type(identificador) is not int or identificador <= 0 or situacao not in Frequencia.Situacao.values:
            raise ValidationError("Inscrição ou situação inválida.")
    # O cancelamento usa o mesmo bloqueio: não há lançamento concorrente em aula cancelada.
    aula = Aula.objects.select_for_update().get(pk=aula_id, atividade_id=atividade_id)
    if aula.situacao != Aula.Situacao.REALIZADA:
        raise ValidationError("Não é possível lançar frequência em aula cancelada.")
    provedor = obter_provedor()
    inscricoes = list(Inscricao.objects.select_for_update().filter(
        pk__in=registros, atividade_id=atividade_id, origem_participante=provedor.origem,
    ).order_by("pk"))
    if len(inscricoes) != len(registros):
        raise ValidationError("Há inscrição inválida para esta atividade ou origem de participantes.")
    getattr(provedor, "bloquear", lambda referencias: None)([i.participante_referencia for i in inscricoes])
    estados = getattr(provedor, "situacoes_em", lambda data: {})(aula.data)
    if any(estados.get(i.participante_referencia) in ("desligamento", "nao_ingressou") for i in inscricoes):
        raise ValidationError("Há participante desligado ou ainda não ingressante na data desta aula.")
    if aula.frequencias.filter(inscricao_id__in=registros).exists():
        raise ValidationError("Há frequência já lançada. Use a ação de correção do registro.")
    for inscricao in inscricoes:
        if provedor.obter(inscricao.participante_referencia) is None:
            raise ValidationError("Há participante indisponível. Confira o cadastro antes de lançar.")
    justificativas = {} if justificativas is None else justificativas
    if not isinstance(justificativas, dict):
        raise ValidationError("Justificativas inválidas.")
    ids_motivos = sorted({dados.get("motivo_id") for dados in justificativas.values()
                         if isinstance(dados, dict) and type(dados.get("motivo_id")) is int})
    motivos_ativos = {motivo.pk: motivo for motivo in MotivoFalta.objects.select_for_update().filter(
        pk__in=ids_motivos, ativo=True,
    ).order_by("pk")}
    detalhes = {}
    for identificador, dados in justificativas.items():
        if type(identificador) is not int or identificador not in registros or registros[identificador] != Frequencia.Situacao.JUSTIFICADO:
            raise ValidationError("Justificativa sem ausência justificada correspondente.")
        if not isinstance(dados, dict) or set(dados) - {"motivo_id", "observacao"}:
            raise ValidationError("Dados da justificativa inválidos.")
        observacao = dados.get("observacao", "")
        if not isinstance(observacao, str) or len(observacao) > 1000:
            raise ValidationError("Observação deve ser um texto de até 1000 caracteres.")
        motivo_id = dados.get("motivo_id")
        motivo = None
        if motivo_id is not None:
            if type(motivo_id) is not int:
                raise ValidationError("Motivo inválido.")
            motivo = motivos_ativos.get(motivo_id)
            if motivo is None:
                raise ValidationError("Motivo não encontrado ou desativado.")
        detalhes[identificador] = (motivo, observacao.strip())
    resultado = []
    for inscricao in inscricoes:
        motivo, observacao = detalhes.get(inscricao.pk, (None, ""))
        situacao = registros[inscricao.pk]
        # Só a conversão automática de "ausente" do afastado é marcada como justificada por afastamento; o
        # "ausente justificado" escolhido pela equipe é manual e um retorno retroativo não o reverte.
        convertida = (estados.get(inscricao.participante_referencia) == "afastamento"
                      and situacao == Frequencia.Situacao.AUSENTE)
        if convertida:
            situacao = Frequencia.Situacao.JUSTIFICADO
        frequencia = Frequencia(aula=aula, inscricao=inscricao, situacao=situacao,
                                motivo=motivo, motivo_descricao=motivo.descricao if motivo else "", observacao=observacao)
        if convertida:
            frequencia.motivo_descricao = "Afastamento"
            frequencia.justificada_por_afastamento = True
        frequencia.full_clean()
        frequencia.save()
        RegistroLancamentoFrequencia.objects.create(frequencia=frequencia, usuario=autor, dados={
            "aula_id": aula.pk, "atividade_id": atividade_id, "data": aula.data.isoformat(),
            "inscricao_id": inscricao.pk, "origem_participante": inscricao.origem_participante,
            "participante_referencia": inscricao.participante_referencia, "situacao": frequencia.situacao,
            "motivo_id": frequencia.motivo_id, "motivo_descricao": frequencia.motivo_descricao,
            "observacao": frequencia.observacao,
        })
        resultado.append(frequencia)
    return resultado


@transaction.atomic
def salvar_motivo_falta(*, usuario, descricao, ativo=True, motivo_id=None):
    permissao = "atividades.change_motivofalta" if motivo_id is not None else "atividades.add_motivofalta"
    autor = autorizar(usuario, permissao)
    if not isinstance(descricao, str) or type(ativo) is not bool:
        raise ValidationError("Informe descrição textual e situação válida.")
    motivo = MotivoFalta.objects.select_for_update().get(pk=motivo_id) if motivo_id is not None else MotivoFalta()
    anteriores = {"descricao": motivo.descricao, "ativo": motivo.ativo} if motivo.pk else None
    motivo.descricao, motivo.ativo = descricao.strip(), ativo
    motivo.full_clean()
    motivo.save()
    RegistroMotivoFalta.objects.create(motivo=motivo, usuario=autor, anteriores=anteriores,
                                      novos={"descricao": motivo.descricao, "ativo": motivo.ativo})
    return motivo


def consultar_frequencia(*, usuario, atividade_id, aula_id, frequencia_id):
    autor = autorizar(usuario, "atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao",
                      "atividades.view_frequencia")
    frequencia = Frequencia.objects.select_related("aula__atividade", "inscricao", "motivo").get(
        pk=frequencia_id, aula_id=aula_id, aula__atividade_id=atividade_id, inscricao__atividade_id=atividade_id,
    )
    provedor = obter_provedor()
    if frequencia.inscricao.origem_participante != provedor.origem:
        raise Frequencia.DoesNotExist
    participante = provedor.obter(frequencia.inscricao.participante_referencia)
    return {"frequencia": frequencia, "nome": participante.nome if participante else "Participante indisponível",
            "demonstracao": provedor.demonstracao, "pode_corrigir": autor.has_perm("atividades.change_frequencia")}


def consultar_historico_participante(*, usuario, atividade_id, inscricao_id):
    """RF-ATV-12: histórico preservado mesmo sem identidade disponível no provedor."""
    autorizar(usuario, "atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao",
              "atividades.view_frequencia")
    provedor = obter_provedor()
    inscricao = Inscricao.objects.select_related("atividade").get(
        pk=inscricao_id, atividade_id=atividade_id, origem_participante=provedor.origem)
    participante = provedor.obter(inscricao.participante_referencia)
    frequencias = Frequencia.objects.filter(inscricao=inscricao, aula__atividade_id=atividade_id).select_related("aula").order_by(
        "-aula__data", "-aula__inicio", "-aula_id", "-pk")
    total_presencas = frequencias.filter(situacao=Frequencia.Situacao.PRESENTE,
        aula__situacao=Aula.Situacao.REALIZADA).count()
    return {"inscricao": inscricao, "atividade": inscricao.atividade,
            "nome": participante.nome if participante else "Participante indisponível",
            "demonstracao": provedor.demonstracao, "frequencias": frequencias, "total_presencas": total_presencas}


def _snapshot_frequencia(frequencia):
    return {"situacao": frequencia.situacao, "motivo_id": frequencia.motivo_id,
            "motivo_descricao": frequencia.motivo_descricao, "observacao": frequencia.observacao,
            "versao": frequencia.versao} | ({"justificada_por_afastamento": True} if frequencia.justificada_por_afastamento else {})


@transaction.atomic
def corrigir_frequencia(*, usuario, atividade_id, aula_id, frequencia_id, versao_esperada,
                       situacao, motivo_id=None, observacao=""):
    contexto = consultar_frequencia(usuario=usuario, atividade_id=atividade_id, aula_id=aula_id, frequencia_id=frequencia_id)
    if not contexto["pode_corrigir"]:
        raise PermissionDenied("Você não tem permissão para corrigir frequência.")
    # Mesmo bloqueio/ordem de lançamento e cancelamento; IDs do vínculo não são editáveis.
    # Critério igual ao do lançamento: só fica "justificada por afastamento" a conversão automática (ausente de
    # afastado, ou a automática mantida sem motivo nem observação). A escolha manual da equipe não é revertida.
    Aula.objects.select_for_update().get(pk=aula_id, atividade_id=atividade_id)
    provedor = obter_provedor()
    referencia = contexto["frequencia"].inscricao.participante_referencia
    getattr(provedor, "bloquear", lambda referencias: None)([referencia])
    frequencia = Frequencia.objects.select_for_update().get(pk=frequencia_id, aula_id=aula_id)
    if type(versao_esperada) is not int or versao_esperada != frequencia.versao:
        raise ValidationError("Este registro foi alterado. Atualize a página e confira o histórico antes de salvar.")
    if situacao not in Frequencia.Situacao.values or not isinstance(observacao, str) or len(observacao) > 1000:
        raise ValidationError("Situação ou observação inválida.")
    observacao = observacao.strip()
    if situacao != Frequencia.Situacao.JUSTIFICADO and (motivo_id is not None or observacao):
        raise ValidationError("Motivo e observação só se aplicam à ausência justificada.")
    if motivo_id is not None and type(motivo_id) is not int:
        raise ValidationError("Motivo inválido.")
    anteriores = _snapshot_frequencia(frequencia)
    afastado = getattr(provedor, "situacoes_em", lambda data: {})(frequencia.aula.data).get(referencia) == "afastamento"
    automatica = afastado and (situacao == Frequencia.Situacao.AUSENTE or (
        situacao == Frequencia.Situacao.JUSTIFICADO and motivo_id is None and not observacao
        and frequencia.justificada_por_afastamento))
    if automatica:
        situacao = Frequencia.Situacao.JUSTIFICADO
    if motivo_id != frequencia.motivo_id:
        motivo = MotivoFalta.objects.select_for_update().filter(pk=motivo_id, ativo=True).first() if motivo_id is not None else None
        if motivo_id is not None and motivo is None:
            raise ValidationError("Motivo não encontrado ou desativado.")
        frequencia.motivo = motivo
        frequencia.motivo_descricao = motivo.descricao if motivo else ""
    frequencia.situacao, frequencia.observacao = situacao, observacao
    if frequencia.justificada_por_afastamento and not automatica and motivo_id is None:
        frequencia.motivo_descricao = ""
    frequencia.justificada_por_afastamento = automatica
    if automatica:
        frequencia.motivo_descricao = "Afastamento"
    frequencia.full_clean()
    if _snapshot_frequencia(frequencia) == anteriores:
        return frequencia
    frequencia.versao += 1
    frequencia.save(update_fields=["situacao", "motivo", "motivo_descricao", "observacao", "versao", "justificada_por_afastamento"])
    RegistroCorrecaoFrequencia.objects.create(frequencia=frequencia, usuario=usuario,
                                             anteriores=anteriores, novos=_snapshot_frequencia(frequencia))
    return frequencia
