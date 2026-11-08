from datetime import time

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Atividade(models.Model):
    """Contrato provisório para o cadastro inicial de atividades (RF-ATV-01)."""

    nome = models.CharField("identificação", max_length=150)
    local = models.CharField("local", max_length=150)
    monitor = models.CharField("monitor/oficineiro responsável", max_length=150)

    class Meta:
        ordering = ["nome"]
        verbose_name = "atividade"
        verbose_name_plural = "atividades"

    def __str__(self):
        return self.nome


class RegistroCadastroAtividade(models.Model):
    """Evidência do cadastro, com os valores originais e seu responsável."""

    atividade = models.OneToOneField(
        Atividade, on_delete=models.PROTECT, related_name="registro_cadastro"
    )
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    dados = models.JSONField()

    class Meta:
        default_permissions = ()
        verbose_name = "registro de cadastro de atividade"
        verbose_name_plural = "registros de cadastro de atividades"


class HorarioAtividade(models.Model):
    class DiaSemana(models.IntegerChoices):
        SEGUNDA = 0, "Segunda-feira"
        TERCA = 1, "Terça-feira"
        QUARTA = 2, "Quarta-feira"
        QUINTA = 3, "Quinta-feira"
        SEXTA = 4, "Sexta-feira"
        SABADO = 5, "Sábado"
        DOMINGO = 6, "Domingo"

    atividade = models.ForeignKey(Atividade, on_delete=models.PROTECT, related_name="horarios")
    dia_semana = models.PositiveSmallIntegerField("dia da semana", choices=DiaSemana.choices)
    inicio = models.TimeField("início")
    fim = models.TimeField("término")

    class Meta:
        ordering = ["dia_semana", "inicio", "pk"]
        verbose_name = "horário de atividade"
        verbose_name_plural = "horários de atividades"
        constraints = [
            models.CheckConstraint(condition=models.Q(dia_semana__gte=0, dia_semana__lte=6), name="horario_dia_valido"),
            models.CheckConstraint(condition=models.Q(fim__gt=models.F("inicio")), name="horario_fim_apos_inicio"),
        ]

    def clean(self):
        super().clean()
        for campo in ("inicio", "fim"):
            valor = getattr(self, campo)
            if isinstance(valor, time) and valor.tzinfo is not None:
                raise ValidationError({campo: "Informe um horário local, sem fuso horário."})
        if isinstance(self.inicio, time) and isinstance(self.fim, time) and self.fim <= self.inicio:
            raise ValidationError({"fim": "O término deve ser posterior ao início, no mesmo dia."})


class RegistroGradeAtividade(models.Model):
    class Acao(models.TextChoices):
        CADASTRO = "cadastro", "Cadastro"
        ALTERACAO = "alteracao", "Alteração"

    horario = models.ForeignKey(HorarioAtividade, on_delete=models.PROTECT, related_name="registros")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    acao = models.CharField(max_length=10, choices=Acao.choices)
    dados_anteriores = models.JSONField(null=True)
    dados_novos = models.JSONField()

    class Meta:
        default_permissions = ()


class AulaQuerySet(models.QuerySet):
    def com_categoria_fmr(self):
        """Categoria pela vigência iniciada até a data da ocorrência."""
        vigencia = ClassificacaoAtividade.objects.filter(
            atividade_id=models.OuterRef("atividade_id"), inicio__lte=models.OuterRef("data")).order_by("-inicio")
        return self.annotate(categoria_fmr_id=models.Subquery(vigencia.values("categoria_id")[:1]),
                             categoria_fmr_nome=models.Subquery(vigencia.values("categoria_nome")[:1]))

    def realizadas(self):
        """Base de consulta para totais de realização; exclui cancelamentos (RN-ATV-06)."""
        return self.filter(situacao="realizada")


class Aula(models.Model):
    """Ocorrência realizada ou cancelada, independente da grade semanal."""

    class Situacao(models.TextChoices):
        REALIZADA = "realizada", "Realizada"
        CANCELADA = "cancelada", "Cancelada"

    class Tipo(models.TextChoices):
        NAO_INFORMADO = "nao_informado", "Não informado"
        REGULAR = "regular", "Regular"
        EXTRA = "extra", "Extra"
        REMARCADA = "remarcada", "Remarcada"

    atividade = models.ForeignKey(Atividade, on_delete=models.PROTECT, related_name="aulas")
    data = models.DateField("data da aula")
    inicio = models.TimeField("início efetivo")
    fim = models.TimeField("término efetivo")
    tipo = models.CharField("tipo de aula", max_length=13, choices=Tipo.choices, default=Tipo.NAO_INFORMADO)
    situacao = models.CharField("situação", max_length=9, choices=Situacao.choices, default=Situacao.REALIZADA)
    objects = AulaQuerySet.as_manager()

    class Meta:
        ordering = ["-data", "-inicio", "-pk"]
        verbose_name = "aula"
        verbose_name_plural = "aulas"
        permissions = [("cancelar_aula", "Pode registrar cancelamento de aula")]
        constraints = [
            models.CheckConstraint(condition=models.Q(fim__gt=models.F("inicio")), name="aula_fim_apos_inicio"),
            models.CheckConstraint(
                condition=models.Q(tipo__in=["nao_informado", "regular", "extra", "remarcada"]),
                name="aula_tipo_valido",
            ),
            models.CheckConstraint(condition=models.Q(situacao__in=["realizada", "cancelada"]), name="aula_situacao_valida"),
        ]

    def clean(self):
        super().clean()
        for campo in ("inicio", "fim"):
            valor = getattr(self, campo)
            if isinstance(valor, time) and valor.tzinfo is not None:
                raise ValidationError({campo: "Informe um horário local, sem fuso horário."})
        if isinstance(self.inicio, time) and isinstance(self.fim, time) and self.fim <= self.inicio:
            raise ValidationError({"fim": "O término deve ser posterior ao início, no mesmo dia."})


class RegistroRealizacaoAula(models.Model):
    """Auditoria da inclusão de uma aula realizada, com seus dados originais."""

    aula = models.OneToOneField(Aula, on_delete=models.PROTECT, related_name="registro_realizacao")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    dados = models.JSONField()

    class Meta:
        default_permissions = ()


class RegistroCancelamentoAula(models.Model):
    aula = models.OneToOneField(Aula, on_delete=models.PROTECT, related_name="registro_cancelamento")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    dados_anteriores = models.JSONField(null=True)
    dados_novos = models.JSONField()

    class Meta:
        default_permissions = ()


class Inscricao(models.Model):
    """Vínculo com identidade externa provisória, sem duplicar o cadastro da pessoa."""

    atividade = models.ForeignKey(Atividade, on_delete=models.PROTECT, related_name="inscricoes")
    origem_participante = models.CharField(max_length=40)
    participante_referencia = models.CharField(max_length=64)
    cadastrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    cadastrada_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-cadastrada_em", "-pk"]
        verbose_name = "inscrição"
        verbose_name_plural = "inscrições"
        constraints = [
            models.UniqueConstraint(fields=["atividade", "origem_participante", "participante_referencia"], name="inscricao_participante_atividade_unica"),
        ]


class MotivoFalta(models.Model):
    descricao = models.CharField("descrição", max_length=150)
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["descricao", "pk"]
        verbose_name = "motivo de falta"
        verbose_name_plural = "motivos de falta"

    def __str__(self):
        return self.descricao


class RegistroMotivoFalta(models.Model):
    motivo = models.ForeignKey(MotivoFalta, on_delete=models.PROTECT)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    anteriores = models.JSONField(null=True)
    novos = models.JSONField()

    class Meta:
        default_permissions = ()


class Frequencia(models.Model):
    class Situacao(models.TextChoices):
        PRESENTE = "presente", "Presente"
        AUSENTE = "ausente", "Ausente"
        JUSTIFICADO = "ausente_justificado", "Ausente justificado"

    aula = models.ForeignKey(Aula, on_delete=models.PROTECT, related_name="frequencias")
    inscricao = models.ForeignKey(Inscricao, on_delete=models.PROTECT, related_name="frequencias")
    situacao = models.CharField(max_length=20, choices=Situacao.choices)
    motivo = models.ForeignKey(MotivoFalta, on_delete=models.PROTECT, null=True, blank=True)
    motivo_descricao = models.CharField(max_length=150, blank=True, default="", editable=False)
    observacao = models.TextField("observação", max_length=1000, blank=True, default="")
    versao = models.PositiveIntegerField(default=1, editable=False)

    class Meta:
        verbose_name = "frequência"
        verbose_name_plural = "frequências"
        constraints = [
            models.UniqueConstraint(fields=["aula", "inscricao"], name="frequencia_aula_inscricao_unica"),
            models.CheckConstraint(condition=models.Q(situacao__in=["presente", "ausente", "ausente_justificado"]), name="frequencia_situacao_valida"),
        ]

    def clean(self):
        super().clean()
        if self.situacao != self.Situacao.JUSTIFICADO and (self.motivo_id or self.observacao or self.motivo_descricao):
            raise ValidationError("Motivo e observação pertencem somente à ausência justificada.")
        atividade_aula = Aula.objects.filter(pk=self.aula_id).values_list("atividade_id", flat=True).first()
        atividade_inscricao = Inscricao.objects.filter(pk=self.inscricao_id).values_list("atividade_id", flat=True).first()
        if atividade_aula and atividade_inscricao and atividade_aula != atividade_inscricao:
            raise ValidationError({"inscricao": "A inscrição não pertence à atividade da aula."})


class RegistroLancamentoFrequencia(models.Model):
    frequencia = models.OneToOneField(Frequencia, on_delete=models.PROTECT, related_name="registro_lancamento")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    dados = models.JSONField()

    class Meta:
        default_permissions = ()


class RegistroCorrecaoFrequencia(models.Model):
    frequencia = models.ForeignKey(Frequencia, on_delete=models.PROTECT, related_name="correcoes")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    anteriores = models.JSONField()
    novos = models.JSONField()

    class Meta:
        default_permissions = ()
        ordering = ["registrado_em", "pk"]


class CategoriaFMR(models.Model):
    nome = models.CharField(max_length=150)
    ativa = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome", "pk"]
        default_permissions = ("view",)
        verbose_name = "categoria FMR"

    def __str__(self):
        return self.nome


class EsperaAtividade(models.Model):
    class Situacao(models.TextChoices):
        AGUARDANDO = "aguardando", "Aguardando"
        INSCRITO = "inscrito", "Inscrito"
        RETIRADO = "retirado", "Retirado"

    atividade = models.ForeignKey(Atividade, on_delete=models.PROTECT, related_name="lista_espera")
    origem_participante = models.CharField(max_length=40)
    participante_referencia = models.CharField(max_length=64)
    situacao = models.CharField(max_length=10, choices=Situacao.choices, default=Situacao.AGUARDANDO)
    cadastrada_em = models.DateTimeField(auto_now_add=True)
    inscricao = models.OneToOneField(Inscricao, on_delete=models.PROTECT, null=True, blank=True)

    class Meta:
        ordering = ["cadastrada_em", "pk"]
        default_permissions = ("add", "view", "change")
        constraints = [
            models.UniqueConstraint(fields=["atividade", "origem_participante", "participante_referencia"],
                condition=models.Q(situacao="aguardando"), name="espera_ativa_participante_unica"),
            models.CheckConstraint(condition=models.Q(situacao__in=["aguardando", "inscrito", "retirado"]), name="espera_situacao_valida"),
            models.CheckConstraint(condition=(models.Q(situacao="inscrito", inscricao__isnull=False)
                | models.Q(situacao__in=["aguardando", "retirado"], inscricao__isnull=True)), name="espera_inscricao_coerente"),
        ]


class RegistroEsperaAtividade(models.Model):
    espera = models.ForeignKey(EsperaAtividade, on_delete=models.PROTECT, related_name="registros")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    anteriores = models.JSONField(null=True)
    novos = models.JSONField()

    class Meta:
        default_permissions = ()


class ClassificacaoAtividade(models.Model):
    atividade = models.ForeignKey(Atividade, on_delete=models.PROTECT, related_name="classificacoes")
    categoria = models.ForeignKey(CategoriaFMR, on_delete=models.PROTECT)
    categoria_nome = models.CharField(max_length=150, editable=False)
    inicio = models.DateField("vigente a partir de")

    class Meta:
        ordering = ["-inicio", "-pk"]
        default_permissions = ()
        constraints = [models.UniqueConstraint(fields=["atividade", "inicio"], name="classificacao_atividade_inicio_unico")]


class RegistroCategoriaFMR(models.Model):
    categoria = models.ForeignKey(CategoriaFMR, on_delete=models.PROTECT)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    anteriores = models.JSONField(null=True)
    novos = models.JSONField()

    class Meta:
        default_permissions = ()


class RegistroClassificacaoAtividade(models.Model):
    classificacao = models.ForeignKey(ClassificacaoAtividade, on_delete=models.PROTECT, related_name="registros")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    registrado_em = models.DateTimeField(auto_now_add=True)
    anteriores = models.JSONField(null=True)
    novos = models.JSONField()

    class Meta:
        default_permissions = ()
