from datetime import date, time
from unittest.mock import patch
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from usuarios.tests.base import administrador, equipe
from atividades.models import Atividade, Aula, RegistroSituacaoAtividade
from atividades.services import registrar_aula, registrar_aula_cancelada, inscrever_participante, consultar_frequencia_mensal
from atividades.situacao import alterar_situacao_atividade
from atividades.espera import adicionar_espera


@override_settings(DEBUG=True, NCI_PARTICIPANTES_PROVIDER="atividades.integracoes.participantes_placeholder.ProvedorPlaceholder")
class SituacaoAtividadeTests(TestCase):
    def setUp(self):
        self.admin = administrador()
        self.equipe = equipe()
        self.admin.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades"))
        self.atividade = Atividade.objects.create(nome="Oficina fictícia", local="Sala", monitor="Teste")

    def alterar(self, ativa, **kwargs):
        return alterar_situacao_atividade(usuario=kwargs.get("usuario", self.admin), atividade_id=self.atividade.pk, ativa=ativa)

    def test_desativacao_bloqueia_novas_gravacoes_preserva_aulas_e_totais(self):
        dados = dict(usuario=self.admin, atividade_id=self.atividade.pk, data=date(2024, 2, 1), inicio=time(9), fim=time(10))
        aula = registrar_aula(**dados)
        self.alterar(False)
        for servico in (registrar_aula, registrar_aula_cancelada):
            with self.assertRaises(ValidationError):
                servico(**dados)
        for servico in (inscrever_participante, adicionar_espera):
            with self.assertRaises(ValidationError):
                servico(usuario=self.admin, atividade_id=self.atividade.pk, participante_referencia="demo-1")
        self.assertTrue(Aula.objects.filter(pk=aula.pk).exists())
        self.assertEqual(consultar_frequencia_mensal(usuario=self.admin, ano=2024, mes=2)["totais"]["aulas_realizadas"], 1)
        self.alterar(True)
        registrar_aula(**dados)
        self.assertEqual(Aula.objects.count(), 2)

    def test_admin_apenas_idempotencia_e_rollback(self):
        with self.assertRaises(PermissionDenied):
            self.alterar(False, usuario=self.equipe)
        with patch("atividades.situacao.RegistroSituacaoAtividade.objects.create", side_effect=RuntimeError), self.assertRaises(RuntimeError):
            self.alterar(False)
        self.atividade.refresh_from_db()
        self.assertTrue(self.atividade.ativa)
        self.alterar(False)
        self.alterar(False)
        self.assertEqual(RegistroSituacaoAtividade.objects.count(), 1)

    def test_interface_confirma_por_post_e_nao_seleciona_inativa_para_chamada(self):
        self.client.force_login(self.admin)
        url = reverse("atividades:situacao", args=[self.atividade.pk])
        self.assertContains(self.client.get(url), "histórico continua disponível")
        self.atividade.refresh_from_db()
        self.assertTrue(self.atividade.ativa)
        self.assertEqual(self.client.post(url, {"ativo": "0"}).status_code, 302)
        from atividades.views.nova_chamada import EscolherAtividadeForm
        self.assertFalse(EscolherAtividadeForm({"atividade": self.atividade.pk}).is_valid())
        self.assertContains(self.client.get(reverse("atividades:lista")), "Inativa")
