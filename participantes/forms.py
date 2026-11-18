from django import forms
from django.utils import timezone

from .models import Participante, SituacaoSocial

SIM_NAO = ((True, "Sim"), (False, "Não"))


def _sim_nao(valor):
    return {"True": True, "False": False}.get(valor, valor)


def aplicar_bootstrap(form):
    """Classes do Bootstrap nos widgets, para os templates só desenharem o layout."""
    for campo in form.fields.values():
        widget = campo.widget
        if isinstance(widget, forms.RadioSelect):
            continue
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(widget, forms.Select):
            widget.attrs.setdefault("class", "form-select")
            # O Django 6 ainda não traduz "- Select an option -" para pt-br.
            if getattr(campo, "choices", None):
                campo.choices = [("", "Selecione") if valor == "" else (valor, rotulo)
                                 for valor, rotulo in campo.choices]
        else:
            widget.attrs.setdefault("class", "form-control")


class TelefoneField(forms.CharField):
    """Aceita o telefone com máscara; o campo do navegador limita a 20 caracteres digitados.

    Não normaliza nem valida o tamanho: o modelo tira a máscara e confere os dígitos (RF-PAR-02).
    """

    TAMANHO_DIGITADO = 20

    def __init__(self, *, max_length=None, **kwargs):
        # O max_length do modelo (10/11) vale para os dígitos, não para o texto com máscara.
        super().__init__(**kwargs)

    def widget_attrs(self, widget):
        return {**super().widget_attrs(widget), "maxlength": str(self.TAMANHO_DIGITADO)}


def _widget_telefone(exemplo):
    return forms.TextInput(attrs={"type": "tel", "inputmode": "numeric", "autocomplete": "off",
                                  "placeholder": exemplo, "data-mascara": "telefone"})


class ParticipanteForm(forms.ModelForm):
    confirmar_duplicidade = forms.BooleanField(
        label="Confirmo que é outra pessoa, com o mesmo nome e data de nascimento", required=False)
    ensino_medio_completo = forms.TypedChoiceField(
        label="Ensino médio completo?", choices=SIM_NAO, coerce=_sim_nao, widget=forms.RadioSelect)
    # Q5: o cadastro registra a data de entrada (Movimentacao); o serviço valida (não futura, não antes do nascimento).
    data_entrada = forms.DateField(label="Data de entrada",
                                   widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}))

    class Meta:
        model = Participante
        fields = ("nome_completo", "endereco", "identidade_genero", "origem_encaminhamento",
                  "observacao_encaminhamento", "telefone_residencial", "telefone_celular", "data_nascimento",
                  "raca_cor", "sexo", "ensino_medio_completo")
        # Sem status: desligamento, reativação e afastamento passam pelos serviços de movimentação.
        labels = {"telefone_residencial": "Telefone fixo", "raca_cor": "Raça/cor"}
        field_classes = {"telefone_celular": TelefoneField, "telefone_residencial": TelefoneField}
        widgets = {
            "data_nascimento": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "telefone_celular": _widget_telefone("(11) 91234-5678"),
            "telefone_residencial": _widget_telefone("(11) 3123-4567"),
            "observacao_encaminhamento": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {"telefone_celular": "Informe pelo menos um dos dois telefones do próprio participante."}

    def __init__(self, *args, mostrar_confirmacao=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.mostrar_confirmacao = mostrar_confirmacao
        entrada = self.instance.data_entrada if self.instance.pk else None
        self.fields["data_entrada"].initial = entrada or timezone.localdate()
        from .categorias import IDENTIDADES_GENERO_LEGADAS
        if self.instance.identidade_genero in IDENTIDADES_GENERO_LEGADAS:
            self.fields["identidade_genero"].help_text = (
                "O cadastro possui uma categoria anterior. Confirme a autodeclaração e selecione uma das opções do FMR."
            )
        if not mostrar_confirmacao:
            # Só existe depois do alerta de duplicidade; antes disso, nunca confirma.
            del self.fields["confirmar_duplicidade"]
        aplicar_bootstrap(self)

    def dados_servico(self):
        # Telefones podem ir com máscara: o full_clean do serviço os normaliza no modelo.
        dados = {campo: self.cleaned_data[campo] for campo in (*self._meta.fields, "data_entrada")}
        return dados, self.cleaned_data.get("confirmar_duplicidade") is True


class SituacaoSocialForm(forms.ModelForm):
    """RF-PAR-04: cada indicador é sim ou não; não marcado significa "não"."""

    INDICADORES = ("mora_sozinho", "tem_apoio", "possui_deficiencia", "recebe_bpc", "imigrante_refugiado")

    class Meta:
        model = SituacaoSocial
        fields = ("vigente_desde", "mora_sozinho", "tem_apoio", "possui_deficiencia", "recebe_bpc",
                  "imigrante_refugiado")
        widgets = {"vigente_desde": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}
        help_texts = {"vigente_desde": "A partir de quando esta situação vale. Para corrigir um registro, "
                                       "use a mesma data dele."}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aplicar_bootstrap(self)

    @classmethod
    def inicial_de(cls, situacao, hoje=None):
        """Valores iniciais de um novo registro: começa hoje e repete os indicadores da situação atual, se houver."""
        inicial = {"vigente_desde": hoje or timezone.localdate()}
        if situacao is not None:
            inicial.update({campo: getattr(situacao, campo) for campo in cls.INDICADORES})
        return inicial

    def validate_unique(self):
        # Mesma data = correção do registro existente; quem decide é o serviço.
        pass

    def dados_servico(self):
        return {campo: self.cleaned_data[campo] for campo in self._meta.fields}
