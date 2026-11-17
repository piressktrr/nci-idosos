"""Telas de gestão de colaboradores (RF-USR-03). Só administradores (RN-USR-01); a gravação fica nos serviços."""

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .consultas import ACOES, diferencas, historico, pesquisar_colaboradores
from .decorators import administrador_required
from .forms import ColaboradorForm, NovoColaboradorForm, SenhaForm
from .services import cadastrar_colaborador, corrigir_colaborador, definir_senha, perfil_de


def _aplicar_erro(form, erro):
    if hasattr(erro, "error_dict"):
        for campo, erros in erro.message_dict.items():
            form.add_error(campo if campo in form.fields else None, erros)
    else:
        form.add_error(None, erro)


@administrador_required
@require_http_methods(["GET"])
def lista(request):
    termo = request.GET.get("q", "").strip()[:150]
    contas = pesquisar_colaboradores(termo, usuario=request.user)
    pagina = Paginator(contas, 20).get_page(request.GET.get("page"))
    linhas = [{"conta": conta, "perfil": perfil_de(conta)} for conta in pagina]
    return render(request, "usuarios/lista.html", {"pagina": pagina, "linhas": linhas, "termo": termo})


@administrador_required
@require_http_methods(["GET", "POST"])
def cadastrar(request):
    form = NovoColaboradorForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        dados = {campo: form.cleaned_data[campo] for campo in
                 ("username", "first_name", "last_name", "email", "perfil", "senha")}
        try:
            conta = cadastrar_colaborador(usuario=request.user, **dados)
        except ValidationError as erro:
            _aplicar_erro(form, erro)
        else:
            messages.success(request, f"Colaborador {conta.get_username()} cadastrado com sucesso.")
            return redirect("usuarios:lista")
    return render(request, "usuarios/formulario.html", {"form": form, "conta": None})


@administrador_required
@require_http_methods(["GET", "POST"])
def editar(request, conta_id):
    conta = get_object_or_404(get_user_model(), pk=conta_id)
    proprio = conta.pk == request.user.pk
    perfil = perfil_de(conta)
    inicial = {"first_name": conta.first_name, "last_name": conta.last_name, "email": conta.email, "perfil": perfil}
    form = ColaboradorForm(request.POST or None, initial=inicial, proprio=proprio)
    if request.method == "POST" and form.is_valid():
        dados = {campo: form.cleaned_data[campo] for campo in ("first_name", "last_name", "email")}
        try:
            corrigir_colaborador(usuario=request.user, conta_id=conta.pk,
                                 perfil=perfil if proprio else form.cleaned_data["perfil"], **dados)
        except ValidationError as erro:
            _aplicar_erro(form, erro)
        else:
            messages.success(request, "Dados do colaborador atualizados.")
            return redirect("usuarios:editar", conta_id=conta.pk)
    registros = [{"registro": item, "acao": ACOES.get(item.acao, item.acao), "mudancas": diferencas(item)}
                 for item in historico(conta, usuario=request.user)]
    return render(request, "usuarios/formulario.html", {
        "form": form, "conta": conta, "perfil": perfil, "proprio": proprio, "registros": registros})


@administrador_required
@require_http_methods(["GET", "POST"])
def senha(request, conta_id):
    conta = get_object_or_404(get_user_model(), pk=conta_id)
    form = SenhaForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            conta = definir_senha(usuario=request.user, conta_id=conta.pk, senha=form.cleaned_data["senha"])
        except ValidationError as erro:
            _aplicar_erro(form, erro)
        else:
            if conta.pk == request.user.pk:
                update_session_auth_hash(request, conta)  # mantém a sessão de quem trocou a própria senha
            messages.success(request, f"Nova senha definida para {conta.get_username()}.")
            return redirect("usuarios:editar", conta_id=conta.pk)
    return render(request, "usuarios/senha.html", {"form": form, "conta": conta})
