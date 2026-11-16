"""Categorias FMR e classificação de atividades (RF-ATV-13)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..classificacao import autorizar, classificar_atividade, com_categoria_vigente, salvar_categoria
from ..forms import CategoriaForm, ClassificacaoForm
from ..models import Atividade, CategoriaFMR


@login_required
@require_http_methods(["GET", "POST"])
def categorias(request, categoria_id=None):
    autorizar(request.user, catalogo=True)
    categoria = get_object_or_404(CategoriaFMR, pk=categoria_id) if categoria_id is not None else None
    form = CategoriaForm(request.POST if request.method == "POST" else None, instance=categoria)
    if request.method == "POST" and form.is_valid():
        try:
            salvar_categoria(usuario=request.user, categoria_id=categoria_id, **form.cleaned_data)
        except ValidationError as erro:
            form.add_error(None, erro)
        else:
            messages.success(request, "Categoria salva.")
            return redirect("atividades:categorias_fmr")
    return render(request, "atividades/categorias_fmr.html", {
        "form": form, "categoria": categoria, "categorias": CategoriaFMR.objects.all()})


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
