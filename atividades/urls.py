from django.urls import path

from . import views

app_name = "atividades"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:atividade_id>/grade/", views.grade, name="grade"),
    path("<int:atividade_id>/grade/<int:horario_id>/editar/", views.editar_horario, name="editar_horario"),
    path("<int:atividade_id>/aulas/", views.aulas, name="aulas"),
    path("<int:atividade_id>/inscricoes/", views.inscricoes, name="inscricoes"),
    path("<int:atividade_id>/aulas/canceladas/nova/", views.nova_aula_cancelada, name="nova_aula_cancelada"),
    path("<int:atividade_id>/aulas/<int:aula_id>/cancelar/", views.confirmar_cancelamento, name="cancelar_aula"),
]
