from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from participantes.services import cadastrar_participante
from participantes.tests.test_models import dados_participante

class TranscricaoFMRTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="transcricao_ficticia")
        cls.usuario.groups.add(Group.objects.get(name="Equipe"))
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("view_atividade", "view_aula", "view_frequencia")))

    def setUp(self):
        self.client.force_login(self.usuario)
        self.url = reverse("relatorios:fmr")
        self.parametros = {"mes": "2024-02", "modo": "transcricao"}

    def test_abertura_retorno_mes_bissexto_e_campos_pendentes(self):
        self.assertContains(self.client.get(self.url, {"mes": "2024-02"}), "?mes=2024-02&amp;modo=transcricao")
        resposta = self.client.get(self.url, self.parametros)
        self.assertContains(resposta, 'href="?mes=2024-02"')
        self.assertContains(resposta, 'name="modo" value="transcricao"')
        self.assertContains(resposta, '<tr><th scope="row">29/02/2024</th><td>0</td></tr>', html=True)
        # Média sobre os 21 dias úteis de fev/2024 (P06), não mais "sem dias com atendimento".
        self.assertContains(resposta, "Dias de funcionamento (dias úteis, segunda a sexta)")
        self.assertContains(resposta, "Feriados não são descontados")
        self.assertContains(resposta, "<dt>Média diária</dt><dd>0</dd>", html=True)
        # RF-FMR-13 (Q4): valor a lançar no portal, com reativados somados aos ingressos.
        self.assertContains(resposta, "Ingressaram (portal)")
        self.assertContains(resposta, 'id="nota-ingressaram-portal"')
        self.assertContains(resposta, 'id="tabela-campos-indisponiveis"')
        self.assertContains(resposta, 'id="tabela-movimentacao-etaria"')

    def test_contagem_adotada_mensal_unico_e_alerta_sem_lista_nominal(self):
        frequencia = {"dias": [{"data": date(2024, 2, 2), "ocorrencias": 2, "participantes_unicos": 1}],
                      "total_participantes_unicos": 1, "total_ocorrencias": 2, "demonstracao": False}
        cadastrar_participante(usuario=self.usuario, data_entrada=date(2024, 2, 1),
            **dados_participante(nome_completo="Nome fictício privado", telefone_residencial="",
                                observacao_encaminhamento=""))
        with patch("relatorios.services.consultar_presencas_mensais", return_value=frequencia):
            resposta = self.client.get(self.url, self.parametros)
            self.assertContains(resposta, '<tr><th scope="row">02/02/2024</th><td>2</td></tr>', html=True)
            self.assertContains(resposta, "Pessoas atendidas no mês de referência (indivíduos)</dt><dd>1")
            self.assertContains(resposta, 'id="avisos-consistencia"')
            self.assertNotContains(resposta, "Nome fictício privado")
            with override_settings(NCI_FMR_CONTAGEM_DIARIA="participantes_unicos"):
                resposta = self.client.get(self.url, self.parametros)
            self.assertContains(resposta, '<tr><th scope="row">02/02/2024</th><td>1</td></tr>', html=True)
            self.assertNotContains(resposta, 'id="avisos-consistencia"')

    def test_mes_invalido_e_controles_de_acesso(self):
        resposta = self.client.get(self.url, self.parametros | {"mes": "2024-13"})
        self.assertNotContains(resposta, 'id="presencas-por-data"')
        self.usuario.user_permissions.clear()
        resposta = self.client.get(self.url, self.parametros)
        self.assertContains(resposta, "Seu perfil não possui as permissões")
        self.assertNotContains(resposta, "Total no mês (soma das contagens diárias)")
        self.usuario.groups.clear()
        self.assertEqual(self.client.get(self.url, self.parametros).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(self.url, self.parametros).status_code, 302)
