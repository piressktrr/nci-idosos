from django.urls import path

from . import views

app_name = "atividades"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("<int:atividade_id>/grade/", views.grade, name="grade"),
    path("<int:atividade_id>/grade/<int:horario_id>/editar/", views.editar_horario, name="editar_horario"),
]
