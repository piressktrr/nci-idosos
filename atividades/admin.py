"""Admin somente leitura: inclusões e alterações passam pelos serviços, que auditam cada ação."""

from django.contrib import admin

from . import models


class SomenteLeituraAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(models.Atividade)
class AtividadeAdmin(SomenteLeituraAdmin):
    list_display = ("nome", "local", "monitor")
    search_fields = ("nome", "local", "monitor")


@admin.register(models.HorarioAtividade)
class HorarioAtividadeAdmin(SomenteLeituraAdmin):
    list_display = ("atividade", "dia_semana", "inicio", "fim")
    list_filter = ("dia_semana",)


@admin.register(models.Aula)
class AulaAdmin(SomenteLeituraAdmin):
    list_display = ("atividade", "data", "inicio", "fim", "tipo", "situacao")
    list_filter = ("situacao", "tipo")
    date_hierarchy = "data"


@admin.register(models.Inscricao)
class InscricaoAdmin(SomenteLeituraAdmin):
    list_display = ("atividade", "origem_participante", "participante_referencia", "cadastrada_em")
    list_filter = ("origem_participante",)


@admin.register(models.Frequencia)
class FrequenciaAdmin(SomenteLeituraAdmin):
    list_display = ("aula", "inscricao", "situacao", "motivo_descricao", "versao")
    list_filter = ("situacao",)


@admin.register(models.EsperaAtividade)
class EsperaAtividadeAdmin(SomenteLeituraAdmin):
    list_display = ("atividade", "participante_referencia", "situacao", "cadastrada_em")
    list_filter = ("situacao",)


@admin.register(models.ClassificacaoAtividade)
class ClassificacaoAtividadeAdmin(SomenteLeituraAdmin):
    list_display = ("atividade", "categoria_nome", "inicio")


admin.site.register(models.MotivoFalta, SomenteLeituraAdmin)
admin.site.register(models.CategoriaFMR, SomenteLeituraAdmin)


class EventoAuditoriaAdmin(SomenteLeituraAdmin):
    """Proxies de core.EventoAuditoria: o manager já filtra pelo tipo; o alvo é exibido pelo id."""

    list_display = ("registrado_em", "alvo_id", "acao", "usuario")
    list_select_related = ("usuario",)
    date_hierarchy = "registrado_em"
    fields = ("tipo", "alvo_id", "acao", "usuario", "registrado_em", "anteriores", "novos", "origem_id")
    readonly_fields = fields


for modelo in (
    models.RegistroCadastroAtividade, models.RegistroGradeAtividade, models.RegistroRealizacaoAula,
    models.RegistroCancelamentoAula, models.RegistroMotivoFalta, models.RegistroLancamentoFrequencia,
    models.RegistroCorrecaoFrequencia, models.RegistroEsperaAtividade, models.RegistroCategoriaFMR,
    models.RegistroClassificacaoAtividade,
):
    admin.site.register(modelo, EventoAuditoriaAdmin)
