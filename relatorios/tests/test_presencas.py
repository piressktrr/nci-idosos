from datetime import date, time
from decimal import Decimal
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
    def test_media_exemplo_1579_em_20_dias_uteis_e_arredondamento_na_tela(self):
        # Fevereiro/2023 tem exatamente 20 dias úteis (P06: dias úteis do calendário).
        dias_uteis = [dia for dia in range(1, 29) if date(2023, 2, dia).weekday() < 5]
        dados = {"dias": [{"data": date(2023, 2, n), "ocorrencias": 79 if i < 19 else 78,
                            "participantes_unicos": 1} for i, n in enumerate(dias_uteis)],
                 "total_ocorrencias": 1579, "total_participantes_unicos": 1, "demonstracao": False}
        with patch("relatorios.services.consultar_presencas_mensais", return_value=dados):
            resultado = self.consultar(ano=2023)
            self.client.force_login(self.usuario)
            resposta = self.client.get(self.url, {"mes": "2023-02"})
        self.assertEqual(resultado["media_diaria"], Decimal("78.95"))
        self.assertEqual(resultado["dias_funcionamento"], 20)
        self.assertEqual(len(resultado["dias"]), 28)
        self.assertContains(resposta, "Média diária:</strong> 79")
        self.assertContains(resposta, "1579 ÷ 20 dias úteis")

    def test_dias_uteis_do_calendario_sem_feriados(self):
        from relatorios.services import dias_uteis
        # Fev/2024 (bissexto, começa na quinta): 21; fev/2023: 20; jun/2024 (começa no sábado): 20; jan/2025: 23.
        # Dez/2024: 22, sem descontar o feriado de 25/12 (o sistema não tem calendário de feriados).
        for ano, mes, esperado in ((2024, 2, 21), (2023, 2, 20), (2024, 6, 20), (2025, 1, 23), (2024, 12, 22)):
            with self.subTest(ano=ano, mes=mes):
                self.assertEqual(dias_uteis(ano, mes), esperado)
        # Sábado e domingo com presença não aumentam o divisor.
        self.lancar(date(2024, 2, 3))
        self.lancar(date(2024, 2, 4))
        resultado = self.consultar()
        self.assertEqual((resultado["dias_funcionamento"], resultado["dias_com_atendimento"]), (21, 2))
        self.assertEqual(resultado["media_diaria"], Decimal(2) / Decimal(21))

    def test_divisor_e_dias_uteis_independente_das_datas_com_presenca(self):
        self.lancar(date(2024, 2, 1))
        self.lancar(date(2024, 2, 1), self.mesma_pessoa)
        self.lancar(date(2024, 2, 2))
        self.lancar(date(2024, 2, 3), situacao="ausente")
        self.lancar(date(2024, 2, 4), situacao="ausente_justificado")
        self.lancar(date(2024, 2, 5), cancelada=True)
        self.criar_aula(date(2024, 2, 6))
        resultado = self.consultar()
        # Antes o divisor era o número de datas com presença (2); agora são os 21 dias úteis de fev/2024 (P06).
        self.assertEqual(resultado["dias_funcionamento"], 21)
        self.assertEqual(resultado["dias_com_atendimento"], 2)
        self.assertEqual(resultado["media_diaria"], Decimal(3) / Decimal(21))
        with override_settings(NCI_FMR_CONTAGEM_DIARIA="participantes_unicos"):
            resultado = self.consultar()
        self.assertEqual(resultado["total_contagem_diaria"], 2)
        self.assertEqual(resultado["media_diaria"], Decimal(2) / Decimal(21))

    def test_correcao_remove_ultimo_atendimento_e_media_vira_zero_real(self):
        frequencia = self.lancar(date(2024, 2, 1))
        self.assertEqual(self.consultar()["dias_com_atendimento"], 1)
        Frequencia.objects.filter(pk=frequencia.pk).update(situacao="ausente")
        resultado = self.consultar()
        self.assertEqual(resultado["dias_com_atendimento"], 0)
        self.assertEqual(resultado["dias_funcionamento"], 21)
        self.assertEqual(resultado["media_diaria"], 0)

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
        self.assertEqual([dia for dia in resultado["dias"] if dia["ocorrencias"]], [
            {"data": date(2024, 2, 1), "ocorrencias": 3, "participantes_unicos": 2},
            {"data": date(2024, 2, 29), "ocorrencias": 1, "participantes_unicos": 1}])
        self.assertEqual(resultado["total_ocorrencias"], 4)
        self.assertEqual(resultado["total_participantes_unicos"], 2)
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Total mensal de ocorrências:</strong> 4")
        self.assertContains(resposta, "Pessoas atendidas no mês de referência (indivíduos):</strong> 2")
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
        self.assertEqual(len(resultado["dias"]), 29)
        self.assertEqual([dia["ocorrencias"] for dia in resultado["dias"]], [0] * 28 + [1])
        self.assertEqual(resultado["total_participantes_unicos"], 1)

    def test_mes_sem_aulas_e_anos_extremos_media_zero_sobre_dias_uteis(self):
        for ano, mes, uteis in ((2024, 2, 21), (1, 1, 23), (9999, 12, 23)):
            with self.subTest(ano=ano, mes=mes):
                resultado = self.consultar(ano=ano, mes=mes)
                self.assertTrue(all(dia["ocorrencias"] == 0 for dia in resultado["dias"]))
                self.assertEqual(resultado["dias_funcionamento"], uteis)
                self.assertEqual(resultado["dias_com_atendimento"], 0)
                self.assertEqual(resultado["total_ocorrencias"], 0)
                self.assertEqual(resultado["total_participantes_unicos"], 0)
                self.assertEqual(resultado["media_diaria"], 0)

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
        self.assertEqual(self.consultar()["dias_com_atendimento"], 0)

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

    def test_interface_totais_datas_media_e_consulta_somente_leitura(self):
        self.lancar(date(2024, 2, 29))
        self.client.force_login(self.usuario)
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Presenças por data")
        self.assertContains(resposta, "29/02/2024")
        self.assertContains(resposta, "Total mensal de ocorrências:</strong> 1", html=False)
        self.assertContains(resposta, "Pessoas atendidas no mês de referência (indivíduos):</strong> 1", html=False)
        self.assertContains(resposta, "Dias de funcionamento:</strong> 21")
        self.assertContains(resposta, "dias úteis do calendário do mês, de segunda a sexta")
        self.assertContains(resposta, "Feriados não são descontados")
        self.assertContains(resposta, "Média diária:</strong> 0")
        self.assertNotContains(resposta, "Falta informação para calcular")
        self.assertEqual(resposta.context["presencas"]["media_diaria"], Decimal(1) / Decimal(21))
        for consulta in consultas:
            self.assertTrue(consulta["sql"].upper().startswith("SELECT"), consulta["sql"])

    def test_interface_sem_aulas_preserva_mes_e_restringe_consulta(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Nenhum atendimento registrado neste mês")
        self.assertContains(resposta, 'value="2024-02"')
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.usuario.user_permissions.clear()
        self.assertNotContains(self.client.get(self.url), 'id="presencas-por-data"')
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
