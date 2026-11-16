from datetime import date, datetime, time, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse

from atividades.models import Atividade, Aula, HorarioAtividade


class SugestoesAulaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="sugestoes_ficticias")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=(
                "view_atividade", "view_aula", "add_aula", "view_horarioatividade"
            )
        ))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala de teste", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra fictícia", local="Sala de teste", monitor="Fictício")
        cls.url = reverse("atividades:aulas", args=[cls.atividade.pk])

    def setUp(self):
        self.client.force_login(self.usuario)
        # Domingo em UTC, ainda sábado no fuso configurado do NCI.
        self.relogio = patch("atividades.forms.timezone.now", return_value=datetime(2026, 11, 8, 1, 30, 45, tzinfo=timezone.utc))
        self.relogio.start()
        self.addCleanup(self.relogio.stop)

    def horario(self, atividade=None, **dados):
        return HorarioAtividade.objects.create(atividade=atividade or self.atividade, **(
            {"dia_semana": 5, "inicio": time(14), "fim": time(15)} | dados
        ))

    def test_sugere_hoje_e_termino_agora_no_fuso_local(self):
        form = self.client.get(self.url).context["form"]
        self.assertEqual(form.initial["data"], date(2026, 11, 7))
        self.assertEqual(form.initial["fim"], time(22, 30))
        self.assertEqual(form.initial["tipo"], "regular")
        self.assertFalse(form.initial.get("inicio"))

    def test_regular_com_horario_unico_deduz_inicio_e_termino(self):
        self.horario()
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.context["form"].initial["inicio"], time(14))
        self.assertEqual(resposta.context["form"].initial["fim"], time(15))
        self.assertEqual(resposta.context["form"].initial["data"], date(2026, 11, 7))
        self.assertContains(resposta, 'atividades/aulas.js')
        self.assertContains(resposta, 'id="sugestoes-aula"')

    def test_varios_horarios_do_dia_nao_escolhem_faixa_arbitrariamente(self):
        self.horario()
        self.horario(inicio=time(16), fim=time(17))
        resposta = self.client.get(self.url)
        self.assertFalse(resposta.context["form"].initial.get("inicio"))
        self.assertEqual(resposta.context["form"].initial["fim"], time(22, 30))
        self.assertEqual(len(resposta.context["sugestoes"]["horarios"]), 2)

    def test_dias_e_atividades_diferentes_nao_preenchem_horarios(self):
        self.horario(dia_semana=1)
        self.horario(atividade=self.outra)
        resposta = self.client.get(self.url)
        self.assertFalse(resposta.context["form"].initial.get("inicio"))
        self.assertEqual(resposta.context["form"].initial["fim"], time(22, 30))
        self.assertEqual([item["dia_semana"] for item in resposta.context["sugestoes"]["horarios"]], [1])

    def test_post_manual_e_persistido_sem_ser_sobrescrito_pela_grade(self):
        self.horario()
        dados = {"tipo": "regular", "data": "2024-02-29", "inicio": "10:12", "fim": "11:34"}
        self.assertEqual(self.client.post(self.url, dados).status_code, 302)
        aula = Aula.objects.get()
        self.assertEqual(aula.data, date(2024, 2, 29))
        self.assertEqual(aula.inicio, time(10, 12))
        self.assertEqual(aula.fim, time(11, 34))
        self.assertEqual(aula.registro_realizacao.dados["fim"], "11:34:00")

    def test_post_invalido_preserva_campos_digitados_inclusive_campos_vazios(self):
        self.horario()
        dados = {"tipo": "extra", "data": "", "inicio": "16:31", "fim": "17:32"}
        resposta = self.client.post(self.url, dados)
        form = resposta.context["form"]
        self.assertTrue(form.is_bound)
        for campo, valor in dados.items():
            self.assertEqual(form[campo].value(), valor)
        self.assertContains(resposta, 'data-bound="true"')
        self.assertFalse(Aula.objects.exists())

    def test_sugestoes_nao_expoem_grade_sem_permissao_de_consulta(self):
        self.horario()
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="view_horarioatividade"
        ))
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.context["sugestoes"]["horarios"], [])
        self.assertFalse(resposta.context["form"].initial.get("inicio"))

    def test_somente_leitura_nao_recebe_formulario_ou_sugestoes(self):
        self.horario()
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="add_aula"
        ))
        resposta = self.client.get(self.url)
        self.assertNotContains(resposta, 'id="form-aula"')
        self.assertNotContains(resposta, 'id="sugestoes-aula"')
