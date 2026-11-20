from importlib import import_module
from django.apps import apps
from django.db import connection
from django.test import TestCase
from atividades.models import CategoriaFMR


class CategoriasPadraoFMRTests(TestCase):
    def test_doze_categorias_oficiais_cadastradas_sem_duplicar_ou_reativar(self):
        migration = import_module("atividades.migrations.0018_categorias_padrao_fmr")
        self.assertEqual(len(migration.CATEGORIAS_FMR), 12)
        self.assertEqual(CategoriaFMR.objects.filter(nome__in=migration.CATEGORIAS_FMR).count(), 12)
        categoria = CategoriaFMR.objects.get(nome="Atividades esportivas")
        CategoriaFMR.objects.filter(pk=categoria.pk).update(ativa=False)
        migration.cadastrar_categorias(apps, connection.schema_editor())
        self.assertEqual(CategoriaFMR.objects.filter(nome__in=migration.CATEGORIAS_FMR).count(), 12)
        categoria.refresh_from_db()
        self.assertFalse(categoria.ativa)
