from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from .models import Atividade, Aula, RegistroRealizacaoAula
from .services import cadastrar_horario, registrar_aula


class AulasExtrasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="equipe_extras_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=(
                "view_atividade", "view_aula", "add_aula", "add_horarioatividade"
            )
        ))
        cls.atividade = Atividade.objects.create(nome="Atividade fictícia", local="Sala de teste", monitor="Fictício")
        cls.dados = {"data": date(2024, 2, 29), "inicio": time(9), "fim": time(10)}
        cls.post = {"data": "2024-02-29", "inicio": "09:00", "fim": "10:00"}
        cls.url = reverse("atividades:aulas", args=[cls.atividade.pk])

    def registrar(self, **dados):
        return registrar_aula(usuario=self.usuario, atividade_id=self.atividade.pk, **(self.dados | dados))

    def test_extra_e_remarcada_fora_do_dia_e_horarios_da_grade(self):
        cadastrar_horario(usuario=self.usuario, atividade_id=self.atividade.pk,
                          dia_semana=0, inicio=time(14), fim=time(15))
        for tipo in (Aula.Tipo.EXTRA, Aula.Tipo.REMARCADA):
            with self.subTest(tipo=tipo):
                aula = self.registrar(tipo=tipo)
                aula.refresh_from_db()
                self.assertEqual(aula.tipo, tipo)
                self.assertEqual(aula.data.weekday(), 3)
                self.assertEqual(aula.inicio, time(9))
                self.assertEqual(aula.registro_realizacao.dados["tipo"], tipo)
                self.assertEqual(aula.registro_realizacao.usuario_id, self.usuario.pk)

    def test_todos_os_tipos_podem_ser_registrados_sem_grade(self):
        for tipo in (Aula.Tipo.REGULAR, Aula.Tipo.EXTRA, Aula.Tipo.REMARCADA):
            self.registrar(tipo=tipo)
        self.assertFalse(self.atividade.horarios.exists())
        self.assertEqual(self.atividade.aulas.count(), 3)

    def test_tipo_invalido_nao_persiste_aula_ou_auditoria(self):
        for tipo in (None, "", "cancelada", "outro", "<script>"):
            with self.subTest(tipo=tipo), self.assertRaises(ValidationError) as erro:
                self.registrar(tipo=tipo)
            self.assertIn("tipo", erro.exception.message_dict)
        self.assertFalse(Aula.objects.exists())
        self.assertFalse(RegistroRealizacaoAula.objects.exists())

    def test_remarcada_nao_altera_outra_aula_nem_a_grade(self):
        original = self.registrar(tipo=Aula.Tipo.REGULAR)
        snapshot = original.registro_realizacao.dados.copy()
        self.registrar(tipo=Aula.Tipo.REMARCADA, data=date(2024, 3, 1))
        original.refresh_from_db()
        self.assertEqual(original.data, self.dados["data"])
        self.assertEqual(original.tipo, Aula.Tipo.REGULAR)
        self.assertEqual(original.registro_realizacao.dados, snapshot)
        self.assertEqual(Aula.objects.count(), 2)
        self.assertFalse(self.atividade.horarios.exists())

    def test_falha_auditoria_desfaz_registro_extra_ou_remarcado(self):
        for tipo in (Aula.Tipo.EXTRA, Aula.Tipo.REMARCADA):
            with self.subTest(tipo=tipo), patch(
                "atividades.services.RegistroRealizacaoAula.objects.create", side_effect=RuntimeError
            ):
                with self.assertRaises(RuntimeError):
                    self.registrar(tipo=tipo)
        self.assertFalse(Aula.objects.exists())

    def test_permissao_revogada_impede_extra_e_remarcada(self):
        self.assertTrue(self.usuario.has_perm("atividades.add_aula"))
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="add_aula"
        ))
        for tipo in (Aula.Tipo.EXTRA, Aula.Tipo.REMARCADA):
            with self.subTest(tipo=tipo), self.assertRaises(PermissionDenied):
                self.registrar(tipo=tipo)
        self.assertFalse(Aula.objects.exists())

    def test_banco_rejeita_tipo_fora_dos_permitidos(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Aula.objects.create(atividade=self.atividade, **self.dados, tipo="invalido")

    def test_interface_escolhe_tipo_persiste_e_exibe(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        escolhas = dict(resposta.context["form"].fields["tipo"].choices)
        self.assertEqual(set(escolhas), {"", "regular", "extra", "remarcada"})
        for tipo, rotulo in (("extra", "Extra"), ("remarcada", "Remarcada")):
            with self.subTest(tipo=tipo):
                resposta = self.client.post(self.url, self.post | {"tipo": tipo}, follow=True)
                self.assertContains(resposta, f"<td>{rotulo}</td>", html=True)
                aula = Aula.objects.get(tipo=tipo)
                self.assertEqual(aula.registro_realizacao.dados["tipo"], tipo)
        self.assertEqual(Aula.objects.count(), 2)

    def test_interface_exige_tipo_e_rejeita_nao_informado_para_novos_registros(self):
        self.client.force_login(self.usuario)
        for dados in (self.post, self.post | {"tipo": "nao_informado"}, self.post | {"tipo": "outro"}):
            with self.subTest(dados=dados):
                resposta = self.client.post(self.url, dados)
                self.assertEqual(resposta.status_code, 200)
                self.assertIn("tipo", resposta.context["form"].errors)
        self.assertFalse(Aula.objects.exists())

    def test_contrato_anterior_e_listagem_preservam_tipo_nao_informado(self):
        aula = self.registrar()
        self.assertEqual(aula.tipo, Aula.Tipo.NAO_INFORMADO)
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(self.url), "Não informado")

    def test_interface_somente_leitura_nao_registra_extra_ou_remarcada(self):
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="add_aula"
        ))
        self.client.force_login(self.usuario)
        for tipo in ("extra", "remarcada"):
            self.assertEqual(self.client.post(self.url, self.post | {"tipo": tipo}).status_code, 403)
        self.assertFalse(Aula.objects.exists())

    def test_interface_csrf_para_extras_e_remarcadas(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        for tipo in ("extra", "remarcada"):
            dados = self.post | {"tipo": tipo}
            self.assertEqual(client.post(self.url, dados).status_code, 403)
            client.get(self.url)
            token = client.cookies["csrftoken"].value
            self.assertEqual(client.post(self.url, dados | {"csrfmiddlewaretoken": token}).status_code, 302)
        self.assertEqual(RegistroRealizacaoAula.objects.count(), 2)


class TipoAulaMigrationTests(TransactionTestCase):
    def test_migration_preserva_ocorrencia_e_auditoria_sem_inferir_tipo(self):
        origem = [("atividades", "0004_aula_registrorealizacaoaula_and_more")]
        destino = [("atividades", "0005_aula_tipo_aula_aula_tipo_valido")]
        usuario = get_user_model().objects.create_user(username="auditoria_legada_ficticia")
        executor = MigrationExecutor(connection)
        try:
            executor.migrate(origem)
            apps = executor.loader.project_state(origem).apps
            atividade = apps.get_model("atividades", "Atividade").objects.create(
                nome="Legada fictícia", local="Sala de teste", monitor="Fictício"
            )
            aula = apps.get_model("atividades", "Aula").objects.create(
                atividade_id=atividade.pk, data=date(2024, 2, 29), inicio=time(9), fim=time(10)
            )
            snapshot = {"atividade_id": atividade.pk, "data": "2024-02-29", "inicio": "09:00:00", "fim": "10:00:00"}
            apps.get_model("atividades", "RegistroRealizacaoAula").objects.create(
                aula_id=aula.pk, usuario_id=usuario.pk, dados=snapshot
            )
            executor = MigrationExecutor(connection)
            executor.migrate(destino)
            apps = executor.loader.project_state(destino).apps
            migrada = apps.get_model("atividades", "Aula").objects.get(pk=aula.pk)
            self.assertEqual(migrada.tipo, "nao_informado")
            self.assertEqual(migrada.data, date(2024, 2, 29))
            self.assertEqual(migrada.inicio, time(9))
            self.assertEqual(migrada.fim, time(10))
            registro = apps.get_model("atividades", "RegistroRealizacaoAula").objects.get(aula_id=aula.pk)
            self.assertEqual(registro.dados, snapshot)
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(executor.loader.graph.leaf_nodes())
