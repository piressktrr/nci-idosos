from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from .models import Atividade, Aula, RegistroCancelamentoAula, RegistroRealizacaoAula
from .services import cancelar_aula, registrar_aula, registrar_aula_cancelada


class CancelamentoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="cancelamento_ficticio")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=(
                "view_atividade", "view_aula", "add_aula", "cancelar_aula"
            )
        ))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala de teste", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra fictícia", local="Sala de teste", monitor="Fictício")
        cls.dados = {"data": date(2024, 2, 29), "inicio": time(9), "fim": time(10), "tipo": "regular"}
        cls.post = {"data": "2024-02-29", "inicio": "09:00", "fim": "10:00", "tipo": "regular"}

    def realizada(self, **dados):
        return registrar_aula(usuario=self.usuario, atividade_id=self.atividade.pk, **(self.dados | dados))

    def cancelada(self, **dados):
        return registrar_aula_cancelada(usuario=self.usuario, atividade_id=self.atividade.pk, **(self.dados | dados))

    def cancelar(self, aula):
        return cancelar_aula(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=aula.pk)

    def url(self, aula=None, atividade=None):
        if aula:
            return reverse("atividades:cancelar_aula", args=[(atividade or self.atividade).pk, aula.pk])
        return reverse("atividades:nova_aula_cancelada", args=[self.atividade.pk])

    def lista_url(self):
        return reverse("atividades:aulas", args=[self.atividade.pk])

    def test_cancela_preservando_dados_e_auditoria_de_realizacao(self):
        aula = self.realizada()
        snapshot = aula.registro_realizacao.dados.copy()
        self.cancelar(aula)
        aula.refresh_from_db()
        self.assertEqual(aula.situacao, Aula.Situacao.CANCELADA)
        for campo, valor in self.dados.items():
            self.assertEqual(getattr(aula, campo), valor)
        self.assertEqual(aula.registro_realizacao.dados, snapshot)
        registro = aula.registro_cancelamento
        self.assertEqual(registro.usuario_id, self.usuario.pk)
        self.assertIsNotNone(registro.registrado_em)
        self.assertEqual(registro.dados_anteriores["situacao"], "realizada")
        self.assertEqual(registro.dados_novos["situacao"], "cancelada")

    def test_registra_cancelada_sem_lancar_realizacao(self):
        aula = self.cancelada()
        self.assertEqual(aula.situacao, "cancelada")
        self.assertFalse(RegistroRealizacaoAula.objects.exists())
        self.assertIsNone(aula.registro_cancelamento.dados_anteriores)
        self.assertEqual(aula.registro_cancelamento.dados_novos["data"], "2024-02-29")
        self.assertFalse(Aula.objects.realizadas().exists())

    def test_consulta_de_realizadas_exclui_canceladas_de_todos_os_tipos(self):
        mantida = self.realizada()
        for tipo in Aula.Tipo.values:
            self.cancelada(tipo=tipo)
            self.cancelar(self.realizada(tipo=tipo))
        self.assertEqual(list(Aula.objects.realizadas()), [mantida])
        self.assertEqual(list(self.atividade.aulas.realizadas()), [mantida])
        self.assertEqual(self.atividade.aulas.count(), 9)
        self.assertFalse(self.outra.aulas.exists())

    def test_cancelamento_repetido_nao_duplica_ou_reescreve_auditoria(self):
        aula = self.realizada()
        self.cancelar(aula)
        primeiro = aula.registro_cancelamento
        with self.assertRaises(ValidationError):
            self.cancelar(aula)
        self.assertEqual(RegistroCancelamentoAula.objects.count(), 1)
        self.assertEqual(aula.registro_cancelamento.registrado_em, primeiro.registrado_em)

    def test_anonimo_usuario_nao_persistido_e_sem_permissao_nao_cancelam(self):
        aula = self.realizada()
        sem_acesso = get_user_model().objects.create_user(username="sem_cancelamento")
        for usuario in (None, AnonymousUser(), get_user_model()(username="nao_salvo"), sem_acesso):
            with self.subTest(usuario=usuario):
                with self.assertRaises(PermissionDenied):
                    cancelar_aula(usuario=usuario, atividade_id=self.atividade.pk, aula_id=aula.pk)
                with self.assertRaises(PermissionDenied):
                    registrar_aula_cancelada(usuario=usuario, atividade_id=self.atividade.pk, **self.dados)
        aula.refresh_from_db()
        self.assertEqual(aula.situacao, "realizada")
        self.assertFalse(RegistroCancelamentoAula.objects.exists())

    def test_cancelamento_consulta_permissao_revogada_e_conta_desativada(self):
        aula = self.realizada()
        self.assertTrue(self.usuario.has_perm("atividades.cancelar_aula"))
        permissao = Permission.objects.get(content_type__app_label="atividades", codename="cancelar_aula")
        self.usuario.user_permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            self.cancelar(aula)
        self.usuario.user_permissions.add(permissao)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.cancelada()
        self.assertFalse(RegistroCancelamentoAula.objects.exists())

    def test_registro_direto_exige_tambem_permissao_de_cadastro(self):
        aula = self.realizada()
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="add_aula"
        ))
        with self.assertRaises(PermissionDenied):
            self.cancelada()
        self.cancelar(aula)
        self.assertEqual(RegistroCancelamentoAula.objects.count(), 1)

    def test_nao_cancela_aula_de_outra_atividade(self):
        aula = self.realizada()
        with self.assertRaises(Aula.DoesNotExist):
            cancelar_aula(usuario=self.usuario, atividade_id=self.outra.pk, aula_id=aula.pk)
        self.assertFalse(RegistroCancelamentoAula.objects.exists())

    def test_falha_na_auditoria_reverte_status_ou_cadastro(self):
        aula = self.realizada()
        with patch("atividades.services.RegistroCancelamentoAula.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.cancelar(aula)
            with self.assertRaises(RuntimeError):
                self.cancelada()
        aula.refresh_from_db()
        self.assertEqual(aula.situacao, "realizada")
        self.assertEqual(Aula.objects.count(), 1)
        self.assertFalse(RegistroCancelamentoAula.objects.exists())

    def test_registro_direto_valida_dados_sem_gravar(self):
        for dados in ({"data": None}, {"fim": time(8)}, {"tipo": "invalido"}):
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                self.cancelada(**dados)
        with self.assertRaises(Atividade.DoesNotExist):
            registrar_aula_cancelada(usuario=self.usuario, atividade_id=999999, **self.dados)
        self.assertFalse(Aula.objects.exists())
        self.assertFalse(RegistroCancelamentoAula.objects.exists())

    def test_banco_rejeita_situacao_invalida(self):
        aula = self.realizada()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Aula.objects.filter(pk=aula.pk).update(situacao="outra")

    def test_interface_confirma_em_get_e_cancela_somente_em_post(self):
        aula = self.realizada()
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(self.url(aula)), "Confirmar cancelamento")
        self.assertTrue(Aula.objects.realizadas().exists())
        resposta = self.client.post(self.url(aula), follow=True)
        self.assertContains(resposta, "Aula cancelada com sucesso")
        self.assertContains(resposta, "Realizadas: 0 · Canceladas: 1")
        self.assertContains(resposta, "<td>Cancelada</td>", html=True)
        self.assertNotContains(resposta, ">Cancelar aula</a>")
        self.assertFalse(Aula.objects.realizadas().exists())
        self.assertEqual(self.client.post(self.url(aula)).status_code, 200)
        self.assertEqual(RegistroCancelamentoAula.objects.count(), 1)

    def test_interface_registra_cancelada_diretamente(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(self.lista_url()), self.url())
        self.assertContains(self.client.get(self.url()), "Início previsto")
        resposta = self.client.post(self.url(), self.post, follow=True)
        self.assertContains(resposta, "Aula cancelada registrada com sucesso")
        self.assertEqual(Aula.objects.get().situacao, "cancelada")
        self.assertFalse(RegistroRealizacaoAula.objects.exists())

    def test_interface_sem_permissao_ou_anonima_nao_expoe_acoes(self):
        aula = self.realizada()
        for url in (self.url(), self.url(aula)):
            self.assertEqual(self.client.get(url).status_code, 302)
            self.assertEqual(self.client.post(url, self.post).status_code, 302)
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="cancelar_aula"
        ))
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.lista_url())
        self.assertNotContains(resposta, "Registrar aula cancelada")
        self.assertNotContains(resposta, ">Cancelar aula</a>")
        for url in (self.url(), self.url(aula)):
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, self.post).status_code, 403)

    def test_interface_isola_atividade_e_retorna_404_para_aula_inexistente(self):
        aula = self.realizada()
        self.client.force_login(self.usuario)
        for url in (self.url(aula, self.outra), reverse("atividades:cancelar_aula", args=[self.atividade.pk, 999999])):
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url).status_code, 404)
        self.assertFalse(RegistroCancelamentoAula.objects.exists())

    def test_csrf_no_cancelamento_e_registro_direto(self):
        aula = self.realizada()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        for url in (self.url(aula), self.url()):
            self.assertEqual(client.post(url, self.post).status_code, 403)
            client.get(url)
            token = client.cookies["csrftoken"].value
            self.assertEqual(client.post(url, self.post | {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(RegistroCancelamentoAula.objects.count(), 2)
        self.assertEqual(Aula.objects.realizadas().count(), 0)


class SituacaoAulaMigrationTests(TransactionTestCase):
    def test_migration_mantem_aulas_anteriores_realizadas_sem_reescrever_auditoria(self):
        origem = [("atividades", "0005_aula_tipo_aula_aula_tipo_valido")]
        destino = [("atividades", "0006_registrocancelamentoaula_alter_aula_options_and_more")]
        usuario = get_user_model().objects.create_user(username="legado_cancelamento_ficticio")
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(origem)
            apps = executor.loader.project_state(origem).apps
            atividade = apps.get_model("atividades", "Atividade").objects.create(nome="Legada fictícia", local="Sala", monitor="Fictício")
            aula = apps.get_model("atividades", "Aula").objects.create(
                atividade_id=atividade.pk, data=date(2024, 2, 29), inicio=time(9), fim=time(10), tipo="extra"
            )
            dados = {"data": "2024-02-29", "tipo": "extra"}
            apps.get_model("atividades", "RegistroRealizacaoAula").objects.create(
                aula_id=aula.pk, usuario_id=usuario.pk, dados=dados
            )
            executor = MigrationExecutor(connection)
            executor.migrate(destino)
            apps = executor.loader.project_state(destino).apps
            migrada = apps.get_model("atividades", "Aula").objects.get(pk=aula.pk)
            self.assertEqual(migrada.situacao, "realizada")
            self.assertEqual(migrada.tipo, "extra")
            self.assertEqual(migrada.data, date(2024, 2, 29))
            self.assertEqual(apps.get_model("atividades", "RegistroRealizacaoAula").objects.get(aula_id=aula.pk).dados, dados)
            self.assertFalse(apps.get_model("atividades", "RegistroCancelamentoAula").objects.exists())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
