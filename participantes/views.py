from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .auditoria import diferencas, historico
from .forms import ParticipanteForm
from .models import Participante
from .services import cadastrar_participante, corrigir_participante


def _aplicar_erro(form, erro):
    if hasattr(erro, "error_dict"):
        for campo, erros in erro.message_dict.items():
            form.add_error(campo if campo in form.fields else None, erros)
    else:
        form.add_error(None, erro)


def _formulario(request, participante=None):
    """Cadastro e correção usam o mesmo fluxo, inclusive o alerta de duplicidade (RN-PAR-01)."""
    form = ParticipanteForm(request.POST or None, instance=participante,
                            mostrar_confirmacao=bool(request.POST.get("confirmar_duplicidade_exibida")))
    if request.method == "POST" and form.is_valid():
        dados, confirmar = form.dados_servico()
        try:
            if participante is None:
                participante = cadastrar_participante(usuario=request.user, confirmar_duplicidade=confirmar, **dados)
                messages.success(request, "Participante cadastrado com sucesso.")
            else:
                corrigir_participante(usuario=request.user, participante_id=participante.pk,
                                      confirmar_duplicidade=confirmar, **dados)
                messages.success(request, "Cadastro atualizado.")
        except ValidationError as erro:
            if getattr(erro, "code", None) == "possivel_duplicado":
                form = ParticipanteForm(request.POST, instance=participante, mostrar_confirmacao=True)
                form.is_valid()
            _aplicar_erro(form, erro)
        else:
            return redirect("participantes:detalhe", participante_id=participante.pk)
    return render(request, "participantes/formulario.html", {
        "form": form, "participante": participante})


@login_required
@permission_required("participantes.view_participante", raise_exception=True)
@require_http_methods(["GET"])
def lista(request):
    pagina = Paginator(Participante.objects.all(), 20).get_page(request.GET.get("page"))
    return render(request, "participantes/lista.html", {"pagina": pagina})


@login_required
@permission_required(("participantes.view_participante", "participantes.add_participante"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def cadastrar(request):
    return _formulario(request)


@login_required
@permission_required("participantes.view_participante", raise_exception=True)
@require_http_methods(["GET"])
def detalhe(request, participante_id):
    participante = get_object_or_404(Participante, pk=participante_id)
    registros = None
    if request.user.has_perm("participantes.change_participante"):
        registros = [{"registro": item, "mudancas": diferencas(item)} for item in historico(participante)]
    return render(request, "participantes/detalhe.html", {"participante": participante, "registros": registros})


@login_required
@permission_required(("participantes.view_participante", "participantes.change_participante"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def corrigir(request, participante_id):
    return _formulario(request, get_object_or_404(Participante, pk=participante_id))
