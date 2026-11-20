from django.urls import path

from . import views
from . import views_movimentacoes as movimentos

app_name = "participantes"
urlpatterns = [
    path("motivos-desligamento/", movimentos.motivos, name="motivos_desligamento"),
    path("motivos-desligamento/<int:motivo_id>/editar/", movimentos.motivos, name="editar_motivo_desligamento"),
    path("<int:participante_id>/movimentacoes/", movimentos.movimentar, name="movimentar"),
    path("", views.lista, name="lista"),
    path("novo/", views.cadastrar, name="cadastrar"),
    path("exportar/", views.exportar, name="exportar"),
    path("<int:participante_id>/", views.detalhe, name="detalhe"),
    path("<int:participante_id>/corrigir/", views.corrigir, name="corrigir"),
    path("<int:participante_id>/situacao-social/", views.situacao_social, name="situacao_social"),
]
