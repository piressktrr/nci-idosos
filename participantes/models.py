from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .categorias import IdentidadeGenero, RacaCor, Sexo
from .regras import data_minima_nascimento, faixa_etaria_fmr, idade_em, normalizar_espacos


class Participante(models.Model):
    """Identidade estável da pessoa (RF-PAR-01, RN-PAR-01): um cadastro por pessoa.

    Somente os dados exigidos pelo RF-PAR-01 (RNF-SEG-08). Raça/cor e identidade de gênero
    são corrigidas no próprio cadastro, sem vigência; a correção fica na auditoria.
    """

    nome_completo = models.CharField("nome completo", max_length=200)
    data_nascimento = models.DateField("data de nascimento")
    sexo = models.CharField("sexo", max_length=1, choices=Sexo.choices)
    raca_cor = models.CharField("raça/cor autodeclarada", max_length=20, choices=RacaCor.choices)
    identidade_genero = models.CharField("identidade de gênero", max_length=20, choices=IdentidadeGenero.choices)
    cadastrado_em = models.DateTimeField("cadastrado em", auto_now_add=True)

    class Meta:
        ordering = ["nome_completo", "pk"]
        verbose_name = "participante"
        verbose_name_plural = "participantes"
        indexes = [models.Index(fields=["data_nascimento"], name="participante_nascimento_idx")]
        constraints = [
            models.CheckConstraint(condition=models.Q(sexo__in=Sexo.values), name="participante_sexo_valido"),
            models.CheckConstraint(condition=models.Q(raca_cor__in=RacaCor.values), name="participante_raca_cor_valida"),
            models.CheckConstraint(condition=models.Q(identidade_genero__in=IdentidadeGenero.values),
                                   name="participante_identidade_genero_valida"),
        ]

    def __str__(self):
        return self.nome_completo

    def clean(self):
        super().clean()
        if isinstance(self.nome_completo, str):
            self.nome_completo = normalizar_espacos(self.nome_completo)
            if not self.nome_completo:
                raise ValidationError({"nome_completo": "Informe o nome completo."})
        if self.data_nascimento:
            if self.data_nascimento > timezone.localdate():
                raise ValidationError({"data_nascimento": "A data de nascimento não pode estar no futuro."})
            if self.data_nascimento < data_minima_nascimento():
                raise ValidationError({"data_nascimento": "Confira a data de nascimento informada."})

    def idade(self, referencia=None):
        return idade_em(self.data_nascimento, referencia or timezone.localdate())

    def faixa_etaria(self, referencia=None):
        """RN-PAR-06: sempre calculada a partir da data de nascimento."""
        return faixa_etaria_fmr(self.data_nascimento, referencia or timezone.localdate())
