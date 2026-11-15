from django.urls import path

from . import views

app_name = "participantes"
urlpatterns = [
    path("", views.lista, name="lista"),
    path("novo/", views.cadastrar, name="cadastrar"),
    path("<int:participante_id>/", views.detalhe, name="detalhe"),
    path("<int:participante_id>/corrigir/", views.corrigir, name="corrigir"),
]
