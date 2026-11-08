from django import forms

from .models import Atividade, Aula, HorarioAtividade


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


class AulaForm(forms.ModelForm):
    class Meta:
        model = Aula
        fields = ("data", "inicio", "fim")
        widgets = {
            "data": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "inicio": forms.TimeInput(format="%H:%M:%S", attrs={"type": "time", "step": "1"}),
            "fim": forms.TimeInput(format="%H:%M:%S", attrs={"type": "time", "step": "1"}),
        }
