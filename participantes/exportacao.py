"""Exportação dos participantes em CSV (RNF-SEG-11): a instituição recupera seus dados sem os desenvolvedores.

O arquivo abre direto no Excel em pt-BR (UTF-8 com BOM, separador ";") e contém dados pessoais sensíveis:
só quem tem `participantes.exportar_participante` exporta, e cada exportação fica na auditoria (sem copiar
os dados exportados para o evento). Atividades e frequência não entram aqui (são do módulo de atividades).
"""

import csv

from django.db import transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from core.permissoes import autorizar

from .categorias import TipoMovimentacao
from .consultas import situacoes_vigentes_em
from .models import Movimentacao, Participante, RegistroExportacao

PERMISSAO_EXPORTAR = "participantes.exportar_participante"
FORMATO_CSV = "csv"
BOM = "﻿"
SEPARADOR = ";"
# Início de célula que o Excel/LibreOffice interpretam como fórmula (CSV injection).
INICIO_FORMULA = ("=", "+", "-", "@", "\t", "\r")
INDICADORES = (
    ("mora_sozinho", "Mora sozinho"),
    ("tem_apoio", "Tem apoio familiar ou comunitário"),
    ("possui_deficiencia", "Possui deficiência"),
    ("recebe_bpc", "Recebe BPC"),
    ("imigrante_refugiado", "Imigrante ou refugiado"),
)
# "Código", não "ID": o Excel toma por SYLK um arquivo que começa com "ID".
CABECALHO = (
    "Código", "Nome completo", "Data de nascimento", "Sexo", "Raça/cor", "Identidade de gênero", "Endereço",
    "Telefone celular", "Telefone residencial", "Origem do encaminhamento", "Observação sobre o encaminhamento",
    "Ensino médio completo", "Status", "Data de entrada", *(rotulo for _, rotulo in INDICADORES),
    "Situação social vigente desde",
)


def _data(valor):
    return f"{valor:%d/%m/%Y}" if valor else ""


def _sim_nao(valor):
    return "" if valor is None else ("Sim" if valor else "Não")


def _celula(valor):
    """Texto da célula, neutralizando fórmulas com um apóstrofo na frente."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto.startswith(INICIO_FORMULA) else texto


def _linha(participante, situacao):
    return (
        participante.pk, participante.nome_completo, _data(participante.data_nascimento),
        participante.get_sexo_display(), participante.get_raca_cor_display(),
        participante.get_identidade_genero_display(), participante.endereco, participante.celular_formatado(),
        participante.residencial_formatado(), participante.get_origem_encaminhamento_display(),
        participante.observacao_encaminhamento, _sim_nao(participante.ensino_medio_completo),
        participante.get_status_display(), _data(participante.data_entrada_exportacao),
        *(_sim_nao(getattr(situacao, campo) if situacao else None) for campo, _ in INDICADORES),
        _data(situacao.vigente_desde if situacao else None),
    )


def _participantes():
    """Todos os cadastros com a data de entrada anotada (uma consulta, sem N+1)."""
    entrada = (Movimentacao.objects.filter(participante=OuterRef("pk"), tipo=TipoMovimentacao.ENTRADA)
               .order_by("-data", "-pk").values("data")[:1])
    return list(Participante.objects.annotate(data_entrada_exportacao=Subquery(entrada)))


@transaction.atomic
def exportar_participantes_csv(*, usuario, destino):
    """Escreve em `destino` (texto com write(): HttpResponse ou arquivo aberto com newline="") e retorna a quantidade.

    Uma linha por participante, com a situação social vigente hoje (RN-PAR-05). Número constante de consultas.
    O evento de auditoria é gravado na mesma transação: se a escrita falhar, ele não fica registrado.
    """
    autor = autorizar(usuario, PERMISSAO_EXPORTAR, mensagem="Você não tem permissão para exportar participantes.")
    participantes = _participantes()
    situacoes = situacoes_vigentes_em(timezone.localdate(), participantes)
    RegistroExportacao.objects.create(exportador=autor, acao="exportacao", usuario=autor,
                                      novos={"quantidade": len(participantes), "formato": FORMATO_CSV})
    destino.write(BOM)
    escritor = csv.writer(destino, delimiter=SEPARADOR, lineterminator="\r\n")
    escritor.writerow(CABECALHO)
    escritor.writerows([_celula(valor) for valor in _linha(participante, situacoes.get(participante.pk))]
                       for participante in participantes)
    return len(participantes)
