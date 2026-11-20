from django.apps import AppConfig
from django.db.models.signals import post_migrate, pre_delete


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

        # Grupos Equipe e Administrador (RF-USR-02): só depois do post_migrate as permissões existem.
        from .perfis import garantir_perfis_pos_migrate

        post_migrate.connect(garantir_perfis_pos_migrate, sender=self, dispatch_uid="core_garantir_perfis")
