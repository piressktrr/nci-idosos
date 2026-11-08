from django import forms
from django.utils import timezone

from .models import Atividade, Aula, HorarioAtividade, Frequencia, MotivoFalta


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


class InscricaoForm(forms.Form):
    participante_referencia = forms.ChoiceField(label="Participante")

    def __init__(self, *args, participantes=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["participante_referencia"].choices = [
            ("", "Selecione um participante"),
            *((item.referencia, item.nome) for item in participantes),
        ]


class ChamadaForm(forms.Form):
    def __init__(self, *args, participantes=(), **kwargs):
        super().__init__(*args, **kwargs)
        for item in participantes:
            if item["disponivel"] and item["frequencia"] is None:
                self.fields[f"registro_{item['inscricao_id']}"] = forms.ChoiceField(
                    label=f"Situação de {item['nome']}", required=False,
                    choices=Frequencia.Situacao.choices, widget=forms.RadioSelect,
                    initial=Frequencia.Situacao.PRESENTE,
                )
                self.fields[f"motivo_{item['inscricao_id']}"] = forms.ModelChoiceField(
                    label=f"Motivo da falta de {item['nome']} (opcional)", required=False,
                    queryset=MotivoFalta.objects.filter(ativo=True), empty_label="Sem motivo informado",
                )
                self.fields[f"observacao_{item['inscricao_id']}"] = forms.CharField(
                    label=f"Observação sobre a falta de {item['nome']} (opcional)", required=False, max_length=1000,
                    widget=forms.Textarea(attrs={"rows": 2}),
                )

    def clean(self):
        dados = super().clean()
        for campo in self.data:
            if campo.startswith(("registro_", "motivo_", "observacao_")):
                if campo not in self.fields or (hasattr(self.data, "getlist") and len(self.data.getlist(campo)) != 1):
                    raise forms.ValidationError("Há inscrição inválida, repetida ou já lançada. Atualize a chamada.")
        self.registros = {int(campo.removeprefix("registro_")): valor for campo, valor in dados.items() if campo.startswith("registro_") and valor}
        self.justificativas = {}
        for campo, valor in list(dados.items()):
            if campo.startswith(("motivo_", "observacao_")) and valor and int(campo.split("_")[1]) not in self.registros:
                self.add_error(campo, "Selecione a ausência justificada correspondente.")
        for identificador, situacao in self.registros.items():
            motivo = dados.get(f"motivo_{identificador}")
            observacao = dados.get(f"observacao_{identificador}", "")
            if situacao != Frequencia.Situacao.JUSTIFICADO and (motivo or observacao):
                self.add_error(f"registro_{identificador}", "Motivo e observação só se aplicam à ausência justificada.")
            elif situacao == Frequencia.Situacao.JUSTIFICADO:
                self.justificativas[identificador] = {"motivo_id": motivo.pk if motivo else None, "observacao": observacao}
        if not self.registros and not self.errors:
            raise forms.ValidationError("Selecione ao menos uma situação para lançar.")
        return dados


class MotivoFaltaForm(forms.ModelForm):
    class Meta:
        model = MotivoFalta
        fields = ("descricao", "ativo")


class CorrecaoFrequenciaForm(forms.Form):
    situacao = forms.ChoiceField(label="Situação", choices=Frequencia.Situacao.choices, widget=forms.RadioSelect)
    motivo_id = forms.ModelChoiceField(label="Motivo (opcional)", queryset=MotivoFalta.objects.none(), required=False)
    observacao = forms.CharField(label="Observação (opcional)", required=False, max_length=1000, widget=forms.Textarea(attrs={"rows": 3}))
    versao_esperada = forms.IntegerField(widget=forms.HiddenInput, min_value=1)

    def __init__(self, *args, frequencia, **kwargs):
        super().__init__(*args, **kwargs)
        from django.db.models import Q
        self.fields["motivo_id"].queryset = MotivoFalta.objects.filter(Q(ativo=True) | Q(pk=frequencia.motivo_id))
        self.initial.update({"situacao": frequencia.situacao, "motivo_id": frequencia.motivo_id,
                             "observacao": frequencia.observacao, "versao_esperada": frequencia.versao})

    def clean(self):
        dados = super().clean()
        motivo = dados.get("motivo_id")
        dados["motivo_id"] = motivo.pk if motivo else None
        if dados.get("situacao") != Frequencia.Situacao.JUSTIFICADO and (motivo or dados.get("observacao")):
            raise forms.ValidationError("Motivo e observação só se aplicam à ausência justificada.")
        return dados
