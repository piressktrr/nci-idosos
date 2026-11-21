"""RF-USR-05 (NCI 20/11/2026): "esqueci minha senha" por e-mail, com as telas e o token do próprio Django.

O link chega só ao e-mail cadastrado na conta (único por conta), vale por PASSWORD_RESET_TIMEOUT e só funciona
uma vez. Contas inativas ou sem senha utilizável não recebem e-mail (regra do PasswordResetForm), e um link pedido
antes da desativação deixa de valer (o token inclui `is_active`). A tela de pedido responde igual exista ou não a
conta, para não revelar quais e-mails estão cadastrados. A nova senha passa pelos AUTH_PASSWORD_VALIDATORS e é
gravada na mesma transação da auditoria em RegistroConta, sem a senha nem o hash.
"""

from django.contrib.auth import views as auth_views
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import transaction
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator

from .forms import aplicar_bootstrap
from .models import RegistroConta

PASTA = "usuarios/recuperacao"


class TokenRecuperacao(PasswordResetTokenGenerator):
    """Token do Django que também perde a validade quando a conta é desativada (ou reativada)."""

    key_salt = "usuarios.recuperacao.TokenRecuperacao"

    def _make_hash_value(self, user, timestamp):
        return f"{super()._make_hash_value(user, timestamp)}{user.is_active}"


token_recuperacao = TokenRecuperacao()


class PedirRecuperacao(auth_views.PasswordResetView):
    template_name = f"{PASTA}/pedido.html"
    email_template_name = f"{PASTA}/email.txt"
    subject_template_name = f"{PASTA}/assunto.txt"
    success_url = reverse_lazy("recuperacao_enviada")
    token_generator = token_recuperacao

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["email"].label = "E-mail cadastrado"
        aplicar_bootstrap(form)
        return form


class RecuperacaoEnviada(auth_views.PasswordResetDoneView):
    template_name = f"{PASTA}/enviado.html"


class RedefinirSenha(auth_views.PasswordResetConfirmView):
    template_name = f"{PASTA}/redefinir.html"
    success_url = reverse_lazy("recuperacao_concluida")
    token_generator = token_recuperacao

    def get_user(self, uidb64):
        usuario = super().get_user(uidb64)
        return usuario if usuario is not None and usuario.is_active else None

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["new_password1"].label = "Nova senha"
        form.fields["new_password2"].label = "Confirme a nova senha"
        aplicar_bootstrap(form)
        return form

    @method_decorator(transaction.atomic)
    def form_valid(self, form):
        resposta = super().form_valid(form)
        RegistroConta.objects.create(alvo_id=self.user.pk, acao="senha_recuperada", usuario=self.user,
                                     novos={"senha": "recuperada por e-mail"})
        return resposta


class RecuperacaoConcluida(auth_views.PasswordResetCompleteView):
    template_name = f"{PASTA}/concluido.html"
