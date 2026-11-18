from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from ..chamada_unificada import PERMISSOES, preparar_chamada, salvar_chamada
from ..forms import AulaForm, ChamadaForm
from ..models import Atividade


class EscolherAtividadeForm(forms.Form):
    atividade = forms.ModelChoiceField(label="Atividade", queryset=Atividade.objects.all(), empty_label="Escolha a atividade")


@login_required
@permission_required(PERMISSOES, raise_exception=True)
@require_http_methods(["GET", "POST"])
def nova_chamada(request):
    selecao = EscolherAtividadeForm(request.POST if request.method == "POST" else request.GET or None)
    atividade, participantes, demonstracao = None, [], False
    horarios = []
    indisponivel = False
    if selecao.is_bound and selecao.is_valid():
        try:
            atividade, participantes, demonstracao = preparar_chamada(
                usuario=request.user, atividade_id=selecao.cleaned_data["atividade"].pk)
        except Atividade.DoesNotExist as erro:
            raise Http404 from erro
        except ImproperlyConfigured:
            indisponivel = True
        if atividade and request.user.has_perm("atividades.view_horarioatividade"):
            horarios = list(atividade.horarios.values("pk", "dia_semana", "inicio", "fim"))
    dados = request.POST if request.method == "POST" else None
    form_aula = AulaForm(dados, horarios=horarios)
    form = ChamadaForm(dados, participantes=participantes)
    if request.method == "POST":
        validos = [selecao.is_valid(), form_aula.is_valid(), form.is_valid()]
        if all(validos) and atividade and not indisponivel:
            try:
                aula = salvar_chamada(usuario=request.user, atividade_id=atividade.pk,
                    dados_aula=form_aula.cleaned_data, registros=form.registros, justificativas=form.justificativas)
            except ValidationError as erro:
                form.add_error(None, erro.messages)
            else:
                messages.success(request, "Chamada salva: aula e frequências registradas.")
                return redirect("atividades:chamada", atividade_id=atividade.pk, aula_id=aula.pk)
    for p in participantes:
        chave = f"registro_{p['inscricao_id']}"
        p["campo"] = form[chave] if chave in form.fields else None
        p["campo_motivo"] = form[f"motivo_{p['inscricao_id']}"] if chave in form.fields else None
        p["campo_observacao"] = form[f"observacao_{p['inscricao_id']}"] if chave in form.fields else None
    return render(request, "atividades/nova_chamada.html", {"selecao": selecao, "atividade": atividade,
        "form_aula": form_aula, "form": form, "participantes": participantes,
        "demonstracao": demonstracao, "indisponivel": indisponivel,
        "pode_ver_frequencia": True, "pode_registrar_frequencia": True,
        "sugestoes": {"horarios": horarios, "fuso": timezone.get_current_timezone_name()}}, status=503 if indisponivel else 200)
