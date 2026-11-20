from importlib import import_module

from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from participantes.models import MotivoDesligamento
from relatorios.services import consultar_desligamentos_motivo_fmr


class MotivosOficiaisFMRTests(TestCase):
    motivos = {
        "Mudança de endereço", "Oferta do serviço em domicílio",
        "Transferência para outro serviço", "Óbito", "Desistência", "Excesso de faltas",
    }

    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="catalogo_fmr_ficticio")
        self.usuario.groups.add(Group.objects.get(name="Equipe"))

    def test_migration_cadastra_seis_motivos_e_relatorio_mostra_zeros(self):
        self.assertSetEqual(set(MotivoDesligamento.objects.filter(ativo=True).values_list("descricao", flat=True)), self.motivos)
        dados = consultar_desligamentos_motivo_fmr(usuario=self.usuario, ano=2024, mes=2)
        self.assertSetEqual({linha["descricao"] for linha in dados["linhas"]}, self.motivos)
        self.assertEqual([linha["quantidade"] for linha in dados["linhas"]], [0] * 6)
        self.assertEqual(dados["total"], 0)
        self.client.force_login(self.usuario)
        resposta = self.client.get(reverse("relatorios:fmr"), {"mes": "2024-02"})
        for descricao in self.motivos:
            self.assertContains(resposta, descricao)

    def test_repetir_cadastro_nao_duplica_nem_reativa_ou_altera_outros_motivos(self):
        MotivoDesligamento.objects.filter(descricao="Desistência").update(ativo=False)
        extra = MotivoDesligamento.objects.create(descricao="Motivo fictício adicional")
        migration = import_module("participantes.migrations.0010_motivos_fmr")
        migration.cadastrar_motivos(apps, connection.schema_editor())
        migration.cadastrar_motivos(apps, connection.schema_editor())
        self.assertEqual(MotivoDesligamento.objects.count(), 7)
        self.assertFalse(MotivoDesligamento.objects.get(descricao="Desistência").ativo)
        self.assertTrue(MotivoDesligamento.objects.filter(pk=extra.pk).exists())
