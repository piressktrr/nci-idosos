"""Lista de espera das atividades (RF-ATV-14)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from ..espera import adicionar_espera, autorizar, retirar_espera
from ..forms import InscricaoForm, VagaForm
from ..integracoes.participantes import obter_provedor
from ..models import Atividade, EsperaAtividade
from ..services import inscrever_participante


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_esperaatividade"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def lista_espera(request, atividade_id):
    atividade = get_object_or_404(Atividade, pk=atividade_id)
    if request.method == "POST":
        autorizar(request.user, "atividades.add_esperaatividade")
    try:
        provedor = obter_provedor()
        participantes = provedor.listar()
        form = InscricaoForm(request.POST if request.method == "POST" else None, participantes=participantes)
        if request.method == "POST" and form.is_valid():
            try:
                adicionar_espera(usuario=request.user, atividade_id=atividade_id, **form.cleaned_data)
            except ValidationError as erro:
                form.add_error(None, erro.messages)
            else:
                messages.success(request, "Participante adicionado à lista de espera.")
                return redirect("atividades:lista_espera", atividade_id=atividade_id)
    except ImproperlyConfigured:
        return render(request, "atividades/lista_espera.html", {"atividade": atividade, "indisponivel": True}, status=503)
    pagina = Paginator(atividade.lista_espera.filter(origem_participante=provedor.origem), 20).get_page(request.GET.get("page"))
    nomes = {item.referencia: item.nome for item in participantes}
    linhas = [{"espera": item, "nome": nomes.get(item.participante_referencia, "Participante indisponível")} for item in pagina]
    primeiro = atividade.lista_espera.filter(origem_participante=provedor.origem, situacao="aguardando").first()
    return render(request, "atividades/lista_espera.html", {"atividade": atividade, "form": form,
        "pagina": pagina, "linhas": linhas, "primeiro": primeiro, "demonstracao": provedor.demonstracao})


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_esperaatividade", "atividades.change_esperaatividade"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def atender_espera(request, atividade_id, espera_id, retirar=False):
    autorizar(request.user, "atividades.change_esperaatividade")
    if not retirar:
        autorizar(request.user, "atividades.add_inscricao")
    try:
        provedor = obter_provedor()
        espera = get_object_or_404(EsperaAtividade.objects.select_related("atividade"), pk=espera_id,
            atividade_id=atividade_id, origem_participante=provedor.origem)
        participante = provedor.obter(espera.participante_referencia)
        form = VagaForm(request.POST if request.method == "POST" else None)
        if request.method == "POST" and (retirar or form.is_valid()):
            try:
                if retirar:
                    retirar_espera(usuario=request.user, atividade_id=atividade_id, espera_id=espera_id)
                else:
                    inscrever_participante(usuario=request.user, atividade_id=atividade_id,
                        participante_referencia=espera.participante_referencia, espera_id=espera_id,
                        vaga_confirmada=form.cleaned_data["vaga_confirmada"])
            except ValidationError as erro:
                form.add_error(None, erro.messages)
            else:
                messages.success(request, "Retirada registrada." if retirar else "Participante inscrito pela lista de espera.")
                return redirect("atividades:lista_espera", atividade_id=atividade_id)
    except ImproperlyConfigured:
        return render(request, "atividades/lista_espera.html", {"atividade": get_object_or_404(Atividade, pk=atividade_id), "indisponivel": True}, status=503)
    return render(request, "atividades/atender_espera.html", {"espera": espera, "form": form,
        "nome": participante.nome if participante else "Participante indisponível", "retirar": retirar})
