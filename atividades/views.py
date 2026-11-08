from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .forms import AtividadeForm, AulaForm, HorarioAtividadeForm, InscricaoForm
from .integracoes.participantes import obter_provedor
from .models import Atividade, Aula, HorarioAtividade
from .services import (
    cadastrar_atividade, cadastrar_horario, alterar_horario, registrar_aula,
    cancelar_aula, registrar_aula_cancelada, inscrever_participante,
)


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
    pagina = Paginator(atividade.aulas.all(), 20).get_page(request.GET.get("page"))
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
