from datetime import time, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from atividades.models import Atividade, HorarioAtividade, RegistroGradeAtividade
from atividades.services import cadastrar_horario, alterar_horario


class GradeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="equipe_grade_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=(
                "view_atividade", "view_horarioatividade", "add_horarioatividade", "change_horarioatividade"
            )
        ))
        cls.atividade = Atividade.objects.create(nome="Atividade fictícia", local="Sala de teste", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra atividade fictícia", local="Outra sala", monitor="Fictício")
        cls.dados = {"dia_semana": 0, "inicio": time(9), "fim": time(10)}

    def cadastrar(self, **dados):
        return cadastrar_horario(usuario=self.usuario, atividade_id=self.atividade.pk, **(self.dados | dados))

    def alterar(self, horario, **dados):
        return alterar_horario(usuario=self.usuario, atividade_id=self.atividade.pk,
                              horario_id=horario.pk, **(self.dados | dados))

    def url(self, atividade=None):
        return reverse("atividades:grade", args=[(atividade or self.atividade).pk])

    def editar_url(self, horario, atividade=None):
        return reverse("atividades:editar_horario", args=[(atividade or self.atividade).pk, horario.pk])

    def test_cadastro_grava_grade_e_auditoria(self):
        horario = self.cadastrar()
        horario.refresh_from_db()
        self.assertEqual(horario.atividade_id, self.atividade.pk)
        self.assertEqual(horario.get_dia_semana_display(), "Segunda-feira")
        registro = horario.registros.get()
        self.assertEqual(registro.acao, "cadastro")
        self.assertEqual(registro.usuario_id, self.usuario.pk)
        self.assertIsNotNone(registro.registrado_em)
        self.assertIsNone(registro.dados_anteriores)
        self.assertEqual(registro.dados_novos, {"dia_semana": 0, "inicio": "09:00:00", "fim": "10:00:00"})

    def test_varios_horarios_por_dia_e_atividade(self):
        self.cadastrar()
        self.cadastrar(inicio=time(14), fim=time(15))
        self.cadastrar(dia_semana=6)
        self.assertEqual(self.atividade.horarios.count(), 3)
        self.assertFalse(self.outra.horarios.exists())

    def test_alteracao_preserva_valores_anteriores_e_novos(self):
        horario = self.cadastrar()
        self.alterar(horario, dia_semana=2, inicio=time(11), fim=time(12))
        horario.refresh_from_db()
        self.assertEqual(horario.dia_semana, 2)
        self.assertEqual(horario.inicio, time(11))
        self.assertEqual(horario.fim, time(12))
        registro = horario.registros.get(acao="alteracao")
        self.assertEqual(registro.dados_anteriores["inicio"], "09:00:00")
        self.assertEqual(registro.dados_novos, {"dia_semana": 2, "inicio": "11:00:00", "fim": "12:00:00"})
        self.assertEqual(horario.registros.count(), 2)

    def test_validacao_de_dia_e_intervalo_antes_de_gravar(self):
        for dados in ({"dia_semana": -1}, {"dia_semana": 7}, {"dia_semana": "inválido"},
                      {"inicio": None}, {"inicio": "inválido"}, {"fim": None},
                      {"fim": time(9)}, {"fim": time(8)}, {"inicio": time(9, tzinfo=timezone.utc)}):
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                self.cadastrar(**dados)
        self.assertFalse(HorarioAtividade.objects.exists())
        self.assertFalse(RegistroGradeAtividade.objects.exists())

    def test_alteracao_invalida_mantem_grade_e_auditoria(self):
        horario = self.cadastrar()
        with self.assertRaises(ValidationError):
            self.alterar(horario, fim=time(8))
        horario.refresh_from_db()
        self.assertEqual(horario.fim, time(10))
        self.assertEqual(horario.registros.count(), 1)

    def test_anonimo_sem_permissao_e_desativado_nao_gravam(self):
        sem_acesso = get_user_model().objects.create_user(username="grade_sem_permissao")
        for usuario in (None, AnonymousUser(), sem_acesso):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                cadastrar_horario(usuario=usuario, atividade_id=self.atividade.pk, **self.dados)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.cadastrar()
        self.assertFalse(HorarioAtividade.objects.exists())

    def test_alteracao_exige_permissao_atual_mesmo_com_cache(self):
        horario = self.cadastrar()
        self.assertTrue(self.usuario.has_perm("atividades.change_horarioatividade"))
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="change_horarioatividade"
        ))
        with self.assertRaises(PermissionDenied):
            self.alterar(horario, dia_semana=1)
        horario.refresh_from_db()
        self.assertEqual(horario.dia_semana, 0)

    def test_horario_de_outra_atividade_nao_pode_ser_alterado(self):
        horario = self.cadastrar()
        with self.assertRaises(HorarioAtividade.DoesNotExist):
            alterar_horario(usuario=self.usuario, atividade_id=self.outra.pk, horario_id=horario.pk, **self.dados)
        self.assertEqual(horario.registros.count(), 1)

    def test_atividade_inexistente_nao_cria_grade(self):
        with self.assertRaises(Atividade.DoesNotExist):
            cadastrar_horario(usuario=self.usuario, atividade_id=999999, **self.dados)
        self.assertFalse(HorarioAtividade.objects.exists())

    def test_falha_na_auditoria_reverte_cadastro_e_alteracao(self):
        with patch("atividades.services.RegistroGradeAtividade.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.cadastrar()
        self.assertFalse(HorarioAtividade.objects.exists())
        horario = self.cadastrar()
        with patch("atividades.services.RegistroGradeAtividade.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.alterar(horario, dia_semana=3)
        horario.refresh_from_db()
        self.assertEqual(horario.dia_semana, 0)
        self.assertEqual(horario.registros.count(), 1)

    def test_banco_rejeita_dia_ou_intervalo_invalido(self):
        for dados in ({"dia_semana": 7}, {"fim": time(8)}):
            with self.subTest(dados=dados), self.assertRaises(IntegrityError):
                with transaction.atomic():
                    HorarioAtividade.objects.create(atividade=self.atividade, **(self.dados | dados))

    def test_interface_cadastra_e_altera_pelo_backend(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(reverse("atividades:lista")), self.url())
        self.assertContains(self.client.get(self.url()), "Nenhum horário cadastrado")
        dados = {"dia_semana": "0", "inicio": "09:00", "fim": "10:00"}
        resposta = self.client.post(self.url(), dados, follow=True)
        self.assertContains(resposta, "Horário cadastrado com sucesso")
        self.assertContains(resposta, "Segunda-feira")
        horario = HorarioAtividade.objects.get()
        self.assertContains(self.client.get(self.editar_url(horario)), "Salvar alteração")
        resposta = self.client.post(self.editar_url(horario), dados | {"dia_semana": "4", "fim": "11:00"}, follow=True)
        self.assertContains(resposta, "Sexta-feira")
        self.assertContains(resposta, "<td>11:00</td>", html=True)
        self.assertNotContains(resposta, "11:00:00")
        registro = horario.registros.get(acao="alteracao")
        self.assertEqual(registro.dados_anteriores["dia_semana"], 0)
        self.assertEqual(registro.dados_novos["dia_semana"], 4)
        self.client.get(self.url())
        self.assertEqual(HorarioAtividade.objects.count(), 1)

    def test_interface_invalida_exibe_erro_sem_gravar(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url(), {"dia_semana": "0", "inicio": "10:00", "fim": "09:00"})
        self.assertContains(resposta, "O término deve ser posterior")
        self.assertIn("fim", resposta.context["form"].errors)
        self.assertFalse(HorarioAtividade.objects.exists())

    def test_interface_anonima_e_sem_acesso_nao_expoe_grade(self):
        self.assertEqual(self.client.get(self.url()).status_code, 302)
        self.assertEqual(self.client.post(self.url(), {}).status_code, 302)
        self.usuario.user_permissions.clear()
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.url()).status_code, 403)
        self.assertEqual(self.client.post(self.url(), {}).status_code, 403)

    def test_interface_somente_leitura_nao_permite_post_ou_edicao(self):
        horario = self.cadastrar()
        self.usuario.user_permissions.remove(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=("add_horarioatividade", "change_horarioatividade")
        ))
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Segunda-feira")
        self.assertNotContains(resposta, "Adicionar horário")
        self.assertNotContains(resposta, ">Alterar</a>")
        self.assertEqual(self.client.post(self.url(), {}).status_code, 403)
        self.assertEqual(self.client.get(self.editar_url(horario)).status_code, 403)
        self.assertEqual(self.client.post(self.editar_url(horario), {}).status_code, 403)

    def test_interface_recusa_horario_de_outra_atividade_e_ids_inexistentes(self):
        horario = self.cadastrar()
        self.client.force_login(self.usuario)
        for metodo in (self.client.get, self.client.post):
            self.assertEqual(metodo(self.editar_url(horario, self.outra)).status_code, 404)
            self.assertEqual(metodo(reverse("atividades:grade", args=[999999])).status_code, 404)
        self.assertEqual(horario.registros.count(), 1)

    def test_csrf_em_cadastro_e_alteracao(self):
        horario = self.cadastrar()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        dados = {"dia_semana": "1", "inicio": "09:00", "fim": "10:00"}
        for url in (self.url(), self.editar_url(horario)):
            self.assertEqual(client.post(url, dados).status_code, 403)
            client.get(url)
            token = client.cookies["csrftoken"].value
            self.assertEqual(client.post(url, dados | {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(HorarioAtividade.objects.count(), 2)
        self.assertEqual(RegistroGradeAtividade.objects.count(), 3)
