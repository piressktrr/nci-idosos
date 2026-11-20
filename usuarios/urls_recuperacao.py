"""Rotas públicas do "esqueci minha senha" (RF-USR-05), sob /entrar/."""

from django.urls import path

from . import recuperacao

urlpatterns = [
    path("esqueci-senha/", recuperacao.PedirRecuperacao.as_view(), name="recuperar_senha"),
    path("esqueci-senha/enviado/", recuperacao.RecuperacaoEnviada.as_view(), name="recuperacao_enviada"),
    path("redefinir/<uidb64>/<token>/", recuperacao.RedefinirSenha.as_view(), name="redefinir_senha"),
    path("redefinir/concluido/", recuperacao.RecuperacaoConcluida.as_view(), name="recuperacao_concluida"),
]
