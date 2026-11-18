"""Serviços do cadastro de participantes (RF-PAR-01, RN-PAR-01), com autorização e auditoria."""

from django.core.exceptions import ValidationError
from django.db import transaction

from core.permissoes import autorizar

from .auditoria import registrar
from .categorias import StatusParticipante, TipoMovimentacao
from .models import Movimentacao, Participante, SituacaoSocial, chave_busca

# Status é alterado somente no serviço de movimentações. Entrada fica na Movimentacao.
CAMPOS_CADASTRO = ("nome_completo", "data_nascimento", "sexo", "raca_cor", "identidade_genero",
                   "telefone_celular", "telefone_residencial", "origem_encaminhamento",
                   "endereco", "ensino_medio_completo", "observacao_encaminhamento")


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


def _verificar_duplicidade(participante, confirmar_duplicidade, excluir_id=None):
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
    registrar(participante=participante, acao="cadastro", usuario=autor, novos=_dados(participante, entrada))
    return participante


@transaction.atomic
def corrigir_participante(*, usuario, participante_id, data_entrada, confirmar_duplicidade=False, **dados):
    """Corrige o cadastro (inclusive raça/cor, identidade de gênero e data de entrada), guardando antes e depois.

    O status não é corrigido aqui (RN-PAR-09, P02). Cadastro sem entrada (feito fora dos serviços) ganha a entrada
    informada; na auditoria, a data anterior aparece vazia.
    """
    autor = autorizar(usuario, "participantes.change_participante",
                      mensagem="Você não tem permissão para corrigir participantes.")
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
    posteriores = participante.movimentacoes.exclude(tipo=TipoMovimentacao.ENTRADA)
    if posteriores.filter(data__lt=data_entrada).exists():
        raise ValidationError({"data_entrada": "A entrada não pode ser posterior a desligamentos ou reativações registrados."})
    if posteriores.filter(data__lt=participante.data_nascimento).exists():
        raise ValidationError({"data_nascimento": "O nascimento não pode ser posterior a movimentações registradas."})
    _validar(participante, entrada)
    if _dados(participante, entrada) == anteriores:
        return participante
    _verificar_duplicidade(participante, confirmar_duplicidade, excluir_id=participante.pk)
    participante.save(update_fields=list(CAMPOS_CADASTRO))
    entrada.save()
    registrar(participante=participante, acao="correcao", usuario=autor,
              anteriores=anteriores, novos=_dados(participante, entrada))
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
