from copy import deepcopy
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from participantes.tests.test_models import novo_participante
from relatorios.cobertura import identificar_campos_indisponiveis
from relatorios.services import consultar_indicadores_fmr


class CoberturaRegrasTests(SimpleTestCase):
    def test_zeros_reais_nao_sao_informacoes_ausentes(self):
        dados = {"permanentes": {"total": 0}, "situacao_social": {"linhas": [{"quantidade": 0}]},
                 "presencas": {"media_diaria": Decimal(0)}}
        campos = identificar_campos_indisponiveis(dados)
        self.assertEqual(len(campos), 3)
        self.assertTrue(all(campo["situacao"] == "Fora do MVP" for campo in campos))

    def test_reune_pendencias_sem_modificar_dados_ou_preencher_numeros(self):
        pendencia = {"aviso": "Informação ausente", "explicacao": "Histórico necessário"}
        dados = {"permanentes": {"total": None, "pendencia": pendencia},
                 "movimentacao_etaria": {"pendencias": [pendencia]},
                 "perfil_demografico": {"blocos_pendentes": [{"titulo": "Raça/cor", **pendencia}],
                                         "pendencia_imigrantes": pendencia}}
        anterior = deepcopy(dados)
        campos = identificar_campos_indisponiveis(dados)
        self.assertEqual(dados, anterior)
        self.assertEqual([c["campo"] for c in campos[:4]], ["Participantes que permanecem no serviço",
                         "Movimentação por faixa etária e sexo", "Raça/cor", "Imigrantes/refugiados"])
        self.assertTrue(all(c["explicacao"] == "Histórico necessário" for c in campos[:4]))
        self.assertTrue(all("valor" not in c for c in campos))

    def test_acesso_restrito_nao_e_rotulado_como_dado_ausente(self):
        campos = identificar_campos_indisponiveis({"aviso": "Sem acesso à frequência",
            "perfil_demografico": {"aviso": "Sem acesso ao cadastro", "blocos_pendentes": [{"titulo": "Não expor"}]}})
        self.assertEqual([c["situacao"] for c in campos[:2]], ["Indisponível nesta consulta"] * 2)
        self.assertNotIn("Não expor", str(campos))

    def test_media_sem_divisor_diferente_de_zero_e_html_escapado(self):
        campos = identificar_campos_indisponiveis({"presencas": {"media_diaria": None}})
        self.assertEqual(campos[0]["campo"], "Média diária")
        self.assertEqual(campos[0]["situacao"], "Sem base para cálculo")
        campos[0]["motivo"] = "<script>fictício</script>"
        html = render_to_string("relatorios/_campos_indisponiveis.html", {"campos_indisponiveis": campos})
        self.assertIn("&lt;script&gt;fictício&lt;/script&gt;", html)
        self.assertNotIn("<script>fictício</script>", html)
        self.assertIn('tabindex="0"', html)
        self.assertIn('aria-describedby="campo-fmr-explicacao-1"', html)


class CoberturaFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="cobertura_fmr_ficticio")
        cls.grupo = Group.objects.get(name="Equipe")
        cls.usuario.groups.add(cls.grupo)
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("view_atividade", "view_aula", "view_frequencia")))
        cls.url = reverse("relatorios:fmr")

    def setUp(self):
        self.client.force_login(self.usuario)

    def test_resumo_integra_pendencias_reais_e_fora_mvp_sem_escrita(self):
        with CaptureQueriesContext(connection) as consultas:
            dados = consultar_indicadores_fmr(usuario=self.usuario, ano=2024, mes=2)
        self.assertTrue(all(q["sql"].upper().startswith("SELECT") for q in consultas))
        campos = {c["campo"]: c for c in dados["campos_indisponiveis"]}
        self.assertNotIn("Sexo por raça/cor", campos)
        self.assertNotIn("Identidade de gênero", campos)
        self.assertIn("Região de moradia", campos)
        self.assertIn("Atendimento domiciliar e indicadores do segundo bloco do FMR", campos)
        self.assertNotIn("Situação social dos participantes", campos)
        self.assertEqual(dados["permanentes"]["total"], 0)
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'id="tabela-campos-indisponiveis"')
        self.assertContains(resposta, "Fora do MVP")
        self.assertContains(resposta, "diferente de informação ausente")

    def test_dados_incompletos_aparecem_com_motivo_no_resumo(self):
        pessoa = novo_participante()
        pessoa.save()
        dados = consultar_indicadores_fmr(usuario=self.usuario, ano=2024, mes=2)
        campos = {c["campo"]: c for c in dados["campos_indisponiveis"]}
        self.assertEqual(campos["Participantes que permanecem no serviço"]["situacao"], "Aguardando dados ou definição")
        self.assertIn("fora do cálculo", campos["Participantes que permanecem no serviço"]["motivo"])
        # Antes, o cadastro sem entrada anulava também a situação social; agora ela é calculada com os completos.
        self.assertNotIn("Situação social dos participantes", campos)
        self.assertEqual(dados["permanentes"]["total"], 0)

    def test_aulas_sem_categoria_aparecem_como_pendentes_no_resumo(self):
        from datetime import date, time

        from atividades.models import Atividade, Aula
        atividade = Atividade.objects.create(nome="Oficina fictícia sem categoria", monitor="Equipe", local="Sala")
        Aula.objects.create(atividade=atividade, data=date(2024, 2, 5), inicio=time(9), fim=time(10))
        dados = consultar_indicadores_fmr(usuario=self.usuario, ano=2024, mes=2)
        campos = {c["campo"]: c for c in dados["campos_indisponiveis"]}
        self.assertEqual(campos["Atividades e participações por categoria"]["situacao"], "Aguardando dados ou definição")
        self.assertIn("sem categoria", campos["Atividades e participações por categoria"]["motivo"])

    def test_resumo_preservado_quando_frequencia_nao_pode_ser_consultada(self):
        self.usuario.user_permissions.clear()
        self.grupo.permissions.remove(*Permission.objects.filter(content_type__app_label="atividades"))
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertContains(resposta, 'id="tabela-campos-indisponiveis"')
        self.assertContains(resposta, "Indisponível nesta consulta")
        self.assertContains(resposta, "Aulas, participações e presenças")

    def test_login_perfil_get_e_mes_valido_exigidos(self):
        resposta = self.client.get(self.url, {"mes": "2024-13"})
        self.assertNotContains(resposta, 'id="tabela-campos-indisponiveis"')
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.usuario.groups.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url).status_code, 302)
