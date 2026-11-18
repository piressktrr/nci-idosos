"""Categorias autodeclaradas do cadastro (RF-PAR-01).

Raça/cor e identidade de gênero seguem as categorias do FMR fornecidas pelo responsável.
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
    NAO_INFORMADO = "nao_informado", "Não informado"  # D13: está no protótipo


class IdentidadeGenero(models.TextChoices):
    CISGENERO = "cisgenero", "Cisgênero"
    TRANSGENERO = "transgenero", "Transgênero"
    AGENERO = "agenero", "Agênero"
    NAO_DECLARADO = "nao_declarado", "Não declarado"


# Mantidos somente para não apagar autodeclarações antigas sem correspondência confirmada.
IDENTIDADES_GENERO_LEGADAS = ("travesti", "nao_binaria", "outra")


class OrigemEncaminhamento(models.TextChoices):
    """RF-PAR-06: categoria de origem. Provisória: são os exemplos do requisito até chegar a lista do FMR."""
    CRAS = "cras", "CRAS"
    CREAS = "creas", "CREAS"
    REDE = "rede", "Outro serviço da rede"
    OUTRA = "outra", "Outra origem"



class StatusParticipante(models.TextChoices):
    """Situação operacional; afastamento e desligamento definidos pelo responsável.

    Inativo/cancelado são opções legadas ainda sem equivalência de negócio.
    """
    ATIVO = "ativo", "Ativo"
    INATIVO = "inativo", "Inativo"
    CANCELADO = "cancelado", "Cancelado"
    DESLIGADO = "desligado", "Desligado"
    AFASTADO = "afastado", "Afastado"


class TipoMovimentacao(models.TextChoices):
    """Eventos por vigência; somente entrada é ingresso, retornos preservam a identidade."""
    ENTRADA = "entrada", "Entrada"
    DESLIGAMENTO = "desligamento", "Desligamento"
    REATIVACAO = "reativacao", "Reativação"
    AFASTAMENTO = "afastamento", "Afastamento"
    RETORNO = "retorno", "Retorno de afastamento"
