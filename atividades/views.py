from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from .forms import AtividadeForm, HorarioAtividadeForm
from .models import Atividade, HorarioAtividade
from .services import cadastrar_atividade, cadastrar_horario, alterar_horario


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
    pagina = Paginator(Atividade.objects.order_by("nome", "pk"), 20).get_page(request.GET.get("page"))
    return render(request, "atividades/lista.html", {"form": form, "pagina": pagina})


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_horarioatividade"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def grade(request, atividade_id):
    return _grade(request, atividade_id)


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_horarioatividade", "atividades.change_horarioatividade"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def editar_horario(request, atividade_id, horario_id):
    return _grade(request, atividade_id, horario_id)


def _grade(request, atividade_id, horario_id=None):
    atividade = get_object_or_404(Atividade, pk=atividade_id)
    horario = get_object_or_404(HorarioAtividade, pk=horario_id, atividade=atividade) if horario_id is not None else None
    form = HorarioAtividadeForm(request.POST if request.method == "POST" else None, instance=horario)
    if request.method == "POST":
        permissao = "atividades.change_horarioatividade" if horario is not None else "atividades.add_horarioatividade"
        if not request.user.has_perm(permissao):
            raise PermissionDenied
        if form.is_valid():
            argumentos = {"usuario": request.user, "atividade_id": atividade.pk, **form.cleaned_data}
            try:
                if horario is None:
                    cadastrar_horario(**argumentos)
                else:
                    alterar_horario(horario_id=horario.pk, **argumentos)
            except ValidationError as erro:
                if hasattr(erro, "message_dict"):
                    for campo, erros in erro.message_dict.items():
                        form.add_error(campo if campo in form.fields else None, erros)
                else:
                    form.add_error(None, erro)
            else:
                messages.success(request, "Horário alterado com sucesso." if horario else "Horário cadastrado com sucesso.")
                return redirect("atividades:grade", atividade_id=atividade.pk)
    return render(request, "atividades/grade.html", {
        "atividade": atividade, "horario": horario, "form": form, "horarios": atividade.horarios.all(),
    })
