from django.urls import path

from . import views

app_name = "atividades"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("frequencia-mensal/", views.frequencia_mensal, name="frequencia_mensal"),
    path("motivos-falta/", views.motivos_falta, name="motivos_falta"),
    path("motivos-falta/<int:motivo_id>/editar/", views.motivos_falta, name="editar_motivo_falta"),
    path("<int:atividade_id>/grade/", views.grade, name="grade"),
    path("<int:atividade_id>/grade/<int:horario_id>/editar/", views.editar_horario, name="editar_horario"),
    path("<int:atividade_id>/aulas/", views.aulas, name="aulas"),
    path("<int:atividade_id>/aulas/<int:aula_id>/frequencias/<int:frequencia_id>/", views.detalhe_frequencia, name="detalhe_frequencia"),
    path("<int:atividade_id>/aulas/<int:aula_id>/chamada/", views.chamada, name="chamada"),
    path("<int:atividade_id>/aulas/<int:aula_id>/chamada/registrar/", views.lancar_frequencias, name="lancar_frequencias"),
    path("<int:atividade_id>/inscricoes/", views.inscricoes, name="inscricoes"),
    path("<int:atividade_id>/aulas/canceladas/nova/", views.nova_aula_cancelada, name="nova_aula_cancelada"),
    path("<int:atividade_id>/aulas/<int:aula_id>/cancelar/", views.confirmar_cancelamento, name="cancelar_aula"),
]
