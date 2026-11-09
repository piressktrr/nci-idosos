from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from atividades.models import Atividade, Aula, Inscricao
from atividades.services import obter_lista_chamada


@override_settings(DEBUG=True)
class ChamadaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="chamada_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=("view_atividade", "view_aula", "view_inscricao")
        ))
        cls.atividade = Atividade.objects.create(nome="Atividade fictícia", local="Sala", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra fictícia", local="Sala", monitor="Fictício")
        cls.aula = Aula.objects.create(atividade=cls.atividade, data=date(2024, 2, 29), inicio=time(9), fim=time(10))
        for referencia in ("demo-2", "demo-1"):
            Inscricao.objects.create(atividade=cls.atividade, origem_participante="placeholder",
                                     participante_referencia=referencia, cadastrada_por=cls.usuario)
        Inscricao.objects.create(atividade=cls.outra, origem_participante="placeholder",
                                 participante_referencia="demo-3", cadastrada_por=cls.usuario)
        cls.url = reverse("atividades:chamada", args=[cls.atividade.pk, cls.aula.pk])

    def consultar(self):
        return obter_lista_chamada(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk)

    def test_lista_apenas_vinculados_em_ordem_de_nome_sem_escrever(self):
        antes = Inscricao.objects.count(), Aula.objects.count()
        lista = self.consultar()
        self.assertEqual([p["referencia"] for p in lista["participantes"]], ["demo-1", "demo-2"])
        self.assertTrue(lista["demonstracao"])
        self.assertEqual(lista["aula"].data, date(2024, 2, 29))
        self.assertEqual(antes, (Inscricao.objects.count(), Aula.objects.count()))

    def test_lista_vazia_nao_inventa_participantes(self):
        self.atividade.inscricoes.all().delete()
        self.assertEqual(self.consultar()["participantes"], [])

    def test_referencia_ausente_continua_visivel_sem_apagar_vinculo(self):
        inscricao = Inscricao.objects.create(atividade=self.atividade, origem_participante="placeholder",
                                             participante_referencia="indisponivel", cadastrada_por=self.usuario)
        lista = self.consultar()["participantes"]
        ausente = next(p for p in lista if p["inscricao_id"] == inscricao.pk)
        self.assertFalse(ausente["disponivel"])
        self.assertEqual(ausente["nome"], "Participante indisponível")
        self.assertTrue(Inscricao.objects.filter(pk=inscricao.pk).exists())

    def test_origem_de_demo_nao_se_mistura_com_provedor_substituido(self):
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorAlternativo"):
            self.assertEqual(self.consultar()["participantes"], [])
            Inscricao.objects.create(atividade=self.atividade, origem_participante="participantes",
                                     participante_referencia="demo-1", cadastrada_por=self.usuario)
            lista = self.consultar()
            self.assertFalse(lista["demonstracao"])
            self.assertEqual([p["nome"] for p in lista["participantes"]], ["Participante integrado fictício"])

    def test_anonimo_sem_conta_persistida_e_permissao_nao_consultam(self):
        sem_acesso = get_user_model().objects.create_user(username="sem_chamada")
        for usuario in (None, AnonymousUser(), sem_acesso, get_user_model()(username="nao_salvo")):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                obter_lista_chamada(usuario=usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk)

    def test_permissao_atual_e_conta_ativa_sao_exigidas(self):
        self.assertTrue(self.usuario.has_perm("atividades.view_inscricao"))
        permissao = Permission.objects.get(content_type__app_label="atividades", codename="view_inscricao")
        self.usuario.user_permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            self.consultar()
        self.usuario.user_permissions.add(permissao)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.consultar()

    def test_aula_cancelada_nao_tem_chamada_nem_consulta_nomes(self):
        Aula.objects.filter(pk=self.aula.pk).update(situacao="cancelada")
        with patch("atividades.services.obter_provedor") as provedor, self.assertRaises(ValidationError):
            self.consultar()
        provedor.assert_not_called()

    def test_interface_mostra_aula_e_participantes_com_aviso_fisico(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(reverse("atividades:aulas", args=[self.atividade.pk])), self.url)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "29/02/2024")
        self.assertContains(resposta, "09:00 às 10:00")
        self.assertContains(resposta, "Participante fictício 1")
        self.assertNotContains(resposta, "Participante fictício 3")
        self.assertContains(resposta, "lista física assinada continua obrigatória")
        self.assertContains(resposta, "Sua conta não tem permissão para lançar frequência")

    def test_interface_so_leitura_post_nao_lanca_frequencia(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(self.url, {"presente": "demo-1"}).status_code, 405)

    def test_interface_anonima_e_sem_permissao(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.usuario.user_permissions.clear()
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 403)
        self.assertNotContains(resposta, "Participante fictício 1", status_code=403)

    def test_interface_nao_permite_aula_de_outra_atividade_ou_id_inexistente(self):
        self.client.force_login(self.usuario)
        for args in ([self.outra.pk, self.aula.pk], [self.atividade.pk, 999999]):
            self.assertEqual(self.client.get(reverse("atividades:chamada", args=args)).status_code, 404)

    def test_interface_nao_exibe_link_de_chamada_para_cancelada(self):
        Aula.objects.filter(pk=self.aula.pk).update(situacao="cancelada")
        self.client.force_login(self.usuario)
        self.assertNotContains(self.client.get(reverse("atividades:aulas", args=[self.atividade.pk])), self.url)
        self.assertContains(self.client.get(self.url), "aula está cancelada")

    @override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorIndisponivel")
    def test_provedor_indisponivel_retorna_503_sem_nomes(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Cadastro de participantes indisponível", status_code=503)
        self.assertNotContains(resposta, "Participante fictício 1", status_code=503)
