from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import EventoAuditoria, ProtegidoPorAuditoria

from .categorias import (IDENTIDADES_GENERO_LEGADAS, IdentidadeGenero, OrigemEncaminhamento, RacaCor, Sexo, StatusParticipante,
                         TipoMovimentacao)
from .regras import (celular_valido, chave_nome, data_minima_nascimento, faixa_etaria_fmr_no_mes, formatar_telefone,
                     idade_em, normalizar_espacos, residencial_valido, so_digitos)

TAMANHO_NOME_BUSCA = 255


def chave_busca(nome):
    """Valor de `Participante.nome_busca` para um nome (ou termo de pesquisa): sem acentos, caixa e espaços extras."""
    return chave_nome(nome or "")[:TAMANHO_NOME_BUSCA]


class Participante(ProtegidoPorAuditoria, models.Model):
    """Identidade estável da pessoa (RF-PAR-01, RN-PAR-01): um cadastro por pessoa.

    Dados dos RF-PAR-01, 02 e 06 e os campos do protótipo aprovados na D13 (RNF-SEG-08). Raça/cor e identidade de gênero
    são corrigidas no próprio cadastro, sem vigência; a correção fica na auditoria.
    """

    nome_completo = models.CharField("nome completo", max_length=200)
    # RF-PAR-09 e RN-PAR-01: chave_nome(nome_completo), mantida pelo save, para pesquisa e duplicidade no banco
    # sem depender da extensão unaccent. Atualizações em massa (update/bulk_update) precisam preenchê-la.
    nome_busca = models.CharField("nome para busca", max_length=TAMANHO_NOME_BUSCA, blank=True, editable=False,
                                  db_index=True)
    data_nascimento = models.DateField("data de nascimento")
    sexo = models.CharField("sexo", max_length=1, choices=Sexo.choices)
    raca_cor = models.CharField("raça/cor autodeclarada", max_length=20, choices=RacaCor.choices)
    identidade_genero = models.CharField("identidade de gênero", max_length=20, choices=IdentidadeGenero.choices)
    # D13: campos do protótipo.
    endereco = models.CharField("endereço", max_length=255)
    ensino_medio_completo = models.BooleanField("ensino médio completo", null=True)
    # RF-PAR-02: contato do próprio participante; pelo menos um dos dois é obrigatório (validado no clean).
    telefone_celular = models.CharField("telefone celular", max_length=11, blank=True)
    telefone_residencial = models.CharField("telefone residencial", max_length=10, blank=True)
    # RF-PAR-06: só a categoria; o registro de entrada fica para a Movimentacao (RF-PAR-07/08).
    origem_encaminhamento = models.CharField("origem do encaminhamento", max_length=20,
                                             choices=OrigemEncaminhamento.choices)
    # RF-PAR-14 (P14, NCI 20/11/2026): origem em texto livre quando a categoria for "Outros".
    origem_descricao = models.CharField("descrição da origem", max_length=150, blank=True, default="")
    observacao_encaminhamento = models.TextField("observação sobre o encaminhamento", max_length=1000,
                                                 blank=True, default="")
    # Situação somente pelos serviços de movimentação, nunca por edição direta do cadastro.
    status = models.CharField("status", max_length=10, choices=StatusParticipante.choices,
                              default=StatusParticipante.ATIVO)
    cadastrado_em = models.DateTimeField("cadastrado em", auto_now_add=True)

    class Meta:
        ordering = ["nome_completo", "pk"]
        verbose_name = "participante"
        verbose_name_plural = "participantes"
        # RNF-SEG-11: exportação de todos os cadastros (dados sensíveis); o Administrador a recebe pelo
        # core.perfis (todas as permissões do app), a Equipe não.
        permissions = [("exportar_participante", "Pode exportar participantes")]
        indexes = [models.Index(fields=["data_nascimento"], name="participante_nascimento_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(sexo__in=Sexo.values), name="participante_sexo_valido"),
            models.CheckConstraint(condition=models.Q(raca_cor__in=RacaCor.values), name="participante_raca_cor_valida"),
            models.CheckConstraint(condition=models.Q(identidade_genero__in=[*IdentidadeGenero.values, *IDENTIDADES_GENERO_LEGADAS]),
                                   name="participante_identidade_genero_valida"),
            models.CheckConstraint(condition=models.Q(status__in=StatusParticipante.values),
                                   name="participante_status_valido"),
            # Vazio só para cadastros anteriores ao RF-PAR-06; o clean exige a origem em cadastro e correção.
            models.CheckConstraint(condition=models.Q(origem_encaminhamento__in=[*OrigemEncaminhamento.values, ""]),
                                   name="participante_origem_encaminhamento_valida"),
        ]

    def __str__(self):
        return self.nome_completo

    def save(self, *args, **kwargs):
        self.nome_busca = chave_busca(self.nome_completo)
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "nome_completo" in update_fields:
            kwargs["update_fields"] = {*update_fields, "nome_busca"}
        super().save(*args, **kwargs)

    def clean_fields(self, exclude=None):
        # Telefones chegam com máscara do formulário; o limite de 10/11 caracteres vale para os dígitos.
        self._normalizar_telefones()
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        if isinstance(self.nome_completo, str):
            self.nome_completo = normalizar_espacos(self.nome_completo)
            if not self.nome_completo:
                raise ValidationError({"nome_completo": "Informe o nome completo."})
            self.nome_busca = chave_busca(self.nome_completo)
        if self.data_nascimento:
            if self.data_nascimento > timezone.localdate():
                raise ValidationError({"data_nascimento": "A data de nascimento não pode estar no futuro."})
            if self.data_nascimento < data_minima_nascimento():
                raise ValidationError({"data_nascimento": "Confira a data de nascimento informada."})
        # Endereço e ensino médio são obrigatórios pelo próprio campo (blank=False), validado no full_clean.
        # Só espaços passa no clean_fields; depois de normalizar, vazio também é recusado.
        if isinstance(self.endereco, str):
            self.endereco = normalizar_espacos(self.endereco)
            if not self.endereco:
                raise ValidationError({"endereco": "Informe o endereço."})
        if isinstance(self.observacao_encaminhamento, str):
            self.observacao_encaminhamento = self.observacao_encaminhamento.strip()
        self._validar_origem_descricao()
        self._validar_telefones()

    def _validar_origem_descricao(self):
        """RF-PAR-14: a descrição só existe com a origem "Outros".

        A obrigatoriedade é cobrada na tela (ParticipanteForm), para não invalidar cadastros antigos com "Outros"
        nem os serviços chamados por outros módulos; aqui só normaliza e descarta a descrição fora de "Outros".
        """
        descricao = normalizar_espacos(self.origem_descricao) if isinstance(self.origem_descricao, str) else ""
        self.origem_descricao = descricao if self.origem_encaminhamento == OrigemEncaminhamento.OUTRA else ""

    def origem_formatada(self):
        """Categoria da origem, com a descrição quando for "Outros" (RF-PAR-14)."""
        rotulo = self.get_origem_encaminhamento_display()
        return f"{rotulo}: {self.origem_descricao}" if self.origem_descricao else rotulo

    def _normalizar_telefones(self):
        """RF-PAR-02: guarda só os dígitos (único lugar onde a máscara é retirada)."""
        self.telefone_celular = so_digitos(self.telefone_celular)
        self.telefone_residencial = so_digitos(self.telefone_residencial)

    def _validar_telefones(self):
        """RF-PAR-02: só dígitos, com DDD; exige pelo menos um telefone."""
        self._normalizar_telefones()
        erros = {}
        if self.telefone_celular and not celular_valido(self.telefone_celular):
            erros["telefone_celular"] = "Informe o celular com DDD e 9 dígitos, por exemplo (61) 91234-5678."
        if self.telefone_residencial and not residencial_valido(self.telefone_residencial):
            erros["telefone_residencial"] = "Informe o telefone residencial com DDD e 8 dígitos, por exemplo (61) 3123-4567."
        if not self.telefone_celular and not self.telefone_residencial:
            erros["telefone_celular"] = "Informe pelo menos um telefone do próprio participante (celular ou residencial)."
        if erros:
            raise ValidationError(erros)

    def celular_formatado(self):
        return formatar_telefone(self.telefone_celular)

    def residencial_formatado(self):
        return formatar_telefone(self.telefone_residencial)

    def contato_principal_formatado(self):
        """RF-PAR-02: o número do próprio participante; o celular quando houver."""
        return self.celular_formatado() or self.residencial_formatado()

    def idade(self, referencia=None):
        return idade_em(self.data_nascimento, referencia or timezone.localdate())

    def faixa_etaria(self, referencia=None):
        """RN-PAR-06 e RN-PAR-07: calculada da data de nascimento, pela idade no dia 1º do mês de `referencia`."""
        return faixa_etaria_fmr_no_mes(self.data_nascimento, referencia or timezone.localdate())

    @property
    def entrada(self):
        """Movimentação de entrada (Q5), ou None em cadastros sem ela (ex. criados fora dos serviços)."""
        if self.pk is None:
            return None
        return self.movimentacoes.filter(tipo=TipoMovimentacao.ENTRADA).order_by("-data", "-pk").first()

    @property
    def data_entrada(self):
        entrada = self.entrada
        return entrada.data if entrada else None


class PerfilDemografico(models.Model):
    """Sexo e autodeclarações vigentes a partir de uma data."""

    participante = models.ForeignKey(Participante, on_delete=models.PROTECT, related_name="perfis_demograficos")
    vigente_desde = models.DateField()
    sexo = models.CharField(max_length=1, choices=Sexo.choices)
    raca_cor = models.CharField(max_length=20, choices=RacaCor.choices)
    identidade_genero = models.CharField(max_length=20, choices=IdentidadeGenero.choices)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["participante", "vigente_desde"], name="perfil_demografico_vigencia"),
            models.CheckConstraint(condition=models.Q(sexo__in=Sexo.values, raca_cor__in=RacaCor.values,
                identidade_genero__in=IdentidadeGenero.values), name="perfil_demografico_categorias_validas"),
        ]


class SituacaoSocial(models.Model):
    """RF-PAR-04 e RF-PAR-05: situação social com vigência por data de início (D2).

    Cada linha vale de `vigente_desde` até a próxima linha do mesmo participante. Assim o
    relatório de um mês usa a situação daquele mês, e não a atual (RN-PAR-05, RN-FMR-12).
    """

    participante = models.ForeignKey(Participante, on_delete=models.PROTECT, related_name="situacoes_sociais")
    vigente_desde = models.DateField("vigente desde")
    mora_sozinho = models.BooleanField("mora sozinho")
    tem_apoio = models.BooleanField("tem apoio familiar ou comunitário")
    possui_deficiencia = models.BooleanField("possui deficiência")
    recebe_bpc = models.BooleanField("recebe BPC")
    imigrante_refugiado = models.BooleanField("imigrante ou refugiado")
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        # Pelo id, sem JOIN com Participante (a ordenação "participante" herdaria a do nome).
        ordering = ["participante_id", "-vigente_desde"]
        verbose_name = "situação social"
        verbose_name_plural = "situações sociais"
        constraints = [models.UniqueConstraint(fields=["participante", "vigente_desde"],
                                               name="situacao_social_uma_por_data")]

    def __str__(self):
        return f"{self.participante} desde {self.vigente_desde:%d/%m/%Y}"

    def clean(self):
        super().clean()
        if self.vigente_desde:
            if self.vigente_desde > timezone.localdate():
                raise ValidationError({"vigente_desde": "A data de início não pode estar no futuro."})
            nascimento = self.participante.data_nascimento if self.participante_id else None
            if nascimento and self.vigente_desde < nascimento:
                raise ValidationError({"vigente_desde": "A data de início não pode ser anterior ao nascimento."})

    @classmethod
    def vigente_em(cls, participante, data):
        """Situação que valia na data (RN-PAR-05). None se ainda não havia registro."""
        return cls.objects.filter(participante=participante, vigente_desde__lte=data).order_by("-vigente_desde").first()


class MotivoDesligamento(ProtegidoPorAuditoria, models.Model):
    descricao = models.CharField("descrição", max_length=150, unique=True)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["descricao", "pk"]

    def __str__(self):
        return self.descricao


class Movimentacao(models.Model):
    """Histórico de entrada, desligamento, reativação e afastamento, auditado no participante."""

    participante = models.ForeignKey(Participante, on_delete=models.PROTECT, related_name="movimentacoes")
    tipo = models.CharField("tipo", max_length=20, choices=TipoMovimentacao.choices)
    motivo = models.ForeignKey(MotivoDesligamento, null=True, blank=True, on_delete=models.PROTECT)
    motivo_descricao = models.CharField(max_length=150, blank=True, default="", editable=False)
    origem_entrada = models.CharField("origem no ingresso", max_length=20,
        choices=OrigemEncaminhamento.choices, blank=True, default="", editable=False)
    data = models.DateField("data")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+",
                                verbose_name="registrado por")
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)

    class Meta:
        ordering = ["participante_id", "data", "pk"]
        verbose_name = "movimentação"
        verbose_name_plural = "movimentações"
        constraints = [
            models.CheckConstraint(condition=models.Q(tipo__in=TipoMovimentacao.values),
                                   name="movimentacao_tipo_valido"),
            models.CheckConstraint(condition=(models.Q(tipo="desligamento", motivo__isnull=False)
                | (~models.Q(tipo="desligamento") & models.Q(motivo__isnull=True, motivo_descricao=""))),
                name="movimentacao_motivo_coerente"),
            # Retornos não geram nova entrada (RN-PAR-08).
            models.UniqueConstraint(fields=["participante"], condition=models.Q(tipo=TipoMovimentacao.ENTRADA),
                                    name="movimentacao_uma_entrada"),
            models.CheckConstraint(condition=models.Q(origem_entrada__in=[*OrigemEncaminhamento.values, ""]),
                                   name="movimentacao_origem_valida"),
            models.CheckConstraint(condition=models.Q(tipo="entrada") | models.Q(origem_entrada=""),
                                   name="movimentacao_origem_so_entrada"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} de {self.participante} em {self.data:%d/%m/%Y}"

    def clean(self):
        super().clean()
        if self.data:
            if self.data > timezone.localdate():
                raise ValidationError({"data": "A data não pode estar no futuro."})
            # O participante pode ainda não estar salvo (validação do cadastro antes de gravar).
            participante = getattr(self, "participante", None)
            nascimento = participante.data_nascimento if participante else None
            if nascimento and self.data < nascimento:
                raise ValidationError({"data": "A data não pode ser anterior ao nascimento."})


class RegistroParticipante(EventoAuditoria):
    """Cadastro, correção e situação social do participante (RNF-SEG-07), na tabela única core.EventoAuditoria."""

    alvo, modelo_alvo = "participante", Participante

    class Meta:
        proxy = True
        default_permissions = ()


class RegistroExportacao(EventoAuditoria):
    """Exportação dos participantes (RNF-SEG-11): o alvo é a conta que exportou.

    Guarda só quantidade e formato; nenhum dado pessoal dos participantes vai para o evento.
    """

    alvo, modelo_alvo = "exportador", settings.AUTH_USER_MODEL

    class Meta:
        proxy = True
        default_permissions = ()


class RegistroMotivoDesligamento(EventoAuditoria):
    alvo, modelo_alvo = "motivo_desligamento", MotivoDesligamento

    class Meta:
        proxy = True
        default_permissions = ()
