"""Formulários da gestão de colaboradores. Validam só a tela; as regras ficam nos serviços."""

from django import forms
from django.contrib.auth import get_user_model

from .services import NOMES_PERFIS

Usuario = get_user_model()
ESCOLHAS_PERFIL = [("", "Selecione"), *((nome, nome) for nome in NOMES_PERFIS)]
AJUDA_PERFIL = "Equipe: usuário comum. Administrador: também cadastra e administra as contas de acesso."
AJUDA_SENHA = "Pelo menos 10 caracteres, sem ser só números, comum demais ou parecida com os dados da conta."


def aplicar_bootstrap(form):
    """Classes do Bootstrap nos widgets (mesmo padrão dos formulários de participantes)."""
    for campo in form.fields.values():
        classe = "form-select" if isinstance(campo.widget, forms.Select) else "form-control"
        campo.widget.attrs.setdefault("class", classe)


def _tamanho(campo):
    return Usuario._meta.get_field(campo).max_length


def _campo_senha(rotulo, ajuda=""):
    return forms.CharField(label=rotulo, strip=False, max_length=128, help_text=ajuda,
                           widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))


class ColaboradorForm(forms.Form):
    """Edição: nome, sobrenome, e-mail e perfil. Sem o campo perfil na conta do próprio administrador."""

    first_name = forms.CharField(label="Nome", max_length=_tamanho("first_name"))
    last_name = forms.CharField(label="Sobrenome", max_length=_tamanho("last_name"), required=False)
    email = forms.EmailField(label="E-mail", max_length=_tamanho("email"), required=False)
    perfil = forms.ChoiceField(label="Perfil", choices=ESCOLHAS_PERFIL, help_text=AJUDA_PERFIL)

    def __init__(self, *args, proprio=False, **kwargs):
        super().__init__(*args, **kwargs)
        if proprio:
            del self.fields["perfil"]
        aplicar_bootstrap(self)


class _ConfirmacaoSenhaMixin:
    def clean(self):
        dados = super().clean()
        senha, confirmacao = dados.get("senha"), dados.get("confirmacao_senha")
        if senha and confirmacao and senha != confirmacao:
            self.add_error("confirmacao_senha", "As senhas não conferem.")
        return dados


class NovoColaboradorForm(_ConfirmacaoSenhaMixin, ColaboradorForm):
    """Cadastro com usuário e senha inicial; a força da senha é conferida pelo serviço (AUTH_PASSWORD_VALIDATORS)."""

    field_order = ("username", "first_name", "last_name", "email", "perfil", "senha", "confirmacao_senha")

    username = forms.CharField(
        label="Usuário", max_length=_tamanho("username"),
        help_text="Usado para entrar no sistema. Letras, números e @ . + - _ (sem espaços).",
        widget=forms.TextInput(attrs={"autocomplete": "off", "autocapitalize": "none"}))
    senha = _campo_senha("Senha inicial", AJUDA_SENHA)
    confirmacao_senha = _campo_senha("Confirmação da senha")


class SenhaForm(_ConfirmacaoSenhaMixin, forms.Form):
    senha = _campo_senha("Nova senha", AJUDA_SENHA)
    confirmacao_senha = _campo_senha("Confirmação da nova senha")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_bootstrap(self)
