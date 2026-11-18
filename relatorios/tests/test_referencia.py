from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from relatorios.forms import MesReferenciaForm
from relatorios.services import consultar_periodo_fmr


class ReferenciaFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="equipe_fmr_ficticia")
        cls.grupo, _ = Group.objects.get_or_create(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def consultar(self, **kwargs):
        return consultar_periodo_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | kwargs))

    def test_periodo_mensal_bissexto_e_limites_de_ano(self):
        self.assertEqual(self.consultar(), {"inicio": date(2024, 2, 1), "fim": date(2024, 2, 29)})
        self.assertEqual(self.consultar(ano=2023)["fim"], date(2023, 2, 28))
        self.assertEqual(self.consultar(ano=9999, mes=12)["fim"], date(9999, 12, 31))
        self.assertEqual(self.consultar(ano=1, mes=1)["inicio"], date(1, 1, 1))

    def test_servico_rejeita_valores_invalidos(self):
        for ano, mes in ((0, 2), (10000, 1), (2024, 0), (2024, 13), (True, 2), (2024, False), ("2024", 2)):
            with self.subTest(ano=ano, mes=mes), self.assertRaises(ValidationError):
                self.consultar(ano=ano, mes=mes)

    def test_formulario_aceita_apenas_mes_ano_no_formato_previsto(self):
        for valor in ("2024-02", "0001-01", "9999-12"):
            self.assertTrue(MesReferenciaForm({"mes": valor}).is_valid())
        for valor in ("", "2024-2", "2024-13", "0000-01", "2024-02-01", "abcd", "<script>"):
            with self.subTest(valor=valor):
                self.assertFalse(MesReferenciaForm({"mes": valor}).is_valid())

    def test_http_exige_login_e_rejeita_post(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), reverse("entrar") + "?next=" + self.url,
                             fetch_redirect_response=False)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(self.url, {"mes": "2024-02"}).status_code, 405)

    def test_sem_perfil_e_staff_isolado_nao_acessam(self):
        self.usuario.groups.clear()
        self.usuario.is_staff = True
        self.usuario.save()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        with self.assertRaises(PermissionDenied):
            self.consultar()
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())
        self.assertNotContains(self.client.get(reverse("inicio")), 'href="' + self.url + '"')

    def test_administrador_e_superusuario_acessam(self):
        self.usuario.groups.clear()
        grupo, _ = Group.objects.get_or_create(name="Administrador")
        self.usuario.groups.add(grupo)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.usuario.groups.clear()
        self.usuario.is_superuser = True
        self.usuario.save()
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_autorizacao_atual_sem_cache_e_conta_desativada(self):
        self.consultar()
        self.usuario.groups.clear()
        with self.assertRaises(PermissionDenied):
            self.consultar()
        self.usuario.groups.add(self.grupo)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.consultar()

    def test_mes_atual_local_por_padrao_e_escolha_preservada(self):
        with patch("relatorios.views.timezone.localdate", return_value=date(2027, 1, 1)):
            resposta = self.client.get(self.url)
        self.assertEqual(resposta.context["periodo"]["inicio"], date(2027, 1, 1))
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'value="2024-02"')
        self.assertContains(resposta, "29/02/2024")
        self.assertContains(resposta, "Mês de referência: 02/2024")
        self.assertContains(resposta, "Indicadores disponíveis")

    def test_mes_invalido_nao_vira_mes_atual_e_texto_escapado(self):
        resposta = self.client.get(self.url, {"mes": "<script>"})
        self.assertTrue(resposta.context["form"].errors)
        self.assertIsNone(resposta.context["periodo"])
        self.assertContains(resposta, "&lt;script&gt;")
        self.assertNotContains(resposta, 'id="periodo-selecionado"')

    def test_menu_cartao_e_consulta_sem_escrita(self):
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertEqual(resposta.status_code, 200)
        for consulta in consultas:
            sql = consulta["sql"].upper()
            self.assertTrue(sql.startswith("SELECT"), sql)
        self.assertContains(resposta, 'href="' + self.url + '"')
        self.assertContains(self.client.get(reverse("inicio")), 'href="' + self.url + '"')

    def test_selecao_do_periodo_isolada_nao_consulta_outros_modulos(self):
        with CaptureQueriesContext(connection) as consultas:
            self.consultar()
        for consulta in consultas:
            sql = consulta["sql"].upper()
            self.assertNotIn('"PARTICIPANTES_', sql)
            self.assertNotIn('"ATIVIDADES_', sql)
