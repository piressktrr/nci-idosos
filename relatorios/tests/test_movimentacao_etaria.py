from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.template.loader import render_to_string
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from relatorios.services import consultar_movimentacao_etaria_fmr


class MovimentacaoEtariaFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="etaria_fmr_ficticio")
        cls.grupo = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def consultar(self, **kwargs):
        return consultar_movimentacao_etaria_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | kwargs))

    def test_estrutura_das_faixas_e_sexos_sem_contagens_presumidas(self):
        resultado = self.consultar()
        self.assertEqual({(linha["faixa"], linha["sexo_codigo"]) for linha in resultado["linhas"]},
                         {(faixa, sexo) for faixa in ("60–64", "65–69", "70–74", "75 anos ou mais") for sexo in ("M", "F")})
        for linha in [*resultado["linhas"], resultado["totais"]]:
            for campo in ("vieram_mes_anterior", "ingressaram", "sairam", "permanecem"):
                self.assertEqual(linha[campo], 0)
        self.assertEqual(resultado["pendencias"], [])

    def test_consulta_sem_cadastros_retorna_zeros_sem_escrita(self):
        with CaptureQueriesContext(connection) as consultas:
            resultado = self.consultar()
        self.assertEqual(resultado["pendencias"], [])
        for consulta in consultas:
            sql = consulta["sql"].upper()
            self.assertTrue(sql.startswith("SELECT"), sql)


    def test_mes_selecionado_limites_e_bissexto(self):
        for ano, mes, fim in ((2024, 2, date(2024, 2, 29)), (2023, 2, date(2023, 2, 28)),
                              (1, 1, date(1, 1, 31)), (9999, 12, date(9999, 12, 31))):
            with self.subTest(ano=ano, mes=mes):
                resultado = self.consultar(ano=ano, mes=mes)
                self.assertEqual(resultado["periodo"]["fim"], fim)
                self.assertEqual(resultado["totais"]["permanecem"], 0)
        for ano, mes in ((True, 2), (2024, False), (0, 1), (10000, 1), (2024, 0), (2024, 13)):
            with self.subTest(ano=ano, mes=mes), self.assertRaises(ValidationError):
                self.consultar(ano=ano, mes=mes)

    def test_interface_explicita_referencia_retornos_e_zeros_validos(self):
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Movimentação por faixa etária e sexo")
        self.assertContains(resposta, "Movimentação do mês 02/2024")
        self.assertContains(resposta, "dia 1 do mês")
        self.assertContains(resposta, "Reativados no mês")
        self.assertNotContains(resposta, "Falta definir")
        html_tabela = resposta.content.decode().split('id="tabela-movimentacao-etaria"')[1].split("</table>")[0]
        self.assertIn("0", html_tabela)
        for rotulo in ("Vieram do mês anterior", "Ingressaram", "Saíram", "Permanecem"):
            self.assertIn(rotulo, html_tabela)

    def test_permissao_atual_de_participantes_exigida_independente_de_atividades(self):
        self.assertTrue(self.consultar()["linhas"])
        self.assertContains(self.client.get(self.url), 'id="tabela-movimentacao-etaria"')
        permissao = Permission.objects.get(content_type__app_label="participantes", codename="view_participante")
        self.grupo.permissions.remove(permissao)
        resultado = self.consultar()
        self.assertEqual(resultado["linhas"], [])
        self.assertIsNone(resultado["totais"])
        self.assertEqual(resultado["pendencias"], [])
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Seu perfil não possui permissão para consultar a movimentação")
        self.assertNotContains(resposta, 'id="tabela-movimentacao-etaria"')

    def test_login_perfil_ativo_e_apenas_consulta_get(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.usuario.groups.clear()
        with self.assertRaises(PermissionDenied):
            self.consultar()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.usuario.groups.add(self.grupo)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.consultar()
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)

    def test_mes_invalido_nao_chama_servico_ou_exibe_estrutura(self):
        with patch("relatorios.services.consultar_movimentacao_etaria_fmr") as servico:
            resposta = self.client.get(self.url, {"mes": "2024-13"})
        servico.assert_not_called()
        self.assertTrue(resposta.context["form"].errors)
        self.assertNotContains(resposta, 'id="movimentacao-etaria"')

    def test_valor_ausente_e_zero_real_sao_distintos_na_renderizacao_futura(self):
        desconhecido = render_to_string("relatorios/_valor_contagem.html", {"valor": None})
        conhecido = render_to_string("relatorios/_valor_contagem.html", {"valor": 0})
        self.assertIn("Não calculado", desconhecido)
        self.assertEqual(conhecido.strip(), "0")
