from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from django.utils import timezone

from .forms import AtividadeForm, AulaForm, HorarioAtividadeForm, InscricaoForm, ChamadaForm, MotivoFaltaForm, CorrecaoFrequenciaForm, FrequenciaMensalForm
from .integracoes.participantes import obter_provedor
from .models import Atividade, Aula, HorarioAtividade, MotivoFalta, Frequencia
from .services import (
    cadastrar_atividade, cadastrar_horario, alterar_horario, registrar_aula,
    cancelar_aula, registrar_aula_cancelada, inscrever_participante, obter_lista_chamada, registrar_frequencias, salvar_motivo_falta,
    consultar_frequencia, corrigir_frequencia, consultar_frequencia_mensal,
)


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_aula", "atividades.view_frequencia"), raise_exception=True)
@require_http_methods(["GET"])
def frequencia_mensal(request):
    dados = request.GET.copy()
    if "mes" not in dados:
        dados["mes"] = timezone.localdate().strftime("%Y-%m")
    form = FrequenciaMensalForm(dados)
    contexto = {"form": form}
    status = 200
    if form.is_valid():
        mes = form.cleaned_data["mes"]
        atividade = form.cleaned_data["atividade"]
        try:
            contexto.update(consultar_frequencia_mensal(usuario=request.user, ano=mes.year, mes=mes.month,
                atividade_id=atividade.pk if atividade else None))
            contexto["mes_consultado"] = mes
        except ImproperlyConfigured:
            form.add_error(None, "A integração de participantes está indisponível.")
            status = 503
    return render(request, "atividades/frequencia_mensal.html", contexto, status=status)


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


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao"), raise_exception=True)
@require_http_methods(["GET"])
def chamada(request, atividade_id, aula_id):
    return _chamada(request, atividade_id, aula_id)


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao", "atividades.view_frequencia", "atividades.add_frequencia"), raise_exception=True)
@require_http_methods(["POST"])
def lancar_frequencias(request, atividade_id, aula_id):
    return _chamada(request, atividade_id, aula_id)


def _chamada(request, atividade_id, aula_id):
    try:
        contexto = obter_lista_chamada(usuario=request.user, atividade_id=atividade_id, aula_id=aula_id)
        contexto["modo_correcao"] = (
            request.GET.get("correcao") == "1" and contexto["pode_ver_frequencia"]
            and request.user.has_perm("atividades.change_frequencia")
        )
        form = ChamadaForm(request.POST if request.method == "POST" else None, participantes=contexto["participantes"])
        if request.method == "POST" and form.is_valid():
            try:
                registrar_frequencias(usuario=request.user, atividade_id=atividade_id, aula_id=aula_id,
                                      registros=form.registros, justificativas=form.justificativas)
            except ValidationError as erro:
                form.add_error(None, erro)
            else:
                messages.success(request, "Frequência registrada com sucesso.")
                return redirect("atividades:chamada", atividade_id=atividade_id, aula_id=aula_id)
        for item in contexto["participantes"]:
            chave = f"registro_{item['inscricao_id']}"
            item["campo"] = form[chave] if chave in form.fields else None
            item["campo_motivo"] = form[f"motivo_{item['inscricao_id']}"] if chave in form.fields else None
            item["campo_observacao"] = form[f"observacao_{item['inscricao_id']}"] if chave in form.fields else None
        contexto["form"] = form
    except Aula.DoesNotExist as erro:
        raise Http404("Aula não encontrada.") from erro
    except ValidationError as erro:
        contexto = {"erro": " ".join(erro.messages), "atividade_id": atividade_id}
    except ImproperlyConfigured:
        return render(request, "atividades/chamada.html", {
            "erro": "Cadastro de participantes indisponível.", "atividade_id": atividade_id,
        }, status=503)
    return render(request, "atividades/chamada.html", contexto)


@login_required
@permission_required("atividades.view_motivofalta", raise_exception=True)
@require_http_methods(["GET", "POST"])
def motivos_falta(request, motivo_id=None):
    permissao = "atividades.change_motivofalta" if motivo_id is not None else "atividades.add_motivofalta"
    if (motivo_id is not None or request.method == "POST") and not request.user.has_perm(permissao):
        raise PermissionDenied
    motivo = get_object_or_404(MotivoFalta, pk=motivo_id) if motivo_id is not None else None
    form = MotivoFaltaForm(request.POST if request.method == "POST" else None, instance=motivo)
    if request.method == "POST" and form.is_valid():
        try:
            salvar_motivo_falta(usuario=request.user, motivo_id=motivo_id, **form.cleaned_data)
        except ValidationError as erro:
            form.add_error(None, erro)
        else:
            messages.success(request, "Motivo salvo com sucesso.")
            return redirect("atividades:motivos_falta")
    return render(request, "atividades/motivos_falta.html", {
        "form": form, "motivo": motivo, "motivos": MotivoFalta.objects.all(),
    })


@login_required
@permission_required(("atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao", "atividades.view_frequencia"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def detalhe_frequencia(request, atividade_id, aula_id, frequencia_id):
    try:
        contexto = consultar_frequencia(usuario=request.user, atividade_id=atividade_id, aula_id=aula_id, frequencia_id=frequencia_id)
        if request.method == "POST" and not contexto["pode_corrigir"]:
            raise PermissionDenied
        frequencia = contexto["frequencia"]
        form = CorrecaoFrequenciaForm(request.POST if request.method == "POST" else None, frequencia=frequencia)
        if request.method == "POST" and form.is_valid():
            try:
                resultado = corrigir_frequencia(usuario=request.user, atividade_id=atividade_id, aula_id=aula_id,
                                               frequencia_id=frequencia_id, **form.cleaned_data)
            except ValidationError as erro:
                form.add_error(None, erro)
                frequencia.refresh_from_db()
            else:
                messages.success(request, "Correção registrada com sucesso." if resultado.versao != frequencia.versao else "Nenhuma alteração nos dados.")
                return redirect("atividades:detalhe_frequencia", atividade_id=atividade_id, aula_id=aula_id, frequencia_id=frequencia_id)
        contexto.update({"form": form, "inicial": getattr(frequencia, "registro_lancamento", None),
                         "correcoes": frequencia.correcoes.select_related("usuario")})
    except Frequencia.DoesNotExist as erro:
        raise Http404("Frequência não encontrada.") from erro
    except ImproperlyConfigured:
        return render(request, "atividades/chamada.html", {"erro": "Cadastro de participantes indisponível.", "atividade_id": atividade_id}, status=503)
    return render(request, "atividades/detalhe_frequencia.html", contexto)
