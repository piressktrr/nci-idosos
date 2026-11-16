from django.contrib import admin

from .models import Movimentacao, Participante, SituacaoSocial


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


@admin.register(SituacaoSocial)
class SituacaoSocialAdmin(ParticipanteAdmin):
    list_display = ("participante", "vigente_desde", "mora_sozinho", "tem_apoio", "possui_deficiencia",
                    "recebe_bpc", "imigrante_refugiado")
    search_fields = ("participante__nome_completo",)


@admin.register(Movimentacao)
class MovimentacaoAdmin(ParticipanteAdmin):
    """Somente consulta: a entrada é registrada e corrigida pelos serviços do cadastro, que auditam."""

    list_display = ("participante", "tipo", "data", "usuario", "registrado_em")
    list_filter = ("tipo",)
    search_fields = ("participante__nome_completo",)
