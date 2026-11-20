"""RF-USR-05 (NCI 20/11/2026): "esqueci minha senha" por e-mail, com as telas e o token do próprio Django.

O link chega só ao e-mail cadastrado na conta, vale por PASSWORD_RESET_TIMEOUT e só funciona uma vez. Contas
inativas ou sem senha utilizável não recebem e-mail (regra do PasswordResetForm). A tela de pedido responde
igual exista ou não a conta, para não revelar quais e-mails estão cadastrados. A nova senha passa pelos
AUTH_PASSWORD_VALIDATORS e a redefinição é auditada em RegistroConta, sem a senha nem o hash.
"""

from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

from .forms import aplicar_bootstrap
from .models import RegistroConta

PASTA = "usuarios/recuperacao"


class PedirRecuperacao(auth_views.PasswordResetView):
    template_name = f"{PASTA}/pedido.html"
    email_template_name = f"{PASTA}/email.txt"
    subject_template_name = f"{PASTA}/assunto.txt"
    success_url = reverse_lazy("recuperacao_enviada")

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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["new_password1"].label = "Nova senha"
        form.fields["new_password2"].label = "Confirme a nova senha"
        aplicar_bootstrap(form)
        return form

    def form_valid(self, form):
        resposta = super().form_valid(form)
        RegistroConta.objects.create(alvo_id=self.user.pk, acao="senha_recuperada", usuario=self.user,
                                     novos={"senha": "recuperada por e-mail"})
        return resposta


class RecuperacaoConcluida(auth_views.PasswordResetCompleteView):
    template_name = f"{PASTA}/concluido.html"
