"""Leituras da gestão de colaboradores: lista, perfil e histórico da conta (RF-USR-03, RNF-SEG-07)."""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db.models.functions import Lower

from .models import RegistroConta
from .services import autorizar_administrador

ROTULOS = {"username": "Usuário", "first_name": "Nome", "last_name": "Sobrenome", "email": "E-mail",
           "perfil": "Perfil", "senha": "Senha"}
ACOES = {"cadastro": "Cadastro", "correcao": "Correção", "senha": "Nova senha", "senha_recuperada": "Senha recuperada por e-mail",
         "ativacao": "Reativação", "desativacao": "Desativação"}
ROTULOS["is_active"] = "Conta ativa"


def pesquisar_colaboradores(termo, *, usuario):
    """Contas por nome, sobrenome ou usuário; cada palavra digitada precisa aparecer em algum deles."""
    autorizar_administrador(usuario)
    contas = get_user_model().objects.prefetch_related("groups").order_by(
        Lower("first_name"), Lower("last_name"), Lower("username"), "pk")
    for palavra in (termo or "")[:150].split():
        contas = contas.filter(Q(first_name__icontains=palavra) | Q(last_name__icontains=palavra)
                               | Q(username__icontains=palavra))
    return contas


def historico(conta, *, usuario):
    """Eventos da conta, do mais antigo para o mais recente (índice core_evento_alvo_idx)."""
    autorizar_administrador(usuario)
    return RegistroConta.objects.filter(alvo_id=conta.pk).select_related("usuario")


def _exibir(campo, valor):
    if isinstance(valor, bool):
        return "Sim" if valor else "Não"
    if campo == "perfil" and valor == "":
        return "Sem perfil"
    return valor


def diferencas(evento):
    """[(rótulo, antes, depois)] do evento. No cadastro e na nova senha, antes é None."""
    anteriores = evento.anteriores or {}
    return [(ROTULOS.get(campo, campo), _exibir(campo, anteriores.get(campo)) if evento.anteriores else None,
             _exibir(campo, valor)) for campo, valor in evento.novos.items()]
