from django.urls import path

from . import views

app_name = "usuarios"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.cadastrar, name="cadastrar"),
    path("<int:conta_id>/editar/", views.editar, name="editar"),
    path("<int:conta_id>/senha/", views.senha, name="senha"),
]
