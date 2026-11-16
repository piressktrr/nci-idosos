from django import forms

from .models import Participante, SituacaoSocial
from .regras import so_digitos

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


class ParticipanteForm(forms.ModelForm):
    confirmar_duplicidade = forms.BooleanField(
        label="Confirmo que é outra pessoa, com o mesmo nome e data de nascimento", required=False)
    ensino_medio_completo = forms.TypedChoiceField(
        label="Ensino médio completo?", choices=SIM_NAO, coerce=_sim_nao, widget=forms.RadioSelect)

    class Meta:
        model = Participante
        fields = ("nome_completo", "endereco", "identidade_genero", "origem_encaminhamento",
                  "observacao_encaminhamento", "telefone_residencial", "telefone_celular", "data_nascimento",
                  "raca_cor", "sexo", "ensino_medio_completo", "status")
        labels = {"telefone_residencial": "Telefone fixo", "raca_cor": "Raça/cor"}
        widgets = {
            "data_nascimento": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "telefone_celular": forms.TextInput(attrs={"type": "tel", "inputmode": "numeric", "autocomplete": "off",
                                                       "placeholder": "(11) 91234-5678", "x-data": "",
                                                       "x-on:input": "mascaraTelefone($el)"}),
            "telefone_residencial": forms.TextInput(attrs={"type": "tel", "inputmode": "numeric",
                                                           "autocomplete": "off", "placeholder": "(11) 3123-4567",
                                                           "x-data": "", "x-on:input": "mascaraTelefone($el)"}),
            "observacao_encaminhamento": forms.Textarea(attrs={"rows": 4}),
        }
        help_texts = {"telefone_celular": "Informe pelo menos um dos dois telefones do próprio participante."}

    def __init__(self, *args, mostrar_confirmacao=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.mostrar_confirmacao = mostrar_confirmacao
        # Aceita máscara na digitação; o modelo guarda só os dígitos. O limite fica no clean do modelo.
        for campo in ("telefone_celular", "telefone_residencial"):
            self.fields[campo].max_length = 20
            self.fields[campo].widget.attrs["maxlength"] = 20
            self.fields[campo].validators = []
        if not mostrar_confirmacao:
            # Só existe depois do alerta de duplicidade; antes disso, nunca confirma.
            del self.fields["confirmar_duplicidade"]
        aplicar_bootstrap(self)

    def clean_telefone_celular(self):
        return so_digitos(self.cleaned_data.get("telefone_celular"))

    def clean_telefone_residencial(self):
        return so_digitos(self.cleaned_data.get("telefone_residencial"))

    def dados_servico(self):
        dados = {campo: self.cleaned_data[campo] for campo in self._meta.fields}
        return dados, self.cleaned_data.get("confirmar_duplicidade") is True


class SituacaoSocialForm(forms.ModelForm):
    """RF-PAR-04: cada indicador é sim ou não; não marcado significa "não"."""

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

    def validate_unique(self):
        # Mesma data = correção do registro existente; quem decide é o serviço.
        pass

    def dados_servico(self):
        return {campo: self.cleaned_data[campo] for campo in self._meta.fields}
