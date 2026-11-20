"""
Rotas principais do sistema NCI Idade Dourada.

Início, entrada/saída (autenticação padrão do Django), os apps de atividades,
participantes e colaboradores (contas de acesso) e o admin.
"""
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

from core.views import inicio

urlpatterns = [
    path('', inicio, name='inicio'),
    path('entrar/', LoginView.as_view(template_name='nci/login.html', redirect_authenticated_user=True), name='entrar'),
    path('entrar/', include('usuarios.urls_recuperacao')),
    path('sair/', LogoutView.as_view(), name='sair'),
    path('atividades/', include('atividades.urls')),
    path('participantes/', include('participantes.urls')),
    path('colaboradores/', include('usuarios.urls')),
    path('fmr/', include('relatorios.urls')),
    path('admin/', admin.site.urls),
]
