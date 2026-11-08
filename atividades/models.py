from django.conf import settings
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
