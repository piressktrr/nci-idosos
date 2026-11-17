"""RNF-SEG-11: exporta os participantes em CSV pelo terminal, sem depender da interface."""

import io
import os
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from participantes.exportacao import exportar_participantes_csv


class Command(BaseCommand):
    help = ("Exporta todos os participantes em CSV (UTF-8 com BOM, separador ';'), em nome de um usuário com a "
            "permissão 'Pode exportar participantes'. A exportação fica na auditoria. O arquivo contém dados "
            "sensíveis: guarde com acesso restrito e apague depois do uso.")

    def add_arguments(self, parser):
        parser.add_argument("--usuario", required=True, help="Usuário (username) que faz a exportação.")
        parser.add_argument("--saida", required=True, help="Caminho do arquivo CSV a criar.")
        parser.add_argument("--sobrescrever", action="store_true", help="Substitui o arquivo se ele já existir.")

    def handle(self, *args, usuario, saida, sobrescrever, **options):
        caminho = Path(saida)
        if caminho.exists() and not sobrescrever:
            raise CommandError(f"O arquivo {caminho} já existe. Use --sobrescrever para substituí-lo.")
        autor = get_user_model().objects.filter(username=usuario).first()
        if autor is None:
            raise CommandError(f"Usuário {usuario!r} não encontrado.")
        # Gera em memória antes de abrir o arquivo: sem permissão, nenhum arquivo é criado. A transação externa
        # desfaz o evento de auditoria se a gravação do arquivo falhar.
        conteudo = io.StringIO(newline="")
        with transaction.atomic():
            try:
                quantidade = exportar_participantes_csv(usuario=autor, destino=conteudo)
            except PermissionDenied as erro:
                raise CommandError(str(erro)) from erro
            self._gravar(caminho, conteudo.getvalue(), sobrescrever)
        self.stdout.write(self.style.SUCCESS(f"{quantidade} participante(s) exportado(s) para {caminho}."))
        self.stdout.write("Atenção: o arquivo contém dados pessoais sensíveis. Guarde com acesso restrito e "
                          "apague depois do uso.")

    @staticmethod
    def _gravar(caminho, texto, sobrescrever):
        # O_EXCL: não substitui um arquivo criado entre a verificação e a gravação. 0o600: só o dono lê (Linux).
        modo = os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0)
        modo |= os.O_TRUNC if sobrescrever else os.O_EXCL
        try:
            descritor = os.open(caminho, modo, 0o600)
        except FileExistsError as erro:
            raise CommandError(f"O arquivo {caminho} já existe. Use --sobrescrever para substituí-lo.") from erro
        except OSError as erro:
            raise CommandError(f"Não foi possível criar o arquivo {caminho}: {erro.strerror}.") from erro
        with os.fdopen(descritor, "w", encoding="utf-8", newline="") as arquivo:
            arquivo.write(texto)
