from django import forms

from .models import Participante


class ParticipanteForm(forms.ModelForm):
    confirmar_duplicidade = forms.BooleanField(
        label="Confirmo que é outra pessoa, com o mesmo nome e data de nascimento", required=False)

    class Meta:
        model = Participante
        fields = ("nome_completo", "data_nascimento", "sexo", "raca_cor", "identidade_genero")
        widgets = {"data_nascimento": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})}

    def __init__(self, *args, mostrar_confirmacao=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.mostrar_confirmacao = mostrar_confirmacao
        if not mostrar_confirmacao:
            # Só existe depois do alerta de duplicidade; antes disso, nunca confirma.
            del self.fields["confirmar_duplicidade"]

    def dados_servico(self):
        dados = {campo: self.cleaned_data[campo] for campo in self._meta.fields}
        return dados, self.cleaned_data.get("confirmar_duplicidade") is True
