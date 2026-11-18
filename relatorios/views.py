from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .forms import MesReferenciaForm
from .permissoes import pode_consultar_fmr
from .services import consultar_periodo_fmr


@login_required
@require_GET
def fmr(request):
    if not pode_consultar_fmr(request.user):
        raise PermissionDenied
    dados = request.GET.copy()
    if "mes" not in dados:
        hoje = timezone.localdate()
        dados["mes"] = f"{hoje.year:04d}-{hoje.month:02d}"
    form = MesReferenciaForm(dados)
    periodo = None
    if form.is_valid():
        mes = form.cleaned_data["mes"]
        periodo = consultar_periodo_fmr(usuario=request.user, ano=mes.year, mes=mes.month)
    return render(request, "relatorios/fmr.html", {"form": form, "periodo": periodo})
