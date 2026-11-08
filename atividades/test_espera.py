from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.test import Client
from django.urls import reverse
from unittest.mock import patch

from .espera import adicionar_espera, retirar_espera
from .services import inscrever_participante
from .models import Atividade, Inscricao, EsperaAtividade


@override_settings(DEBUG=True)
class EsperaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="espera_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("add_esperaatividade", "view_esperaatividade", "change_esperaatividade",
                          "view_atividade", "add_inscricao", "view_inscricao")))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala", monitor="Fictício")

    def adicionar(self, **kwargs):
        return adicionar_espera(**({"usuario": self.usuario, "atividade_id": self.atividade.pk,
            "participante_referencia": "demo-1"} | kwargs))

    def atender(self, espera, **kwargs):
        return inscrever_participante(**({"usuario": self.usuario, "atividade_id": self.atividade.pk,
            "participante_referencia": espera.participante_referencia, "espera_id": espera.pk,
            "vaga_confirmada": True} | kwargs))

    def test_fifo_confirmacao_manual_e_bloqueio_inscricao_direta(self):
        primeiro = self.adicionar()
        segundo = self.adicionar(participante_referencia="demo-2")
        with self.assertRaises(ValidationError):
            self.atender(segundo)
        with self.assertRaises(ValidationError):
            self.atender(primeiro, vaga_confirmada=False)
        with self.assertRaises(ValidationError):
            inscrever_participante(usuario=self.usuario, atividade_id=self.atividade.pk, participante_referencia="demo-3")
        inscricao = self.atender(primeiro)
        primeiro.refresh_from_db()
        self.assertEqual(primeiro.inscricao, inscricao)
        self.assertEqual(primeiro.situacao, "inscrito")
        self.assertTrue(primeiro.registros.latest("pk").novos["vaga_confirmada"])
        self.atender(segundo)
        self.assertEqual(Inscricao.objects.count(), 2)
        with self.assertRaises(ValidationError):
            self.atender(primeiro)

    def test_retirada_preserva_historico_e_reentrada_vai_ao_final(self):
        primeiro = self.adicionar()
        segundo = self.adicionar(participante_referencia="demo-2")
        retirar_espera(usuario=self.usuario, atividade_id=self.atividade.pk, espera_id=primeiro.pk)
        novo = self.adicionar()
        self.assertGreater(novo.pk, segundo.pk)
        with self.assertRaises(ValidationError):
            self.atender(novo)
        primeiro.refresh_from_db()
        self.assertEqual(primeiro.situacao, "retirado")
        self.assertEqual(primeiro.registros.count(), 2)
        self.atender(segundo)

    def test_atendimento_e_retirada_exigem_permissoes_atuais(self):
        espera = self.adicionar()
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="change_esperaatividade"))
        with self.assertRaises(PermissionDenied):
            self.atender(espera)
        with self.assertRaises(PermissionDenied):
            retirar_espera(usuario=self.usuario, atividade_id=self.atividade.pk, espera_id=espera.pk)

    def test_falha_auditoria_reverte_atendimento_e_retirada(self):
        espera = self.adicionar()
        with patch("atividades.espera.RegistroEsperaAtividade.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.atender(espera)
            with self.assertRaises(RuntimeError):
                retirar_espera(usuario=self.usuario, atividade_id=self.atividade.pk, espera_id=espera.pk)
        espera.refresh_from_db()
        self.assertEqual(espera.situacao, "aguardando")
        self.assertIsNone(espera.inscricao_id)
        self.assertFalse(Inscricao.objects.exists())

    def test_interface_atendimento_e_retirada_get_sem_escrita_post_csrf(self):
        espera = self.adicionar()
        self.client.force_login(self.usuario)
        url = reverse("atividades:atender_espera", args=[self.atividade.pk, espera.pk])
        self.assertContains(self.client.get(url), "vaga disponível")
        self.assertFalse(Inscricao.objects.exists())
        self.assertTrue(self.client.post(url, {}).context["form"].errors)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(url, {"vaga_confirmada": "on"}).status_code, 403)
        self.assertEqual(self.client.post(url, {"vaga_confirmada": "on"}).status_code, 302)
        self.assertEqual(Inscricao.objects.count(), 1)
        outro = self.adicionar(participante_referencia="demo-2")
        url = reverse("atividades:retirar_espera", args=[self.atividade.pk, outro.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url).status_code, 302)
        outro.refresh_from_db()
        self.assertEqual(outro.situacao, "retirado")

    def test_participante_removido_nao_pula_fila_e_pode_ser_retirado(self):
        espera = self.adicionar()
        EsperaAtividade.objects.filter(pk=espera.pk).update(participante_referencia="removido")
        espera.refresh_from_db()
        with self.assertRaises(ValidationError):
            self.atender(espera)
        self.client.force_login(self.usuario)
        resposta = self.client.post(reverse("atividades:atender_espera", args=[self.atividade.pk, espera.pk]), {"vaga_confirmada": "on"})
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["form"].errors)
        retirar_espera(usuario=self.usuario, atividade_id=self.atividade.pk, espera_id=espera.pk)

    def test_http_nao_aceita_pular_primeiro_ou_contexto_errado(self):
        primeiro = self.adicionar()
        segundo = self.adicionar(participante_referencia="demo-2")
        self.client.force_login(self.usuario)
        url = reverse("atividades:atender_espera", args=[self.atividade.pk, segundo.pk])
        resposta = self.client.post(url, {"vaga_confirmada": "on"})
        self.assertTrue(resposta.context["form"].errors)
        self.assertFalse(Inscricao.objects.exists())
        outra = Atividade.objects.create(nome="Outra", local="Sala", monitor="Fictício")
        self.assertEqual(self.client.get(reverse("atividades:atender_espera", args=[outra.pk, primeiro.pk])).status_code, 404)

    def test_retirada_fora_da_atividade_ou_origem_nao_altera_registro(self):
        espera = self.adicionar()
        outra = Atividade.objects.create(nome="Outra", local="Sala", monitor="Fictício")
        with self.assertRaises(EsperaAtividade.DoesNotExist):
            retirar_espera(usuario=self.usuario, atividade_id=outra.pk, espera_id=espera.pk)
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.test_inscricoes.ProvedorAlternativo"):
            with self.assertRaises(EsperaAtividade.DoesNotExist):
                retirar_espera(usuario=self.usuario, atividade_id=self.atividade.pk, espera_id=espera.pk)

    def test_espera_auditada_sem_inscricao_automatica(self):
        espera = self.adicionar()
        self.assertEqual(espera.situacao, "aguardando")
        self.assertFalse(Inscricao.objects.exists())
        evento = espera.registros.get()
        self.assertEqual(evento.usuario, self.usuario)
        self.assertIsNone(evento.anteriores)
        self.assertIsNotNone(evento.registrado_em)

    def test_rejeita_duplicacao_e_participante_desconhecido(self):
        self.adicionar()
        with self.assertRaises(ValidationError):
            self.adicionar()
        with self.assertRaises(ValidationError):
            self.adicionar(participante_referencia="inexistente")
        self.assertEqual(EsperaAtividade.objects.count(), 1)

    def test_inscrito_nao_entra_na_espera(self):
        Inscricao.objects.create(atividade=self.atividade, origem_participante="placeholder",
            participante_referencia="demo-1", cadastrada_por=self.usuario)
        with self.assertRaises(ValidationError):
            self.adicionar()

    def test_permissao_revogada_e_conta_desativada(self):
        self.usuario.has_perm("atividades.add_esperaatividade")
        self.usuario.user_permissions.clear()
        with self.assertRaises(PermissionDenied):
            self.adicionar()
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.adicionar()

    def test_interface_cadastro_consulta_csrf_e_permissao(self):
        url = reverse("atividades:lista_espera", args=[self.atividade.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(url), "Nenhum participante")
        self.assertEqual(self.client.post(url, {"participante_referencia": "demo-1"}).status_code, 302)
        self.assertContains(self.client.get(url), "Participante fictício 1")
        self.assertEqual(EsperaAtividade.objects.count(), 1)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.usuario)
        self.assertEqual(cliente.post(url, {"participante_referencia": "demo-2"}).status_code, 403)
        self.usuario.user_permissions.clear()
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_isolamento_origem_e_atividade(self):
        self.adicionar()
        outra = Atividade.objects.create(nome="Outra", local="Sala", monitor="Fictício")
        self.adicionar(atividade_id=outra.pk)
        self.assertEqual(EsperaAtividade.objects.count(), 2)
        self.client.force_login(self.usuario)
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.test_inscricoes.ProvedorAlternativo"):
            resposta = self.client.get(reverse("atividades:lista_espera", args=[self.atividade.pk]))
            self.assertEqual(resposta.context["pagina"].paginator.count, 0)

    @override_settings(DEBUG=False)
    def test_indisponibilidade_provedor(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(reverse("atividades:lista_espera", args=[self.atividade.pk])).status_code, 503)
