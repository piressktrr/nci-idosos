from django.urls import path

from .views import atividades, aulas, classificacao, espera, frequencia, grade, inscricoes

app_name = "atividades"
urlpatterns = [
    path("", atividades.lista, name="lista"),
    path("categorias-fmr/", classificacao.categorias, name="categorias_fmr"),
    path("categorias-fmr/<int:categoria_id>/editar/", classificacao.categorias, name="editar_categoria_fmr"),
    path("<int:atividade_id>/classificacao-fmr/", classificacao.classificacao, name="classificacao_fmr"),
    path("frequencia-mensal/", frequencia.frequencia_mensal, name="frequencia_mensal"),
    path("motivos-falta/", frequencia.motivos_falta, name="motivos_falta"),
    path("motivos-falta/<int:motivo_id>/editar/", frequencia.motivos_falta, name="editar_motivo_falta"),
    path("<int:atividade_id>/grade/", grade.grade, name="grade"),
    path("<int:atividade_id>/grade/<int:horario_id>/editar/", grade.editar_horario, name="editar_horario"),
    path("<int:atividade_id>/aulas/", aulas.aulas, name="aulas"),
    path("<int:atividade_id>/aulas/<int:aula_id>/frequencias/<int:frequencia_id>/", frequencia.detalhe_frequencia, name="detalhe_frequencia"),
    path("<int:atividade_id>/aulas/<int:aula_id>/chamada/", frequencia.chamada, name="chamada"),
    path("<int:atividade_id>/aulas/<int:aula_id>/chamada/registrar/", frequencia.lancar_frequencias, name="lancar_frequencias"),
    path("<int:atividade_id>/inscricoes/", inscricoes.inscricoes, name="inscricoes"),
    path("<int:atividade_id>/espera/", espera.lista_espera, name="lista_espera"),
    path("<int:atividade_id>/espera/<int:espera_id>/atender/", espera.atender_espera, name="atender_espera"),
    path("<int:atividade_id>/espera/<int:espera_id>/retirar/", espera.atender_espera, {"retirar": True}, name="retirar_espera"),
    path("<int:atividade_id>/inscricoes/<int:inscricao_id>/frequencia/", frequencia.historico_participante, name="historico_participante"),
    path("<int:atividade_id>/aulas/canceladas/nova/", aulas.nova_aula_cancelada, name="nova_aula_cancelada"),
    path("<int:atividade_id>/aulas/<int:aula_id>/cancelar/", aulas.confirmar_cancelamento, name="cancelar_aula"),
]
