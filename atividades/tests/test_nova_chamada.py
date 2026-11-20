from datetime import date, time
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, Client, override_settings
from django.urls import reverse
from atividades.models import Atividade, Aula, Inscricao, Frequencia, HorarioAtividade
from core.models import EventoAuditoria


@override_settings(DEBUG=True, NCI_PARTICIPANTES_PROVIDER="atividades.integracoes.participantes_placeholder.ProvedorPlaceholder")
class NovaChamadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="chamada_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades"))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala", monitor="Fictício")
        cls.inscricao = Inscricao.objects.create(atividade=cls.atividade, origem_participante="placeholder",
            participante_referencia="demo-1", cadastrada_por=cls.usuario)
        cls.url = reverse("atividades:registro_diario")

    def setUp(self):
        self.client.force_login(self.usuario)
        self.dados = {"atividade": self.atividade.pk, "tipo": "regular", "data": "2024-02-29",
            "inicio": "09:00", "fim": "10:00", f"registro_{self.inscricao.pk}": "presente"}

    def test_get_geral_e_preselecionado_sem_criar_aula(self):
        resposta = self.client.get(self.url)
        self.assertIsNone(resposta.context["atividade"])
        self.assertNotContains(resposta, "Ver aulas de")
        self.assertNotContains(resposta, "Confira a lista física assinada")
        resposta = self.client.get(self.url, {"atividade": self.atividade.pk})
        html = resposta.content.decode()
        self.assertLess(html.index("Ver aulas de"), html.index('id="escolher-atividade"'))
        self.assertLess(html.index("Confira a lista física assinada"), html.index('id="escolher-atividade"'))
        self.assertContains(resposta, f'name="registro_{self.inscricao.pk}"')
        self.assertContains(resposta, "Salvar chamada")
        self.assertFalse(Aula.objects.exists())

    def test_salva_aula_frequencias_e_auditorias_com_redirect(self):
        resposta = self.client.post(self.url, self.dados)
        aula = Aula.objects.get()
        self.assertRedirects(resposta, reverse("atividades:chamada", args=[self.atividade.pk, aula.pk]))
        self.assertEqual(Frequencia.objects.get().situacao, "presente")
        self.assertEqual(EventoAuditoria.objects.count(), 2)

    def test_erros_preservam_formulario_sem_aula_vazia(self):
        for dados in ({"fim": "08:00"}, {f"registro_{self.inscricao.pk}": "invalida"},
                      {f"registro_{self.inscricao.pk}": ""}, {"registro_999999": "presente"}):
            resposta = self.client.post(self.url, self.dados | dados)
            self.assertEqual(resposta.status_code, 200)
            self.assertFalse(Aula.objects.exists())
            self.assertFalse(Frequencia.objects.exists())

    def test_rollback_se_auditoria_de_frequencia_falhar(self):
        with patch("atividades.services.RegistroLancamentoFrequencia.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.client.post(self.url, self.dados)
        self.assertFalse(Aula.objects.exists())
        self.assertFalse(EventoAuditoria.objects.exists())

    def test_sem_inscritos_nao_cria_e_lista_nao_exibe_formulario_isolado(self):
        outra = Atividade.objects.create(nome="Outra", local="Sala", monitor="Fictício")
        resposta = self.client.post(self.url, self.dados | {"atividade": outra.pk})
        self.assertEqual(resposta.status_code, 200)
        self.assertFalse(Aula.objects.exists())
        resposta = self.client.get(reverse("atividades:aulas", args=[self.atividade.pk]))
        self.assertContains(resposta, self.url + "?atividade=" + str(self.atividade.pk))
        self.assertNotContains(resposta, 'id="form-aula"')

    def test_csrf_permissoes_e_sugestoes_de_hoje(self):
        hoje = date.today()
        HorarioAtividade.objects.create(atividade=self.atividade, dia_semana=hoje.weekday(), inicio=time(9), fim=time(10))
        resposta = self.client.get(self.url, {"atividade": self.atividade.pk})
        self.assertEqual(resposta.context["form_aula"].initial["inicio"], time(9))
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(self.url, self.dados).status_code, 403)
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="add_frequencia"))
        self.assertEqual(self.client.post(self.url, self.dados).status_code, 403)
        self.assertFalse(Aula.objects.exists())

    def test_inscricoes_novas_ou_outra_atividade_nao_geram_chamada_parcial(self):
        Inscricao.objects.create(atividade=self.atividade, origem_participante="placeholder",
            participante_referencia="demo-2", cadastrada_por=self.usuario)
        resposta = self.client.post(self.url, self.dados)
        self.assertContains(resposta, "Confira a situação de todos")
        self.assertFalse(Aula.objects.exists())

    def test_justificativa_e_horarios_extras_mantidos(self):
        resposta = self.client.post(self.url, self.dados | {"tipo": "extra", "inicio": "18:30", "fim": "19:15",
            f"registro_{self.inscricao.pk}": "ausente_justificado", f"observacao_{self.inscricao.pk}": "Fictícia"})
        self.assertEqual(resposta.status_code, 302)
        self.assertEqual(Aula.objects.get().inicio, time(18, 30))
        self.assertEqual(Frequencia.objects.get().observacao, "Fictícia")
