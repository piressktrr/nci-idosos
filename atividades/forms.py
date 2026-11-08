from django import forms
from django.utils import timezone

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
            "inicio": forms.TimeInput(format="%H:%M", attrs={"type": "time", "step": "60"}),
            "fim": forms.TimeInput(format="%H:%M", attrs={"type": "time", "step": "60"}),
        }


class AulaForm(forms.ModelForm):
    tipo = forms.ChoiceField(label="Tipo de aula", choices=[
        ("", "Selecione o tipo de aula"),
        (Aula.Tipo.REGULAR, "Regular"),
        (Aula.Tipo.EXTRA, "Extra"),
        (Aula.Tipo.REMARCADA, "Remarcada"),
    ])

    def __init__(self, *args, horarios=(), **kwargs):
        super().__init__(*args, **kwargs)
        # Sugestões só no formulário novo: POST sempre preserva os dados enviados.
        if not self.is_bound and not self.instance.pk:
            agora = timezone.localtime()
            self.initial.setdefault("tipo", Aula.Tipo.REGULAR)
            self.initial.setdefault("data", agora.date())
            self.initial.setdefault("fim", agora.time().replace(second=0, microsecond=0))
            horarios_do_dia = [item for item in horarios if item["dia_semana"] == agora.weekday()]
            if len(horarios_do_dia) == 1:
                self.initial.setdefault("inicio", horarios_do_dia[0]["inicio"])
                self.initial["fim"] = horarios_do_dia[0]["fim"]

    class Meta:
        model = Aula
        fields = ("tipo", "data", "inicio", "fim")
        widgets = {
            "data": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "inicio": forms.TimeInput(format="%H:%M", attrs={"type": "time", "step": "60"}),
            "fim": forms.TimeInput(format="%H:%M", attrs={"type": "time", "step": "60"}),
        }
