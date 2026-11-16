from datetime import date, time, timezone
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from atividades.models import Atividade, Aula, RegistroRealizacaoAula
from atividades.services import registrar_aula, cadastrar_horario, alterar_horario


class AulaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="equipe_aula_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=(
                "view_atividade", "view_aula", "add_aula", "add_horarioatividade", "change_horarioatividade"
            )
        ))
        cls.atividade = Atividade.objects.create(nome="Atividade fictícia", local="Sala de teste", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra fictícia", local="Outra sala", monitor="Fictício")
        cls.dados = {"data": date(2024, 2, 29), "inicio": time(9, 15), "fim": time(10, 10)}
        cls.post = {"data": "2024-02-29", "inicio": "09:15", "fim": "10:10", "tipo": "regular"}

    def registrar(self, **dados):
        return registrar_aula(usuario=self.usuario, atividade_id=self.atividade.pk, **(self.dados | dados))

    def url(self, atividade=None):
        return reverse("atividades:aulas", args=[(atividade or self.atividade).pk])

    def assert_sem_aulas(self):
        self.assertFalse(Aula.objects.exists())
        self.assertFalse(RegistroRealizacaoAula.objects.exists())

    def test_registra_data_e_horarios_efetivos_com_autor_e_data_de_digitacao_separados(self):
        aula = self.registrar()
        aula.refresh_from_db()
        self.assertEqual(aula.data, self.dados["data"])
        self.assertEqual(aula.inicio, self.dados["inicio"])
        self.assertEqual(aula.fim, self.dados["fim"])
        registro = aula.registro_realizacao
        self.assertEqual(registro.usuario_id, self.usuario.pk)
        self.assertNotEqual(registro.registrado_em.date(), aula.data)
        self.assertEqual(registro.dados, {
            "atividade_id": self.atividade.pk, "data": "2024-02-29", "inicio": "09:15:00", "fim": "10:10:00",
            "tipo": "nao_informado",
        })

    def test_mais_de_uma_aula_no_mesmo_dia(self):
        self.registrar()
        self.registrar(inicio=time(14), fim=time(15))
        self.assertEqual(self.atividade.aulas.count(), 2)
        self.assertFalse(self.outra.aulas.exists())

    def test_data_obrigatoria_e_valida(self):
        for valor in (None, "", "inválido", "2025-02-29"):
            with self.subTest(valor=valor), self.assertRaises(ValidationError) as erro:
                self.registrar(data=valor)
            self.assertIn("data", erro.exception.message_dict)
        self.assert_sem_aulas()

    def test_horarios_obrigatorios_e_intervalo_valido(self):
        for dados in ({"inicio": None}, {"fim": None}, {"inicio": "inválido"}, {"fim": "25:00"},
                      {"fim": time(9, 15)}, {"fim": time(8)}, {"inicio": time(9, tzinfo=timezone.utc)}):
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                self.registrar(**dados)
        self.assert_sem_aulas()

    def test_anonimo_nao_persistido_e_sem_permissao_nao_registram(self):
        sem_acesso = get_user_model().objects.create_user(username="aula_sem_acesso")
        for usuario in (None, AnonymousUser(), get_user_model()(username="nao_salvo"), sem_acesso):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                registrar_aula(usuario=usuario, atividade_id=self.atividade.pk, **self.dados)
        self.assert_sem_aulas()

    def test_conta_desativada_nao_registra(self):
        self.assertTrue(self.usuario.has_perm("atividades.add_aula"))
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.registrar()
        self.assert_sem_aulas()

    def test_permissao_revogada_nao_e_aceita_por_cache(self):
        self.assertTrue(self.usuario.has_perm("atividades.add_aula"))
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="add_aula"
        ))
        with self.assertRaises(PermissionDenied):
            self.registrar()
        self.assert_sem_aulas()

    def test_atividade_inexistente_nao_registra(self):
        with self.assertRaises(Atividade.DoesNotExist):
            registrar_aula(usuario=self.usuario, atividade_id=999999, **self.dados)
        self.assert_sem_aulas()

    def test_aula_independe_da_grade_regular(self):
        cadastrar_horario(usuario=self.usuario, atividade_id=self.atividade.pk,
                          dia_semana=0, inicio=time(14), fim=time(15))
        aula = self.registrar()  # Quinta-feira, horários diferentes dos previstos.
        self.assertEqual(aula.inicio, time(9, 15))
        self.assertEqual(aula.data.weekday(), 3)

    def test_alterar_grade_nao_modifica_aula_ja_registrada(self):
        horario = cadastrar_horario(usuario=self.usuario, atividade_id=self.atividade.pk,
                                    dia_semana=3, inicio=time(9), fim=time(10))
        aula = self.registrar()
        alterar_horario(usuario=self.usuario, atividade_id=self.atividade.pk, horario_id=horario.pk,
                        dia_semana=4, inicio=time(14), fim=time(15))
        aula.refresh_from_db()
        self.assertEqual(aula.data, self.dados["data"])
        self.assertEqual(aula.inicio, self.dados["inicio"])
        self.assertEqual(aula.fim, self.dados["fim"])

    def test_falha_na_auditoria_desfaz_registro(self):
        with patch("atividades.services.RegistroRealizacaoAula.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.registrar()
        self.assert_sem_aulas()

    def test_banco_rejeita_intervalo_invalido(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Aula.objects.create(atividade=self.atividade, **(self.dados | {"fim": time(8)}))

    def test_interface_registra_lista_e_audita(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(reverse("atividades:lista")), self.url())
        self.assertContains(self.client.get(self.url()), "Nenhuma aula registrada")
        resposta = self.client.post(self.url(), self.post, follow=True)
        self.assertContains(resposta, "Aula realizada registrada com sucesso")
        self.assertContains(resposta, "29/02/2024")
        self.assertContains(resposta, "<td>09:15</td>", html=True)
        self.assertNotContains(resposta, "09:15:00")
        self.assertEqual(Aula.objects.get().atividade_id, self.atividade.pk)
        self.assertEqual(RegistroRealizacaoAula.objects.get().usuario_id, self.usuario.pk)
        self.client.get(self.url())
        self.assertEqual(Aula.objects.count(), 1)

    def test_interface_dados_invalidos_exibem_erros_sem_gravar(self):
        self.client.force_login(self.usuario)
        for dados in ({"data": "2025-02-29"}, {"inicio": "11:00"}):
            with self.subTest(dados=dados):
                resposta = self.client.post(self.url(), self.post | dados)
                self.assertEqual(resposta.status_code, 200)
                self.assertTrue(resposta.context["form"].errors)
        self.assert_sem_aulas()

    def test_interface_anonima_e_sem_permissao(self):
        for metodo in (self.client.get, self.client.post):
            self.assertEqual(metodo(self.url()).status_code, 302)
        self.usuario.user_permissions.clear()
        self.client.force_login(self.usuario)
        for metodo in (self.client.get, self.client.post):
            self.assertEqual(metodo(self.url()).status_code, 403)
        self.assert_sem_aulas()

    def test_interface_somente_leitura_e_isolamento_por_atividade(self):
        self.registrar()
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="add_aula"
        ))
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "29/02/2024")
        self.assertNotContains(resposta, "Registrar aula realizada")
        self.assertEqual(self.client.post(self.url(), self.post).status_code, 403)
        self.assertNotContains(self.client.get(self.url(self.outra)), "29/02/2024")
        self.assertEqual(Aula.objects.count(), 1)

    def test_interface_atividade_inexistente_retorna_404(self):
        self.client.force_login(self.usuario)
        for metodo in (self.client.get, self.client.post):
            self.assertEqual(metodo(reverse("atividades:aulas", args=[999999])).status_code, 404)

    def test_csrf_obrigatorio(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        self.assertEqual(client.post(self.url(), self.post).status_code, 403)
        self.assert_sem_aulas()
        client.get(self.url())
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.url(), self.post | {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(RegistroRealizacaoAula.objects.count(), 1)

    def test_listagem_paginada_por_data_de_ocorrencia(self):
        for dia in range(1, 22):
            self.registrar(data=date(2024, 1, dia))
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url())
        self.assertEqual(len(resposta.context["pagina"]), 20)
        self.assertEqual(resposta.context["pagina"][0].data, date(2024, 1, 21))
        resposta = self.client.get(self.url(), {"page": 2})
        self.assertEqual(len(resposta.context["pagina"]), 1)
        self.assertEqual(resposta.context["pagina"][0].data, date(2024, 1, 1))
