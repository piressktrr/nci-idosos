from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from core.integracoes import ParticipanteResumo
from participantes.consultas import PermanentesComPendencias
from participantes.models import Movimentacao
from participantes.tests.test_models import criar_participante
from relatorios.services import consultar_permanentes_fmr


FONTE = "relatorios.services.integracao_participantes.consultar_permanentes_na_data"


class PermanentesFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="permanentes_fmr_ficticio")
        cls.grupo, _ = Group.objects.get_or_create(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.permissao = Permission.objects.get(content_type__app_label="participantes", codename="view_participante")
        cls.usuario.user_permissions.add(cls.permissao)
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def consultar(self, **kwargs):
        return consultar_permanentes_fmr(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | kwargs))

    @patch(FONTE, return_value=None)
    def test_integracao_pendente_nao_vira_lista_vazia_ou_total_zero(self, _fonte):
        resultado = self.consultar()
        self.assertEqual(resultado["data_referencia"], date(2024, 2, 29))
        self.assertIsNone(resultado["total"])
        self.assertIsNone(resultado["participantes"])
        self.assertEqual(resultado["pendencia"]["codigo"], "CONTRATO-PERMANENCIA")

    def test_estrutura_usa_ultimo_dia_do_mes_inclusive_limites(self):
        for ano, mes, ultimo in ((2023, 2, 28), (2024, 2, 29), (2024, 4, 30), (1, 1, 31), (9999, 12, 31)):
            with self.subTest(ano=ano, mes=mes), patch(FONTE, return_value=None) as fonte:
                resultado = self.consultar(ano=ano, mes=mes)
                referencia = date(ano, mes, ultimo)
                self.assertEqual(resultado["data_referencia"], referencia)
                fonte.assert_called_once_with(usuario=self.usuario, data_referencia=referencia)

    @patch(FONTE, return_value=None)
    def test_consulta_pendente_nao_le_cadastros_status_presencas_ou_historicos(self, _fonte):
        with CaptureQueriesContext(connection) as consultas:
            self.consultar()
        for consulta in consultas:
            sql = consulta["sql"].upper()
            self.assertTrue(sql.startswith("SELECT"), sql)
            self.assertNotRegex(sql, r'(?:FROM|JOIN) "(?:PARTICIPANTES|ATIVIDADES)_')

    @patch(FONTE, return_value=None)
    def test_interface_avisa_falta_de_integracao_com_explicacao_sem_numeros(self, _fonte):
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Participantes que permanecem no serviço")
        self.assertContains(resposta, "29/02/2024")
        self.assertContains(resposta, "Faltam informações históricas")
        self.assertContains(resposta, 'title="Precisamos que o módulo de participantes')
        self.assertContains(resposta, 'aria-describedby="explicacao-permanentes-pendentes"')
        self.assertNotContains(resposta, "Total de participantes que permanecem:")
        self.assertNotContains(resposta, "Nenhum participante permanece")

    def test_estrutura_pronta_para_consumir_consulta_futura_sem_simular_na_interface_real(self):
        pessoas = (ParticipanteResumo("ref-ficticia", "Participante <script>fictício</script>"),)
        with patch(FONTE, return_value=PermanentesComPendencias(pessoas, ())):
            resultado = self.consultar()
            resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertIsNone(resultado["pendencia"])
        self.assertEqual(resultado["participantes"], pessoas)
        self.assertEqual(resultado["total"], 1)
        self.assertContains(resposta, "Participante &lt;script&gt;fictício&lt;/script&gt;")
        self.assertNotContains(resposta, "Participante <script>fictício</script>")
        self.assertContains(resposta, "Total de participantes que permanecem:</strong> 1")

    def test_resultado_vazio_valido_distinto_de_integracao_pendente(self):
        with patch(FONTE, return_value=PermanentesComPendencias((), ())):
            resultado = self.consultar()
            resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertIsNone(resultado["pendencia"])
        self.assertEqual(resultado["total"], 0)
        self.assertEqual(resultado["participantes"], ())
        self.assertContains(resposta, "Nenhum participante permanece no serviço nesta data.")
        self.assertNotContains(resposta, "Faltam informações históricas")

    def test_sem_permissao_de_participantes_nao_chama_integracao(self):
        self.consultar()
        self.usuario.user_permissions.clear()
        self.grupo.permissions.remove(self.permissao)
        with patch(FONTE) as fonte:
            resultado = self.consultar()
            resposta = self.client.get(self.url)
            fonte.assert_not_called()
        self.assertIsNone(resultado["total"])
        self.assertIsNone(resultado["participantes"])
        self.assertIsNone(resultado["pendencia"])
        self.assertContains(resposta, "Seu perfil não possui permissão para consultar os participantes")

    def test_sem_perfil_ou_conta_inativa_nao_chama_integracao(self):
        self.usuario.groups.clear()
        with patch(FONTE) as fonte:
            with self.assertRaises(PermissionDenied):
                self.consultar()
            with self.assertRaises(PermissionDenied):
                self.consultar(usuario=AnonymousUser())
            self.usuario.groups.add(self.grupo)
            get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
            with self.assertRaises(PermissionDenied):
                self.consultar()
            fonte.assert_not_called()

    def test_mes_invalido_nao_chama_integracao_nem_exibe_secao(self):
        with patch(FONTE) as fonte:
            for ano, mes in ((0, 2), (10000, 1), (2024, 0), (2024, 13), (True, 1), (2024, False)):
                with self.subTest(ano=ano, mes=mes), self.assertRaises(ValidationError):
                    self.consultar(ano=ano, mes=mes)
            resposta = self.client.get(self.url, {"mes": "invalido"})
            fonte.assert_not_called()
        self.assertNotContains(resposta, 'id="participantes-permanecem"')

    @patch(FONTE, return_value=None)
    def test_pendencia_independe_das_permissoes_de_frequencia_e_nao_grava(self, _fonte):
        with CaptureQueriesContext(connection) as consultas:
            resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Seu perfil não possui as permissões para consultar os indicadores de frequência")
        self.assertContains(resposta, "Faltam informações históricas")
        for consulta in consultas:
            self.assertTrue(consulta["sql"].upper().startswith("SELECT"), consulta["sql"])
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class PermanentesComCadastrosPendentesTests(TestCase):
    """RN-FMR-12: cadastros sem entrada, Inativos ou Cancelados ficam fora do total, listados, sem anular o mês."""

    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="pendentes_fmr_ficticio")
        cls.usuario.groups.add(Group.objects.get(name="Equipe"))
        cls.url = reverse("relatorios:fmr")
        cls.ana = criar_participante(nome_completo="Ana Fictícia Completa")
        Movimentacao.objects.create(participante=cls.ana, usuario=cls.usuario, tipo="entrada", data=date(2024, 1, 2))
        cls.bia = criar_participante(nome_completo="Bia Fictícia Sem Entrada")
        cls.caio = criar_participante(nome_completo="Caio Fictício Inativo", status="inativo")
        Movimentacao.objects.create(participante=cls.caio, usuario=cls.usuario, tipo="entrada", data=date(2024, 1, 2))
        cls.dora = criar_participante(nome_completo="Dora Fictícia Cancelada Sem Entrada", status="cancelado")

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_total_dos_completos_com_lista_e_motivos_dos_pendentes(self):
        resultado = consultar_permanentes_fmr(usuario=self.usuario, ano=2024, mes=2)
        self.assertIsNone(resultado["pendencia"])
        self.assertEqual(resultado["total"], 1)
        self.assertEqual([p.nome for p in resultado["participantes"]], ["Ana Fictícia Completa"])
        self.assertEqual([(p["nome"], p["motivo"]) for p in resultado["cadastros_pendentes"]], [
            ("Bia Fictícia Sem Entrada", "sem entrada"),
            ("Caio Fictício Inativo", "status Inativo"),
            ("Dora Fictícia Cancelada Sem Entrada", "sem entrada; status Cancelado"),
        ])
        self.assertEqual(resultado["motivos_pendentes"], [
            {"motivo": "sem entrada", "quantidade": 2}, {"motivo": "status Cancelado", "quantidade": 1},
            {"motivo": "status Inativo", "quantidade": 1}])
        self.assertEqual([p["codigo"] for p in resultado["pendencias"]], ["CADASTROS-PENDENTES"])

    def test_status_nao_e_convertido(self):
        consultar_permanentes_fmr(usuario=self.usuario, ano=2024, mes=2)
        self.client.get(self.url, {"mes": "2024-02"})
        self.caio.refresh_from_db()
        self.dora.refresh_from_db()
        self.assertEqual((self.caio.status, self.dora.status), ("inativo", "cancelado"))

    def test_tela_mostra_total_aviso_e_lista_nominal(self):
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, "Total de participantes que permanecem:</strong> 1")
        self.assertContains(resposta, "3 cadastro(s) fora do cálculo deste FMR")
        self.assertContains(resposta, "Todos os totais desta página excluem esses cadastros")
        self.assertContains(resposta, "<tr><td>Caio Fictício Inativo</td><td>Status Inativo</td></tr>", html=True)
        self.assertContains(resposta, "O total exclui 3 cadastro(s) fora do cálculo")
        self.assertNotContains(resposta, "Faltam informações históricas")

    def test_transcricao_mostra_contagem_por_motivo_sem_nomes(self):
        resposta = self.client.get(self.url, {"mes": "2024-02", "modo": "transcricao"})
        self.assertContains(resposta, "3 cadastro(s) fora do cálculo deste FMR")
        self.assertContains(resposta, "<li>Sem entrada: 2</li>", html=True)
        self.assertContains(resposta, "<li>Status Inativo: 1</li>", html=True)
        self.assertContains(resposta, "(exclui 3 cadastro(s) fora do cálculo)")
        for nome in ("Bia Fictícia", "Caio Fictício", "Dora Fictícia", "Ana Fictícia"):
            self.assertNotContains(resposta, nome)

    def test_sem_pendentes_nao_mostra_aviso(self):
        type(self.ana).objects.exclude(pk=self.ana.pk).update(status="ativo")
        for pessoa in (self.bia, self.dora):
            Movimentacao.objects.create(participante=pessoa, usuario=self.usuario, tipo="entrada", data=date(2024, 3, 1))
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertNotContains(resposta, 'id="cadastros-conferir"')
        self.assertEqual(resposta.context["permanentes"]["total"], 2)
