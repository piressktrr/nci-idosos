from django.contrib.auth.decorators import login_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from .forms import MesReferenciaForm
from .permissoes import pode_consultar_fmr
from .services import consultar_indicadores_fmr


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
    contexto = {"form": form, "periodo": None, "transcricao": dados.get("modo") == "transcricao"}
    status = 200
    if form.is_valid():
        mes = form.cleaned_data["mes"]
        try:
            contexto.update(consultar_indicadores_fmr(usuario=request.user, ano=mes.year, mes=mes.month))
        except ImproperlyConfigured:
            form.add_error(None, "A integração de participantes está indisponível ou a configuração do FMR é inválida. Tente consultar novamente mais tarde.")
            status = 503
    return render(request, "relatorios/fmr.html", contexto, status=status)
