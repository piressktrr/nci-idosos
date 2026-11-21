"""Serviços do cadastro de participantes (RF-PAR-01, RN-PAR-01), com autorização e auditoria."""

from datetime import date

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from core.permissoes import autorizar

from .auditoria import registrar
from .categorias import IdentidadeGenero, OrigemEncaminhamento, StatusParticipante, TipoMovimentacao
from .models import Movimentacao, Participante, PerfilDemografico, SituacaoSocial, chave_busca

# Status é alterado somente no serviço de movimentações. Entrada fica na Movimentacao.
CAMPOS_CADASTRO = ("nome_completo", "data_nascimento", "sexo", "raca_cor", "identidade_genero",
                   "telefone_celular", "telefone_residencial", "origem_encaminhamento", "origem_descricao",
                   "endereco", "ensino_medio_completo", "observacao_encaminhamento")
CAMPOS_DEMOGRAFICOS = ("sexo", "raca_cor", "identidade_genero")


def _dados(participante, entrada=None):
    """Dados auditados do cadastro; a data de entrada entra no mesmo evento (cadastro ou correção)."""
    return {
        "nome_completo": participante.nome_completo,
        "data_nascimento": participante.data_nascimento.isoformat(),
        "sexo": participante.sexo,
        "raca_cor": participante.raca_cor,
        "identidade_genero": participante.identidade_genero,
        "telefone_celular": participante.telefone_celular,
        "telefone_residencial": participante.telefone_residencial,
        "origem_encaminhamento": participante.origem_encaminhamento,
        "origem_descricao": participante.origem_descricao,
        "endereco": participante.endereco,
        "ensino_medio_completo": participante.ensino_medio_completo,
        "observacao_encaminhamento": participante.observacao_encaminhamento,
        "status": participante.status,
        "data_entrada": entrada.data.isoformat() if entrada and entrada.data else None,
    }


def _validar(participante, entrada):
    """full_clean do participante e da entrada juntos, com o erro da data no campo `data_entrada` do formulário."""
    erros = {}
    try:
        participante.full_clean()
    except ValidationError as erro:
        erros.update(erro.message_dict)
    try:
        # Participante e usuário vêm do próprio serviço; a unicidade da entrada fica com o banco.
        entrada.full_clean(exclude=["participante", "usuario"], validate_constraints=False)
    except ValidationError as erro:
        for campo, mensagens in erro.message_dict.items():
            erros.setdefault("data_entrada" if campo == "data" else campo, []).extend(mensagens)
    if erros:
        raise ValidationError(erros)


def possiveis_duplicados(*, nome_completo, data_nascimento, excluir_id=None):
    """RN-PAR-01: mesmos nome (sem acento/caixa) e data de nascimento.

    É só um alerta: o documento para identificar duplicidade ainda será escolhido pelo NCI (P18).
    """
    if not isinstance(nome_completo, str) or not data_nascimento:
        return []
    return list(Participante.objects.filter(data_nascimento=data_nascimento, nome_busca=chave_busca(nome_completo))
                .exclude(pk=excluir_id))


def pesquisar_participantes(termo):
    """RF-PAR-09: lista por nome, ignorando acentos, maiúsculas e espaços extras.

    Cada palavra digitada precisa aparecer no nome, em qualquer ordem ("silva ana" acha "Ana Silva").
    A comparação é feita no banco sobre `nome_busca`, normalizado em Python pela mesma função do termo,
    sem depender da extensão unaccent do PostgreSQL.
    """
    participantes = Participante.objects.all()
    for palavra in chave_busca(termo)[:200].split():
        participantes = participantes.filter(nome_busca__contains=palavra)
    return participantes


def _travar_identidade(participante):
    """RN-PAR-01: serializa cadastros e correções da mesma pessoa (nome normalizado + nascimento).

    Sem o lock, dois envios simultâneos (duplo clique em "Salvar") passam juntos pela checagem de duplicidade e criam
    dois cadastros que depois não podem ser excluídos. O advisory lock do PostgreSQL vale até o fim da transação.
    """
    chave = f"participante:{chave_busca(participante.nome_completo)}:{participante.data_nascimento}"
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", [chave])


def _verificar_duplicidade(participante, confirmar_duplicidade, excluir_id=None):
    _travar_identidade(participante)
    duplicados = possiveis_duplicados(nome_completo=participante.nome_completo,
                                      data_nascimento=participante.data_nascimento, excluir_id=excluir_id)
    if duplicados and confirmar_duplicidade is not True:
        raise ValidationError(
            "Já existe participante com o mesmo nome e data de nascimento. Confira se é a mesma pessoa; "
            "quem retorna ao serviço deve manter o cadastro existente.",
            code="possivel_duplicado",
        )


@transaction.atomic
def cadastrar_participante(*, usuario, data_entrada, confirmar_duplicidade=False, **dados):
    """RF-PAR-01: cadastra a pessoa uma única vez, com a entrada (Q5), e audita na mesma transação.

    Sempre ativo (RN-PAR-09, P02). Um único evento de cadastro guarda os dados e a data de entrada.
    """
    autor = autorizar(usuario, "participantes.add_participante",
                      mensagem="Você não tem permissão para cadastrar participantes.")
    dados.setdefault("origem_descricao", "")  # RF-PAR-14: opcional fora da origem "Outros"
    if set(dados) != set(CAMPOS_CADASTRO):
        raise ValidationError("Dados de cadastro incompletos ou inválidos.")
    participante = Participante(**dados, status=StatusParticipante.ATIVO)
    entrada = Movimentacao(participante=participante, tipo=TipoMovimentacao.ENTRADA, data=data_entrada,
                          usuario=autor, origem_entrada=participante.origem_encaminhamento)
    _validar(participante, entrada)
    _verificar_duplicidade(participante, confirmar_duplicidade)
    participante.save()
    entrada.participante = participante
    entrada.save()
    PerfilDemografico.objects.create(participante=participante, vigente_desde=data_entrada,
                                    **{campo: dados[campo] for campo in CAMPOS_DEMOGRAFICOS})
    registrar(participante=participante, acao="cadastro", usuario=autor, novos=_dados(participante, entrada))
    return participante


def _cobrir_perfil_desde_a_entrada(participante, data_entrada, anteriores, novos):
    """RF-PAR-05 / RN-FMR-12: o perfil demográfico precisa valer desde a entrada.

    O primeiro perfil nasce no cadastro, com a data de entrada. Se a entrada for antecipada, o início do primeiro
    perfil acompanha; se o cadastro não tiver perfil (anterior à migration 0013), cria-se um com os valores que
    valiam antes desta correção. Sem isso, os meses entre a entrada e o primeiro perfil ficam sem sexo, raça/cor e
    identidade de gênero e o FMR deixa essas tabelas em branco para todos.
    """
    primeiro = participante.perfis_demograficos.order_by("vigente_desde").first()
    if primeiro is None:
        valores = {campo: anteriores[campo] for campo in CAMPOS_DEMOGRAFICOS}
        if valores["identidade_genero"] not in IdentidadeGenero.values:
            return  # categoria legada sem equivalente no FMR: o perfil começa na próxima vigência informada
        PerfilDemografico.objects.create(participante=participante, vigente_desde=data_entrada, **valores)
        anteriores["perfil_inicio"], novos["perfil_inicio"] = None, data_entrada.isoformat()
    elif primeiro.vigente_desde > data_entrada:
        anteriores["perfil_inicio"], novos["perfil_inicio"] = primeiro.vigente_desde.isoformat(), data_entrada.isoformat()
        PerfilDemografico.objects.filter(pk=primeiro.pk).update(vigente_desde=data_entrada)


@transaction.atomic
def corrigir_participante(*, usuario, participante_id, data_entrada, perfil_vigente_desde=None,
                         origem_entrada=None, confirmar_duplicidade=False, **dados):
    """Corrige o cadastro (inclusive raça/cor, identidade de gênero e data de entrada), guardando antes e depois.

    O status não é corrigido aqui (RN-PAR-09, P02). Cadastro sem entrada (feito fora dos serviços) ganha a entrada
    informada; na auditoria, a data anterior aparece vazia.
    """
    autor = autorizar(usuario, "participantes.change_participante",
                      mensagem="Você não tem permissão para corrigir participantes.")
    dados.setdefault("origem_descricao", "")  # RF-PAR-14: opcional fora da origem "Outros"
    if set(dados) != set(CAMPOS_CADASTRO):
        raise ValidationError("Dados de cadastro incompletos ou inválidos.")
    participante = Participante.objects.select_for_update().get(pk=participante_id)
    entrada = (Movimentacao.objects.select_for_update().filter(participante=participante, tipo=TipoMovimentacao.ENTRADA)
               .order_by("-data", "-pk").first())
    anteriores = _dados(participante, entrada)
    if entrada is None:
        # Entrada histórica ausente: não presumir sua origem a partir do cadastro atual.
        entrada = Movimentacao(participante=participante, tipo=TipoMovimentacao.ENTRADA, usuario=autor)
    else:
        entrada.participante = participante  # a validação usa a data de nascimento corrigida
    for campo, valor in dados.items():
        setattr(participante, campo, valor)
    entrada.data = data_entrada
    if origem_entrada is not None:
        # RF-FMR-07 / Q13: a origem do ingresso só é informada quando falta; a existente nunca é sobrescrita.
        if entrada.origem_entrada:
            raise ValidationError({"origem_entrada": "A origem do ingresso já está registrada."})
        if origem_entrada not in OrigemEncaminhamento.values:
            raise ValidationError({"origem_entrada": "Escolha uma origem válida."})
        anteriores["origem_entrada"], entrada.origem_entrada = "", origem_entrada
    posteriores = participante.movimentacoes.exclude(tipo=TipoMovimentacao.ENTRADA)
    if posteriores.filter(data__lt=data_entrada).exists():
        raise ValidationError({"data_entrada": "A entrada não pode ser posterior a desligamentos ou reativações registrados."})
    if posteriores.filter(data__lt=participante.data_nascimento).exists():
        raise ValidationError({"data_nascimento": "O nascimento não pode ser posterior a movimentações registradas."})
    _validar(participante, entrada)
    novos = _dados(participante, entrada)
    if "origem_entrada" in anteriores:
        novos["origem_entrada"] = entrada.origem_entrada
    _cobrir_perfil_desde_a_entrada(participante, data_entrada, anteriores, novos)
    if perfil_vigente_desde is not None or any(novos[campo] != anteriores[campo] for campo in CAMPOS_DEMOGRAFICOS):
        vigencia = timezone.localdate() if perfil_vigente_desde is None else perfil_vigente_desde
        if type(vigencia) is not date or not data_entrada <= vigencia <= timezone.localdate():
            raise ValidationError({"perfil_vigente_desde": "Informe uma data entre a entrada e hoje."})
        ultimo = participante.perfis_demograficos.filter(vigente_desde__lte=vigencia).order_by("-vigente_desde").first()
        perfil = {campo: novos[campo] for campo in CAMPOS_DEMOGRAFICOS}
        anteriores["perfil_vigente_desde"] = ultimo.vigente_desde.isoformat() if ultimo else None
        novos["perfil_vigente_desde"] = vigencia.isoformat()
        PerfilDemografico.objects.update_or_create(participante=participante, vigente_desde=vigencia, defaults=perfil)
    if novos == anteriores:
        return participante
    _verificar_duplicidade(participante, confirmar_duplicidade, excluir_id=participante.pk)
    participante.save(update_fields=list(CAMPOS_CADASTRO))
    entrada.save()
    registrar(participante=participante, acao="correcao", usuario=autor,
              anteriores=anteriores, novos=novos)
    return participante


CAMPOS_SITUACAO = ("mora_sozinho", "tem_apoio", "possui_deficiencia", "recebe_bpc", "imigrante_refugiado")


def _dados_situacao(situacao):
    return {"vigente_desde": situacao.vigente_desde.isoformat(),
            **{campo: getattr(situacao, campo) for campo in CAMPOS_SITUACAO}}


@transaction.atomic
def registrar_situacao_social(*, usuario, participante_id, vigente_desde, **indicadores):
    """RF-PAR-04/05: registra a situação a partir de uma data, sem apagar as anteriores.

    Se já existe registro com a mesma data de início, é correção desse registro (antes e depois
    na auditoria). Uma data nova cria uma nova vigência.
    """
    autor = autorizar(usuario, "participantes.change_participante",
                      mensagem="Você não tem permissão para alterar participantes.")
    if set(indicadores) != set(CAMPOS_SITUACAO) or not all(isinstance(v, bool) for v in indicadores.values()):
        raise ValidationError("Dados da situação social incompletos ou inválidos.")
    participante = Participante.objects.select_for_update().get(pk=participante_id)
    situacao = SituacaoSocial.objects.filter(participante=participante, vigente_desde=vigente_desde).first()
    anteriores = _dados_situacao(situacao) if situacao else None
    if situacao is None:
        situacao = SituacaoSocial(participante=participante, vigente_desde=vigente_desde)
    for campo, valor in indicadores.items():
        setattr(situacao, campo, valor)
    situacao.full_clean(validate_unique=anteriores is None)
    if anteriores is not None and _dados_situacao(situacao) == anteriores:
        return situacao
    situacao.save()
    # A coluna acao da auditoria tem 10 caracteres; a correção se distingue por ter "anteriores".
    registrar(participante=participante, acao="situacao", usuario=autor, anteriores=anteriores, novos=_dados_situacao(situacao))
    return situacao
