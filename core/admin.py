from django.contrib import admin

from .models import RegistroAuditoria


@admin.register(RegistroAuditoria)
class RegistroAuditoriaAdmin(admin.ModelAdmin):
    """Consulta da auditoria; inclusão somente pelos serviços."""

    list_display = ("registrado_em", "acao", "content_type", "object_id", "usuario")
    list_filter = ("acao", "content_type")
    date_hierarchy = "registrado_em"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
