from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, Client
from django.urls import reverse
from usuarios.models import RegistroConta
from usuarios.services import alterar_situacao_conta
from .base import administrador, equipe


class SituacaoContaTests(TestCase):
    def setUp(self):
        self.admin = administrador()
        self.conta = equipe()

    def alterar(self, ativo, **kwargs):
        return alterar_situacao_conta(usuario=kwargs.get("usuario", self.admin),
            conta_id=kwargs.get("conta_id", self.conta.pk), ativo=ativo)

    def test_desativa_reativa_sem_excluir_historico_e_sem_reabrir_sessao_antiga(self):
        cliente = Client()
        cliente.force_login(self.conta)
        self.alterar(False)
        self.assertNotIn("_auth_user_id", cliente.session)
        self.alterar(True)
        self.assertNotIn("_auth_user_id", cliente.session)
        self.assertTrue(get_user_model().objects.get(pk=self.conta.pk).is_active)
        self.assertEqual(RegistroConta.objects.filter(alvo_id=self.conta.pk).count(), 2)

    def test_acao_repetida_e_idempotente_e_tipos_invalidos_recusados(self):
        self.alterar(False)
        self.alterar(False)
        self.assertEqual(RegistroConta.objects.count(), 1)
        for valor in (0, 1, "false", None):
            with self.assertRaises(ValidationError):
                self.alterar(valor)

    def test_nao_desativa_proprio_admin_ou_admin_por_usuario_comum(self):
        with self.assertRaises(ValidationError):
            self.alterar(False, conta_id=self.admin.pk)
        with self.assertRaises(PermissionDenied):
            self.alterar(False, usuario=self.conta, conta_id=self.admin.pk)
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])
        with self.assertRaises(PermissionDenied):
            self.alterar(False)

    def test_rollback_inclui_sessoes_e_situacao(self):
        cliente = Client()
        cliente.force_login(self.conta)
        with patch("usuarios.services._registrar", side_effect=RuntimeError), self.assertRaises(RuntimeError):
            self.alterar(False)
        self.conta.refresh_from_db()
        self.assertTrue(self.conta.is_active)
        self.assertIn("_auth_user_id", cliente.session)

    def test_tela_get_sem_mutacao_post_exige_admin_e_csrf(self):
        url = reverse("usuarios:situacao", args=[self.conta.pk])
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(url), "encerra as sessões")
        self.assertTrue(get_user_model().objects.get(pk=self.conta.pk).is_active)
        csrf = Client(enforce_csrf_checks=True)
        csrf.force_login(self.admin)
        self.assertEqual(csrf.post(url, {"ativo": "0"}).status_code, 403)
        self.assertEqual(self.client.post(url, {"ativo": "0"}).status_code, 302)
        self.client.force_login(self.conta)
        self.assertNotEqual(self.client.get(url).status_code, 200)
