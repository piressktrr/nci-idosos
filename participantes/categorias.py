"""Categorias autodeclaradas do cadastro (RF-PAR-01).

PROVISÓRIO: raça/cor segue as cinco categorias do IBGE e identidade de gênero é uma
lista de trabalho. As duas devem ser conferidas com o formulário FMR antes de produção.
Trocar as opções aqui exige apenas uma migration de alteração de choices.
"""

from django.db import models


class Sexo(models.TextChoices):
    """RN-FMR-08: o FMR classifica as faixas etárias por sexo M/F."""

    FEMININO = "F", "Feminino"
    MASCULINO = "M", "Masculino"


class RacaCor(models.TextChoices):
    BRANCA = "branca", "Branca"
    PRETA = "preta", "Preta"
    PARDA = "parda", "Parda"
    AMARELA = "amarela", "Amarela"
    INDIGENA = "indigena", "Indígena"


class IdentidadeGenero(models.TextChoices):
    MULHER_CIS = "mulher_cis", "Mulher cisgênero"
    HOMEM_CIS = "homem_cis", "Homem cisgênero"
    MULHER_TRANS = "mulher_trans", "Mulher transgênero"
    HOMEM_TRANS = "homem_trans", "Homem transgênero"
    TRAVESTI = "travesti", "Travesti"
    NAO_BINARIA = "nao_binaria", "Pessoa não binária"
    OUTRA = "outra", "Outra"
