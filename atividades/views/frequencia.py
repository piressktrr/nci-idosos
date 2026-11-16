"""Chamada, frequência, justificativas e consultas (RF-ATV-07 a 12)."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_http_methods
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from ..forms import ChamadaForm, CorrecaoFrequenciaForm, FrequenciaMensalForm, MotivoFaltaForm
from ..models import Aula, Frequencia, Inscricao, MotivoFalta
from ..services import (
    consultar_frequencia, consultar_frequencia_mensal, consultar_historico_participante,
    corrigir_frequencia, obter_lista_chamada, registrar_frequencias, salvar_motivo_falta,
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
@permission_required(("atividades.view_atividade", "atividades.view_aula", "atividades.view_inscricao", "atividades.view_frequencia"), raise_exception=True)
@require_http_methods(["GET"])
def historico_participante(request, atividade_id, inscricao_id):
    try:
        contexto = consultar_historico_participante(usuario=request.user, atividade_id=atividade_id, inscricao_id=inscricao_id)
    except Inscricao.DoesNotExist:
        raise Http404
    except ImproperlyConfigured:
        return render(request, "atividades/historico_participante.html", {"indisponivel": True}, status=503)
    contexto["pagina"] = Paginator(contexto.pop("frequencias"), 20).get_page(request.GET.get("page"))
    return render(request, "atividades/historico_participante.html", contexto)


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
