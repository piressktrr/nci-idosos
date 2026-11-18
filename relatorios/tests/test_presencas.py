from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from atividades.consultas_fmr import consultar_presencas_mensais
from atividades.models import Atividade, Aula, Frequencia, Inscricao
from relatorios.services import consultar_presencas_fmr


@override_settings(NCI_PARTICIPANTES_PROVIDER="participantes.provedor.ProvedorParticipantes")
class PresencasFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="presencas_fmr_ficticio")
        grupo, _ = Group.objects.get_or_create(name="Equipe")
        cls.usuario.groups.add(grupo)
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("view_atividade", "view_aula", "view_frequencia")))
        cls.atividade = Atividade.objects.create(nome="Oficina fictícia A", local="Sala", monitor="Teste")
        cls.outra = Atividade.objects.create(nome="Oficina fictícia B", local="Sala", monitor="Teste")
        cls.pessoa = cls.inscrever(cls.atividade, "ficticio-a")
        cls.mesma_pessoa = cls.inscrever(cls.outra, "ficticio-a")
        cls.outra_pessoa = cls.inscrever(cls.atividade, "ficticio-b")
        cls.url = reverse("relatorios:fmr")

    @classmethod
    def inscrever(cls, atividade, referencia, origem="participantes"):
        return Inscricao.objects.create(atividade=atividade, origem_participante=origem,
            participante_referencia=referencia, cadastrada_por=cls.usuario)

    def criar_aula(self, data, atividade=None, cancelada=False):
        return Aula.objects.create(atividade=atividade or self.atividade, data=data, inicio=time(9), fim=time(10),
            situacao="cancelada" if cancelada else "realizada")

    def lancar(self, data, inscricao=None, situacao="presente", cancelada=False):
        inscricao = inscricao or self.pessoa
        aula = self.criar_aula(data, inscricao.atividade, cancelada)
        return Frequencia.objects.create(aula=aula, inscricao=inscricao, situacao=situacao)

    def consultar(self, **kwargs):
        return consultar_presencas_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | kwargs))

    def test_identidade_compartilhada_entre_atividades_dias_e_multiplas_pessoas(self):
        primeira = self.lancar(date(2024, 2, 1))
        self.lancar(date(2024, 2, 1), self.mesma_pessoa)
        Frequencia.objects.create(aula=primeira.aula, inscricao=self.outra_pessoa, situacao="presente")
        self.lancar(date(2024, 2, 29))
        resultado = self.consultar()
        self.assertEqual(resultado["dias"], [
            {"data": date(2024, 2, 1), "ocorrencias": 3, "participantes_unicos": 2},
            {"data": date(2024, 2, 29), "ocorrencias": 1, "participantes_unicos": 1}])
        self.assertEqual(resultado["total_ocorrencias"], 4)
        self.assertEqual(resultado["total_participantes_unicos"], 2)
        self.assertEqual(resultado["criterio"], "ocorrencias")

    def test_data_de_ocorrencia_limites_bissexto_canceladas_e_ausencias(self):
        for dia in (date(2024, 1, 31), date(2024, 3, 1)):
            self.lancar(dia)
        self.lancar(date(2024, 2, 1), cancelada=True)
        self.lancar(date(2024, 2, 2), situacao="ausente")
        self.lancar(date(2024, 2, 3), situacao="ausente_justificado")
        self.criar_aula(date(2024, 2, 4))
        self.lancar(date(2024, 2, 29))
        resultado = self.consultar()
        self.assertEqual([dia["data"].day for dia in resultado["dias"]], [2, 3, 4, 29])
        self.assertEqual([dia["ocorrencias"] for dia in resultado["dias"]], [0, 0, 0, 1])
        self.assertEqual(resultado["total_participantes_unicos"], 1)

    def test_mes_sem_aulas_e_anos_extremos_sem_inventar_media(self):
        for ano, mes in ((2024, 2), (1, 1), (9999, 12)):
            with self.subTest(ano=ano, mes=mes):
                resultado = self.consultar(ano=ano, mes=mes)
                self.assertEqual(resultado["dias"], [])
                self.assertEqual(resultado["total_ocorrencias"], 0)
                self.assertEqual(resultado["total_participantes_unicos"], 0)
                self.assertIsNone(resultado["media_diaria"])

    def test_origem_do_provedor_separa_frequencias_de_demonstracao(self):
        demo = self.inscrever(self.atividade, "ficticio-a", origem="placeholder")
        self.lancar(date(2024, 2, 1), demo)
        self.assertEqual(self.consultar()["total_ocorrencias"], 0)
        self.lancar(date(2024, 2, 1))
        self.assertEqual(self.consultar()["total_participantes_unicos"], 1)

    def test_correcao_e_cancelamento_posteriores_refletidos(self):
        frequencia = self.lancar(date(2024, 2, 1))
        self.assertEqual(self.consultar()["total_ocorrencias"], 1)
        Frequencia.objects.filter(pk=frequencia.pk).update(situacao="ausente")
        self.assertEqual(self.consultar()["total_participantes_unicos"], 0)
        Aula.objects.filter(pk=frequencia.aula_id).update(situacao="cancelada")
        self.assertEqual(self.consultar()["dias"], [])

    def test_fonte_e_servico_rejeitam_parametros_invalidos(self):
        for ano, mes in ((True, 2), (2024, False), (0, 1), (10000, 1), (2024, 13), (2024, 0), ("2024", 2)):
            for servico in (consultar_presencas_mensais, consultar_presencas_fmr):
                with self.subTest(servico=servico, ano=ano, mes=mes), self.assertRaises(ValidationError):
                    servico(usuario=self.usuario, ano=ano, mes=mes)

    def test_permissoes_atuais_conta_desativada_e_login(self):
        self.consultar()
        for codename in ("view_atividade", "view_aula", "view_frequencia"):
            permissao = Permission.objects.get(content_type__app_label="atividades", codename=codename)
            self.usuario.user_permissions.remove(permissao)
            with self.assertRaises(PermissionDenied):
                self.consultar()
            self.usuario.user_permissions.add(permissao)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.consultar()
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())

    def test_perfil_fmr_exigido_antes_da_fonte(self):
        self.usuario.groups.clear()
        with patch("relatorios.services.consultar_presencas_mensais") as fonte:
            with self.assertRaises(PermissionDenied):
                self.consultar()
            fonte.assert_not_called()

    @override_settings(NCI_FMR_CONTAGEM_DIARIA="participantes_unicos")
    def test_contagem_configuravel_sem_misturar_medidas(self):
        self.lancar(date(2024, 2, 1))
        self.lancar(date(2024, 2, 1), self.mesma_pessoa)
        resultado = self.consultar()
        self.assertEqual(resultado["criterio"], "participantes_unicos")
        self.assertEqual(resultado["dias"][0]["ocorrencias"], 2)
        self.assertEqual(resultado["dias"][0]["participantes_unicos"], 1)
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "participantes únicos")
        html = resposta.content.decode()
        self.assertLess(html.index('scope="col">Participantes únicos no dia'),
                        html.index('scope="col">Ocorrências de presença'))

    def test_configuracao_invalida_e_demonstracao_nao_geram_indicadores(self):
        with override_settings(NCI_FMR_CONTAGEM_DIARIA="invalida"), self.assertRaises(ImproperlyConfigured):
            self.consultar()
        with override_settings(DEBUG=True,
            NCI_PARTICIPANTES_PROVIDER="atividades.integracoes.participantes_placeholder.ProvedorPlaceholder"):
            with self.assertRaises(ImproperlyConfigured):
                self.consultar()
            self.client.force_login(self.usuario)
            resposta = self.client.get(self.url)
            self.assertNotContains(resposta, 'id="presencas-por-data"')

    def test_interface_totais_datas_media_pendente_e_consulta_somente_leitura(self):
        self.lancar(date(2024, 2, 29))
        self.client.force_login(self.usuario)
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Presenças por data")
        self.assertContains(resposta, "29/02/2024")
        self.assertContains(resposta, "Total mensal de ocorrências:</strong> 1", html=False)
        self.assertContains(resposta, "Participantes únicos no mês:</strong> 1", html=False)
        self.assertContains(resposta, "Falta informação para calcular a média diária.")
        self.assertContains(resposta, 'title="Precisamos que o NCI defina')
        self.assertContains(resposta, 'aria-describedby="explicacao-media-pendente"')
        self.assertContains(resposta, "incluindo o tratamento de feriados e dias sem aulas")
        self.assertIsNone(resposta.context["presencas"]["media_diaria"])
        for consulta in consultas:
            self.assertTrue(consulta["sql"].upper().startswith("SELECT"), consulta["sql"])

    def test_interface_sem_aulas_preserva_mes_e_restringe_consulta(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Nenhuma aula realizada registrada neste mês")
        self.assertContains(resposta, 'value="2024-02"')
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.usuario.user_permissions.clear()
        self.assertNotContains(self.client.get(self.url), 'id="presencas-por-data"')
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
