from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from atividades.models import Atividade, Aula, Frequencia, Inscricao
from relatorios.services import consultar_indicadores_fmr


@override_settings(NCI_PARTICIPANTES_PROVIDER="participantes.provedor.ProvedorParticipantes")
class IndicadoresFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="indicadores_fmr_ficticio")
        grupo, _ = Group.objects.get_or_create(name="Equipe")
        cls.usuario.groups.add(grupo)
        cls.permissoes = Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("view_atividade", "view_aula", "view_frequencia"))
        cls.usuario.user_permissions.add(*cls.permissoes)
        cls.atividade = Atividade.objects.create(nome="Oficina fictícia", local="Sala", monitor="Teste")
        cls.inscricao = Inscricao.objects.create(atividade=cls.atividade, origem_participante="participantes",
            participante_referencia="referencia-ficticia", cadastrada_por=cls.usuario)
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def consultar(self, **kwargs):
        return consultar_indicadores_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | kwargs))

    def valores(self, resultado):
        return {item["codigo"]: item["valor"] for item in resultado["indicadores"]}

    def lancar(self, data, situacao="presente", cancelada=False, inscricao=None):
        aula = Aula.objects.create(atividade=self.atividade, data=data, inicio=time(9), fim=time(10),
            situacao="cancelada" if cancelada else "realizada")
        return Frequencia.objects.create(aula=aula, inscricao=inscricao or self.inscricao, situacao=situacao)

    def test_limites_bissexto_cancelamentos_ausencias_e_multiplas_ocorrencias(self):
        self.lancar(date(2024, 1, 31))
        primeira = self.lancar(date(2024, 2, 1))
        self.lancar(date(2024, 2, 29))
        self.lancar(date(2024, 3, 1))
        self.lancar(date(2024, 2, 10), cancelada=True)
        self.lancar(date(2024, 2, 11), situacao="ausente")
        self.lancar(date(2024, 2, 12), situacao="ausente_justificado")
        outra = Inscricao.objects.create(atividade=self.atividade, origem_participante="participantes",
            participante_referencia="outra-referencia-ficticia", cadastrada_por=self.usuario)
        Frequencia.objects.create(aula=primeira.aula, inscricao=outra, situacao="presente")
        self.assertEqual(self.valores(self.consultar()), {"aulas_realizadas": 4, "participacoes": 3})

    def test_mudanca_de_mes_e_correcao_refletidas_na_interface_sem_escrita(self):
        frequencia = self.lancar(date(2024, 2, 29))
        self.lancar(date(2024, 3, 1))
        Frequencia.objects.filter(pk=frequencia.pk).update(situacao="ausente")
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertEqual(self.valores(resposta.context), {"aulas_realizadas": 1, "participacoes": 0})
        self.assertContains(resposta, "Participações por presença")
        self.assertContains(resposta, "a mesma pessoa pode contar mais de uma vez")
        self.assertContains(resposta, "29/02/2024")
        self.assertEqual(self.valores(self.client.get(self.url, {"mes": "2024-03"}).context),
                         {"aulas_realizadas": 1, "participacoes": 1})
        for consulta in consultas:
            self.assertTrue(consulta["sql"].upper().startswith("SELECT"), consulta["sql"])

    def test_mes_sem_movimento_exibe_zeros_reais_sem_criar_outros_indicadores(self):
        resultado = self.consultar()
        self.assertEqual(self.valores(resultado), {"aulas_realizadas": 0, "participacoes": 0})
        self.assertEqual(resultado["aviso"], "")
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Indicadores disponíveis", count=1)
        for texto in ("Permanentes", "Desligamentos", "BPC"):
            self.assertNotContains(resposta, texto)

    def test_permissoes_da_fonte_revogadas_nao_viram_zero_nem_sao_concedidas(self):
        self.consultar()
        for permissao in self.permissoes:
            with self.subTest(permissao=permissao.codename):
                self.usuario.user_permissions.remove(permissao)
                resultado = self.consultar()
                self.assertEqual(resultado["indicadores"], [])
                resposta = self.client.get(self.url, {"mes": "2024-02"})
                self.assertContains(resposta, "Seu perfil não possui as permissões")
                self.assertNotContains(resposta, 'id="tabela-indicadores-fmr"')
                self.usuario.user_permissions.add(permissao)

    def test_acesso_fmr_e_periodo_validados_antes_de_chamar_fonte(self):
        with patch("relatorios.services.consultar_frequencia_mensal") as fonte:
            with self.assertRaises(ValidationError):
                self.consultar(mes=13)
            self.usuario.groups.clear()
            with self.assertRaises(PermissionDenied):
                self.consultar()
            fonte.assert_not_called()

    def test_integracao_indisponivel_nao_produz_indicadores(self):
        with patch("relatorios.services.consultar_frequencia_mensal", side_effect=ImproperlyConfigured):
            resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertEqual(resposta.status_code, 503)
        self.assertContains(resposta, "A integração de participantes está indisponível", status_code=503)
        self.assertNotContains(resposta, "<table", status_code=503)

    @override_settings(DEBUG=True,
        NCI_PARTICIPANTES_PROVIDER="atividades.integracoes.participantes_placeholder.ProvedorPlaceholder")
    def test_demonstracao_nao_e_publicada_como_fmr(self):
        self.lancar(date(2024, 2, 1))
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertEqual(resposta.context["indicadores"], [])
        self.assertContains(resposta, "dados de demonstração não são utilizados no FMR")
        self.assertNotContains(resposta, 'id="tabela-indicadores-fmr"')

    def test_mes_invalido_nao_consulta_fonte(self):
        with patch("relatorios.services.consultar_frequencia_mensal") as fonte:
            resposta = self.client.get(self.url, {"mes": "2024-13"})
        self.assertTrue(resposta.context["form"].errors)
        self.assertNotContains(resposta, 'id="indicadores-disponiveis"')
        fonte.assert_not_called()
