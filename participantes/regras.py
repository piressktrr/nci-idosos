"""Regras de negócio puras de participantes, sem acesso ao banco."""

import re
import unicodedata
from datetime import date

# RN-FMR-08: faixas etárias do FMR (limite inferior, rótulo). A última é aberta.
FAIXAS_ETARIAS_FMR = ((75, "75 anos ou mais"), (70, "70 a 74 anos"), (65, "65 a 69 anos"), (60, "60 a 64 anos"))


def idade_em(data_nascimento, referencia):
    """Idade completa na data de referência."""
    aniversario_passou = (referencia.month, referencia.day) >= (data_nascimento.month, data_nascimento.day)
    return referencia.year - data_nascimento.year - (0 if aniversario_passou else 1)


def faixa_etaria_fmr(data_nascimento, referencia):
    """RN-PAR-06: faixa derivada da data de nascimento, nunca armazenada.

    Retorna None abaixo de 60 anos, idade sem faixa no FMR. Usa a idade exatamente em `referencia`;
    para o mês do FMR use `faixa_etaria_fmr_no_mes` (RN-PAR-07).
    """
    idade = idade_em(data_nascimento, referencia)
    return next((rotulo for minimo, rotulo in FAIXAS_ETARIAS_FMR if idade >= minimo), None)


def inicio_do_mes(data):
    """RN-PAR-07 (P01, NCI 20/11/2026): a faixa etária do mês usa a idade no dia 1º desse mês."""
    return data.replace(day=1)


def faixa_etaria_fmr_no_mes(data_nascimento, data_no_mes):
    """RN-PAR-07: faixa do FMR no mês de `data_no_mes`, pela idade no dia 1º; quem faz aniversário durante o
    mês só muda de faixa no mês seguinte."""
    return faixa_etaria_fmr(data_nascimento, inicio_do_mes(data_no_mes))


def normalizar_espacos(texto):
    return re.sub(r"\s+", " ", texto).strip()


def chave_nome(nome):
    """Nome comparável para detectar possível duplicidade: sem acentos, caixa ou espaços extras."""
    sem_acentos = "".join(c for c in unicodedata.normalize("NFKD", nome) if not unicodedata.combining(c))
    return normalizar_espacos(sem_acentos).casefold()


def data_minima_nascimento():
    return date(1900, 1, 1)


def so_digitos(texto):
    """Tira máscara, espaços e pontuação de um telefone digitado."""
    return re.sub(r"\D", "", texto or "")


def celular_valido(numero):
    """RF-PAR-02: DDD + 9 dígitos começando por 9, só dígitos."""
    return len(numero) == 11 and numero[0] != "0" and numero[1] != "0" and numero[2] == "9"


def residencial_valido(numero):
    """RF-PAR-02: DDD + 8 dígitos de telefone fixo (começa por 2 a 5), só dígitos."""
    return len(numero) == 10 and numero[0] != "0" and numero[1] != "0" and numero[2] in "2345"


def formatar_telefone(numero):
    if len(numero) == 11:
        return f"({numero[:2]}) {numero[2:7]}-{numero[7:]}"
    if len(numero) == 10:
        return f"({numero[:2]}) {numero[2:6]}-{numero[6:]}"
    return numero
