from django import forms

from .models import Atividade, HorarioAtividade


class AtividadeForm(forms.ModelForm):
    class Meta:
        model = Atividade
        fields = ("nome", "local", "monitor")
        labels = {"nome": "Nome da atividade", "monitor": "Monitor/oficineiro responsável"}


class HorarioAtividadeForm(forms.ModelForm):
    class Meta:
        model = HorarioAtividade
        fields = ("dia_semana", "inicio", "fim")
        widgets = {
            "inicio": forms.TimeInput(format="%H:%M:%S", attrs={"type": "time", "step": "1"}),
            "fim": forms.TimeInput(format="%H:%M:%S", attrs={"type": "time", "step": "1"}),
        }
