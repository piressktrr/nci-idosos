from django.urls import path

from . import views

app_name = "atividades"
urlpatterns = [path("", views.lista, name="lista")]
