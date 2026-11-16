"""Aulas realizadas, extras, remarcadas e canceladas (RF-ATV-03 a 05)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..forms import AulaForm
from ..models import Atividade, Aula
from ..services import cancelar_aula, registrar_aula, registrar_aula_cancelada


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_aula"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def aulas(request, atividade_id):
    return _aulas(request, atividade_id)


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_aula", "atividades.add_aula", "atividades.cancelar_aula"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def nova_aula_cancelada(request, atividade_id):
    return _aulas(request, atividade_id, modo_cancelamento=True)


def _aulas(request, atividade_id, modo_cancelamento=False):
    atividade = get_object_or_404(Atividade, pk=atividade_id)
    horarios = []
    if request.user.has_perm("atividades.add_aula") and request.user.has_perm("atividades.view_horarioatividade"):
        horarios = list(atividade.horarios.values("pk", "dia_semana", "inicio", "fim"))
    form = AulaForm(request.POST if request.method == "POST" else None, horarios=horarios)
    if modo_cancelamento:
        form.fields["inicio"].label = "Início previsto"
        form.fields["fim"].label = "Término previsto"
    if request.method == "POST":
        if not request.user.has_perm("atividades.add_aula"):
            raise PermissionDenied
        if form.is_valid():
            try:
                servico = registrar_aula_cancelada if modo_cancelamento else registrar_aula
                servico(usuario=request.user, atividade_id=atividade.pk, **form.cleaned_data)
            except ValidationError as erro:
                if hasattr(erro, "message_dict"):
                    for campo, erros in erro.message_dict.items():
                        form.add_error(campo if campo in form.fields else None, erros)
                else:
                    form.add_error(None, erro)
            else:
                messages.success(request, "Aula cancelada registrada com sucesso." if modo_cancelamento else "Aula realizada registrada com sucesso.")
                return redirect("atividades:aulas", atividade_id=atividade.pk)
    pagina = Paginator(atividade.aulas.com_categoria_fmr(), 20).get_page(request.GET.get("page"))
    return render(request, "atividades/aulas.html", {
        "atividade": atividade, "form": form, "pagina": pagina,
        "sugestoes": {"horarios": horarios, "fuso": timezone.get_current_timezone_name()},
        "modo_cancelamento": modo_cancelamento,
        "total_realizadas": atividade.aulas.realizadas().count(),
        "total_canceladas": atividade.aulas.filter(situacao=Aula.Situacao.CANCELADA).count(),
    })


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_aula", "atividades.cancelar_aula"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def confirmar_cancelamento(request, atividade_id, aula_id):
    aula = get_object_or_404(Aula.objects.select_related("atividade"), pk=aula_id, atividade_id=atividade_id)
    erro = None
    if request.method == "POST":
        try:
            cancelar_aula(usuario=request.user, atividade_id=atividade_id, aula_id=aula_id)
        except ValidationError as exception:
            erro = " ".join(exception.messages)
        else:
            messages.success(request, "Aula cancelada com sucesso.")
            return redirect("atividades:aulas", atividade_id=atividade_id)
    return render(request, "atividades/cancelar_aula.html", {"aula": aula, "erro": erro})
