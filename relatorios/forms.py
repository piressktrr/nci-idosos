from datetime import date

from django import forms


class MesReferenciaForm(forms.Form):
    mes = forms.RegexField(
        label="Mês de referência", regex=r"\A[0-9]{4}-(0[1-9]|1[0-2])\Z",
        widget=forms.TextInput(attrs={"type": "month", "min": "0001-01", "max": "9999-12"}),
        error_messages={"invalid": "Informe um mês válido no formato AAAA-MM."},
    )

    def clean_mes(self):
        try:
            return date.fromisoformat(self.cleaned_data["mes"] + "-01")
        except ValueError as erro:
            raise forms.ValidationError("Informe um ano entre 1 e 9999.") from erro
