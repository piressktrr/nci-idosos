"""Categorias FMR e classificação de atividades (RF-ATV-13)."""
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse

from ..classificacao import autorizar, classificar_atividade, com_categoria_vigente, salvar_categoria
from ..forms import CategoriaForm, ClassificacaoForm
from ..models import Atividade, CategoriaFMR


class AtividadeCategoriaForm(forms.Form):
    atividade = forms.ModelChoiceField(label="Atividade", queryset=Atividade.objects.all(), empty_label="Escolha a atividade")


@login_required
@require_http_methods(["GET", "POST"])
def categorias(request, categoria_id=None):
    autorizar(request.user, catalogo=True)
    categoria = get_object_or_404(CategoriaFMR, pk=categoria_id) if categoria_id is not None else None
    atribuindo = request.method == "POST" and request.POST.get("acao") == "classificar"
    form = CategoriaForm(request.POST if request.method == "POST" and not atribuindo else None, instance=categoria)
    selecao = AtividadeCategoriaForm(request.POST if atribuindo else request.GET or None)
    atividade = None
    if selecao.is_bound and selecao.is_valid():
        atividade = com_categoria_vigente(Atividade.objects.all(), timezone.localdate()).get(pk=selecao.cleaned_data["atividade"].pk)
    form_classificacao = ClassificacaoForm(request.POST if atribuindo else None,
        initial={"categoria": atividade.categoria_atual_id} if atividade else None)
    if atribuindo and selecao.is_valid() and form_classificacao.is_valid():
        try:
            classificar_atividade(usuario=request.user, atividade_id=atividade.pk,
                categoria_id=form_classificacao.cleaned_data["categoria"].pk, inicio=form_classificacao.cleaned_data["inicio"])
        except ValidationError as erro:
            form_classificacao.add_error(None, erro.messages)
        else:
            messages.success(request, "Categoria da atividade salva com vigência.")
            return redirect(reverse("atividades:categorias_fmr") + f"?atividade={atividade.pk}#categoria-atividade")
    if request.method == "POST" and not atribuindo and form.is_valid():
        try:
            salvar_categoria(usuario=request.user, categoria_id=categoria_id, **form.cleaned_data)
        except ValidationError as erro:
            form.add_error(None, erro)
        else:
            messages.success(request, "Categoria salva.")
            return redirect("atividades:categorias_fmr")
    return render(request, "atividades/categorias_fmr.html", {
        "form": form, "categoria": categoria, "categorias": CategoriaFMR.objects.all(),
        "selecao": selecao, "atividade": atividade, "form_classificacao": form_classificacao,
        "classificacoes": atividade.classificacoes.all() if atividade else []})


@login_required
@permission_required("atividades.view_atividade", raise_exception=True)
@require_http_methods(["GET", "POST"])
def classificacao(request, atividade_id):
    atividade = get_object_or_404(com_categoria_vigente(Atividade.objects.all(), timezone.localdate()), pk=atividade_id)
    if request.method == "POST":
        autorizar(request.user)
    form = ClassificacaoForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            classificar_atividade(usuario=request.user, atividade_id=atividade_id,
                categoria_id=form.cleaned_data["categoria"].pk, inicio=form.cleaned_data["inicio"])
        except ValidationError as erro:
            form.add_error(None, erro)
        else:
            messages.success(request, "Classificação salva com vigência.")
            return redirect("atividades:classificacao_fmr", atividade_id=atividade_id)
    return render(request, "atividades/classificacao_fmr.html", {
        "atividade": atividade, "form": form, "classificacoes": atividade.classificacoes.all()})
