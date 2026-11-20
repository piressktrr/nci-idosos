"""Inscrições de participantes em atividades (RF-ATV-06)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render

from ..forms import InscricaoForm
from ..integracoes.participantes import obter_provedor
from ..models import Atividade
from ..services import inscrever_participante


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_inscricao"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def inscricoes(request, atividade_id):
    atividade = get_object_or_404(Atividade, pk=atividade_id)
    if request.method == "POST" and not request.user.has_perm("atividades.add_inscricao"):
        raise PermissionDenied
    try:
        provedor = obter_provedor()
        participantes = provedor.listar()
        form = InscricaoForm(request.POST if request.method == "POST" else None, participantes=participantes)
        if request.method == "POST" and form.is_valid():
            try:
                inscrever_participante(usuario=request.user, atividade_id=atividade.pk, **form.cleaned_data)
            except ValidationError as erro:
                if hasattr(erro, "message_dict"):
                    for campo, erros in erro.message_dict.items():
                        form.add_error(campo if campo in form.fields else None, erros)
                else:
                    form.add_error(None, erro)
            else:
                messages.success(request, "Inscrição registrada com sucesso.")
                return redirect("atividades:inscricoes", atividade_id=atividade.pk)
    except ImproperlyConfigured:
        return render(request, "atividades/inscricoes.html", {"atividade": atividade, "indisponivel": True}, status=503)
    pagina = Paginator(atividade.inscricoes.filter(origem_participante=provedor.origem), 20).get_page(request.GET.get("page"))
    nomes = {item.referencia: item.nome for item in participantes}
    linhas = [{"inscricao": item, "nome": nomes.get(item.participante_referencia, "Participante indisponível")} for item in pagina]
    return render(request, "atividades/inscricoes.html", {
        "atividade": atividade, "form": form, "pagina": pagina, "linhas": linhas, "demonstracao": provedor.demonstracao,
    })
