from django.core.management.base import BaseCommand
from django.db import DEFAULT_DB_ALIAS

from core.perfis import garantir_perfis


class Command(BaseCommand):
    help = ("Cria os grupos Equipe e Administrador e acrescenta as permissões mínimas de cada um (RF-USR-02). "
            "Idempotente; não remove permissões dadas à mão. Também roda a cada migrate.")

    def add_arguments(self, parser):
        parser.add_argument("--database", default=DEFAULT_DB_ALIAS, help="Banco a usar (padrão: default).")

    def handle(self, *args, database, **options):
        for nome, (criado, acrescentadas) in garantir_perfis(using=database).items():
            situacao = "criado" if criado else "já existia"
            self.stdout.write(f"Grupo {nome}: {situacao}; {acrescentadas} permissão(ões) acrescentada(s).")
        self.stdout.write(self.style.SUCCESS("Perfis de acesso garantidos."))
