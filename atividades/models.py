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
