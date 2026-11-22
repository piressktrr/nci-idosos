"""Cadastro e listagem de atividades (RF-ATV-01, RF-ATV-13)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import redirect, render
from django.utils import timezone

from ..classificacao import com_categoria_vigente
from ..forms import AtividadeForm, FiltroCategoriaForm, SituacaoAtividadeForm
from ..models import Atividade
from ..services import cadastrar_atividade
from core.perfis import e_administrador
from core.decorators import administrador_required
from ..situacao import alterar_situacao_atividade
from django.shortcuts import get_object_or_404


@login_required
@permission_required("atividades.view_atividade", raise_exception=True)
@require_http_methods(["GET", "POST"])
def lista(request):
    form = AtividadeForm(request.POST if request.method == "POST" else None)
    if request.method == "POST":
        # Autoriza mesmo um POST inválido, antes de processar seus campos.
        if not request.user.has_perm("atividades.add_atividade"):
            raise PermissionDenied
        if form.is_valid():
            try:
                cadastrar_atividade(usuario=request.user, **form.cleaned_data)
            except ValidationError as erro:
                if hasattr(erro, "message_dict"):
                    for campo, erros in erro.message_dict.items():
                        form.add_error(campo if campo in form.fields else None, erros)
                else:
                    form.add_error(None, erro)
            else:
                messages.success(request, "Atividade cadastrada com sucesso.")
                return redirect("atividades:lista")
    atividades = com_categoria_vigente(Atividade.objects.order_by("nome", "pk"), timezone.localdate())
    filtro_categoria = FiltroCategoriaForm(request.GET)
    if filtro_categoria.is_valid():
        categoria = filtro_categoria.cleaned_data["categoria"]
        if categoria == "sem_categoria":
            atividades = atividades.filter(categoria_atual_id__isnull=True)
        elif categoria:
            atividades = atividades.filter(categoria_atual_id=int(categoria))
    else:
        atividades = atividades.none()
    pagina = Paginator(atividades, 20).get_page(request.GET.get("page"))
    return render(request, "atividades/lista.html", {"form": form, "pagina": pagina, "filtro_categoria": filtro_categoria, "administrador": e_administrador(request.user)})


@administrador_required
@require_http_methods(["GET", "POST"])
def situacao(request, atividade_id):
    atividade = get_object_or_404(Atividade, pk=atividade_id)
    form = SituacaoAtividadeForm(request.POST if request.method == "POST" else None,
                             initial={"ativo": "0" if atividade.ativa else "1"})
    if request.method == "POST" and form.is_valid():
        try:
            alterar_situacao_atividade(usuario=request.user, atividade_id=atividade.pk, ativa=form.cleaned_data["ativo"])
        except ValidationError as erro:
            form.add_error(None, erro.messages)
        else:
            messages.success(request, "Situação da atividade atualizada. Histórico preservado.")
            return redirect("atividades:lista")
    return render(request, "atividades/situacao.html", {"form": form, "atividade": atividade})
