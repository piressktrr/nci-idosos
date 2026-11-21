from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.module_loading import import_string
from django.views.decorators.http import require_http_methods

from .auditoria import diferencas, historico
from .exportacao import PERMISSAO_EXPORTAR, exportar_participantes_csv
from .forms import ParticipanteForm, SituacaoSocialForm
from .models import Participante, SituacaoSocial
from .provedor import ProvedorParticipantes
from .services import (cadastrar_participante, corrigir_participante, pesquisar_participantes,
                       registrar_situacao_social)


def _aplicar_erro(form, erro):
    if hasattr(erro, "error_dict"):
        for campo, erros in erro.message_dict.items():
            form.add_error(campo if campo in form.fields else None, erros)
    else:
        form.add_error(None, erro)


def _frequencias(usuario, participante):
    """RF-PAR-10: frequência em atividades, pela consulta configurada (sem importar o app de atividades).

    None quando não há consulta configurada ou o usuário não tem as permissões de atividades: o cartão não aparece.
    """
    caminho = getattr(settings, "NCI_CONSULTA_FREQUENCIA_PARTICIPANTE", "")
    if not caminho:
        return None
    consulta = import_string(caminho)
    try:
        # Atividades identifica a pessoa pelo par (origem, referência) do provedor de participantes.
        return consulta(usuario=usuario, origem=ProvedorParticipantes.origem, referencia=str(participante.pk))
    except PermissionDenied:
        return None


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
                                      perfil_vigente_desde=form.cleaned_data.get("perfil_vigente_desde"),
                                      origem_entrada=form.cleaned_data.get("origem_entrada") or None,
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
    termo = request.GET.get("q", "").strip()[:200]
    pagina = Paginator(pesquisar_participantes(termo), 20).get_page(request.GET.get("page"))
    return render(request, "participantes/lista.html", {"pagina": pagina, "termo": termo})


@login_required
@permission_required(PERMISSAO_EXPORTAR, raise_exception=True)
@require_http_methods(["POST"])
def exportar(request):
    """RNF-SEG-11: todos os participantes em CSV, como download; o serviço autoriza de novo e audita.

    Só por POST com CSRF: um link externo não consegue disparar uma exportação (e o registro de auditoria) no
    navegador de um administrador logado.
    """
    nome = f"participantes_{timezone.localdate():%Y-%m-%d}.csv"
    # Dados sensíveis: nada de cache no navegador ou em proxies.
    resposta = HttpResponse(content_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{nome}"', "Cache-Control": "no-store"})
    exportar_participantes_csv(usuario=request.user, destino=resposta)
    return resposta


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
        registros = [{"registro": item, "mudancas": diferencas(item)}
                     for item in historico(participante, usuario=request.user)]
    return render(request, "participantes/detalhe.html", {
        "participante": participante, "registros": registros, "data_entrada": participante.data_entrada,
        "frequencias": _frequencias(request.user, participante),
        "situacoes": participante.situacoes_sociais.all(),
        # RF-PAR-10: entradas, saídas e afastamentos visíveis a quem consulta o cadastro.
        "movimentacoes": participante.movimentacoes.select_related("usuario").order_by("-data", "-pk"),
        "situacao_atual": SituacaoSocial.vigente_em(participante, timezone.localdate())})


@login_required
@permission_required(("participantes.view_participante", "participantes.change_participante"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def corrigir(request, participante_id):
    return _formulario(request, get_object_or_404(Participante, pk=participante_id))


@login_required
@permission_required(("participantes.view_participante", "participantes.change_participante"), raise_exception=True)
@require_http_methods(["GET", "POST"])
def situacao_social(request, participante_id):
    """RF-PAR-04/05: nova vigência da situação social, ou correção de uma existente (mesma data)."""
    participante = get_object_or_404(Participante, pk=participante_id)
    atual = SituacaoSocial.vigente_em(participante, timezone.localdate())
    form = SituacaoSocialForm(request.POST or None, initial=SituacaoSocialForm.inicial_de(atual),
                              instance=SituacaoSocial(participante=participante))
    if request.method == "POST" and form.is_valid():
        try:
            registrar_situacao_social(usuario=request.user, participante_id=participante.pk, **form.dados_servico())
        except ValidationError as erro:
            _aplicar_erro(form, erro)
        else:
            messages.success(request, "Situação social registrada.")
            return redirect("participantes:detalhe", participante_id=participante.pk)
    return render(request, "participantes/situacao_social.html", {"form": form, "participante": participante})
