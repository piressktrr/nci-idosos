from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models


class RegistroAuditoria(models.Model):
    """Tabela única de auditoria (RNF-SEG-07): quem, quando, o quê e como era antes.

    Os registros são somente de inclusão: não podem ser alterados nem excluídos.
    """

    content_type = models.ForeignKey(ContentType, on_delete=models.PROTECT, verbose_name="tipo de registro")
    object_id = models.CharField("identificador do registro", max_length=64)
    acao = models.CharField("ação", max_length=40)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name="usuário")
    registrado_em = models.DateTimeField("registrado em", auto_now_add=True)
    anteriores = models.JSONField("valores anteriores", null=True, blank=True)
    novos = models.JSONField("valores novos")

    class Meta:
        ordering = ["registrado_em", "pk"]
        default_permissions = ("view",)
        verbose_name = "registro de auditoria"
        verbose_name_plural = "registros de auditoria"
        indexes = [models.Index(fields=["content_type", "object_id"], name="auditoria_objeto_idx")]

    def __str__(self):
        return f"{self.acao} · {self.content_type.model} {self.object_id}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("Registros de auditoria não podem ser alterados.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Registros de auditoria não podem ser excluídos.")
