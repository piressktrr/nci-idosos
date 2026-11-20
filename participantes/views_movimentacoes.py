from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from core.decorators import administrador_required
from .models import Participante, MotivoDesligamento
from .movimentacoes import movimentar_participante, salvar_motivo


class MovimentoForm(forms.Form):
    tipo = forms.ChoiceField(label="Movimentação", choices=(("desligamento", "Desligamento"), ("reativacao", "Reativação"), ("afastamento", "Afastamento"), ("retorno", "Retorno de afastamento")))
    data = forms.DateField(label="Data de vigência", initial=timezone.localdate, widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))
    motivo_id = forms.ModelChoiceField(label="Motivo (obrigatório no desligamento)", required=False,
                                      queryset=MotivoDesligamento.objects.filter(ativo=True))


@login_required
@permission_required(("participantes.view_participante", "participantes.change_participante"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def movimentar(request, participante_id):
    pessoa = get_object_or_404(Participante, pk=participante_id)
    form = MovimentoForm(request.POST if request.method == "POST" else None,
        initial={"tipo": {"desligado": "reativacao", "afastado": "retorno"}.get(pessoa.status, "desligamento")})
    if request.method == "POST" and form.is_valid():
        dados = form.cleaned_data.copy()
        motivo = dados.pop("motivo_id")
        try:
            movimentar_participante(usuario=request.user, participante_id=pessoa.pk,
                motivo_id=motivo.pk if motivo else None, **dados)
        except ValidationError as erro:
            form.add_error(None, erro.messages)
        else:
            messages.success(request, "Movimentação registrada. Cadastro e histórico preservados.")
            return redirect("participantes:detalhe", participante_id=pessoa.pk)
    return render(request, "participantes/movimentar.html", {"form": form, "participante": pessoa,
        "movimentos": pessoa.movimentacoes.order_by("-data", "-pk"),
        "sem_motivos": not MotivoDesligamento.objects.filter(ativo=True).exists()})


class MotivoForm(forms.ModelForm):
    class Meta:
        model = MotivoDesligamento
        fields = ("descricao", "ativo")


@administrador_required
@require_http_methods(["GET", "POST"])
def motivos(request, motivo_id=None):
    motivo = get_object_or_404(MotivoDesligamento, pk=motivo_id) if motivo_id is not None else None
    form = MotivoForm(request.POST if request.method == "POST" else None, instance=motivo)
    if request.method == "POST" and form.is_valid():
        try:
            salvar_motivo(usuario=request.user, motivo_id=motivo_id, **form.cleaned_data)
        except ValidationError as erro:
            form.add_error(None, erro.messages)
        else:
            return redirect("participantes:motivos_desligamento")
    return render(request, "participantes/motivos_desligamento.html", {"form": form, "motivos": MotivoDesligamento.objects.all()})
