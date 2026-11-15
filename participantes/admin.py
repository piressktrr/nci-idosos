from django.contrib import admin

from .models import Participante


@admin.register(Participante)
class ParticipanteAdmin(admin.ModelAdmin):
    """Somente consulta: cadastro e correção passam pelos serviços, que auditam (RNF-SEG-07)."""

    list_display = ("nome_completo", "data_nascimento", "sexo", "cadastrado_em")
    search_fields = ("nome_completo",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
