from django.apps import AppConfig
from django.db.models.signals import pre_delete


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Núcleo comum"

    def ready(self):
        # Sem FK, a exclusão de objetos auditados é barrada aqui (ver core.models).
        from .models import TIPOS_AUDITORIA, bloquear_exclusao_auditada

        for modelo in {proxy.modelo_alvo_resolvido() for proxy in TIPOS_AUDITORIA.values()}:
            pre_delete.connect(bloquear_exclusao_auditada, sender=modelo,
                               dispatch_uid=f"auditoria_protege_{modelo._meta.label_lower}")
