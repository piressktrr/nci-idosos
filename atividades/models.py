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


class Aula(models.Model):
    """Ocorrência realizada; horários efetivos independem da grade semanal."""

    atividade = models.ForeignKey(Atividade, on_delete=models.PROTECT, related_name="aulas")
    data = models.DateField("data da aula")
    inicio = models.TimeField("início efetivo")
    fim = models.TimeField("término efetivo")

    class Meta:
        ordering = ["-data", "-inicio", "-pk"]
        verbose_name = "aula realizada"
        verbose_name_plural = "aulas realizadas"
        constraints = [
            models.CheckConstraint(condition=models.Q(fim__gt=models.F("inicio")), name="aula_fim_apos_inicio"),
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
