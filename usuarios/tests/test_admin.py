"""RNF-SEG-07: contas e grupos fora do admin do Django; só pelas telas próprias, auditadas. Dados fictícios."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from usuarios.models import RegistroConta
from usuarios.services import cadastrar_colaborador

from .base import administrador, dados_cadastro


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class ContasForaDoAdminTests(TestCase):
    def test_user_e_group_nao_estao_registrados(self):
        self.assertFalse(admin.site.is_registered(get_user_model()))
        self.assertFalse(admin.site.is_registered(Group))
        for nome in ("admin:auth_user_changelist", "admin:auth_user_add", "admin:auth_group_changelist"):
            with self.subTest(url=nome), self.assertRaises(NoReverseMatch):
                reverse(nome)

    def test_superusuario_nao_altera_contas_pelo_admin(self):
        superusuario = get_user_model().objects.create_superuser("super_admin_ficticio", password=None)
        self.client.force_login(superusuario)
        indice = self.client.get(reverse("admin:index"))
        self.assertEqual(indice.status_code, 200)
        self.assertNotContains(indice, "/admin/auth/")
        for url in ("/admin/auth/user/", "/admin/auth/user/add/", f"/admin/auth/user/{superusuario.pk}/change/",
                    "/admin/auth/group/", "/admin/auth/group/add/"):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 404)
        resposta = self.client.post("/admin/auth/user/add/", {"username": "pelo_admin_ficticio",
                                                              "password1": "Girassol-Ficticio-2026",
                                                              "password2": "Girassol-Ficticio-2026"})
        self.assertEqual(resposta.status_code, 404)
        self.assertFalse(get_user_model().objects.filter(username="pelo_admin_ficticio").exists())

    def test_tela_propria_continua_auditando(self):
        admin_conta = administrador()
        nova = cadastrar_colaborador(usuario=admin_conta, **dados_cadastro())
        self.assertTrue(RegistroConta.objects.filter(conta=nova, acao="cadastro").exists())
