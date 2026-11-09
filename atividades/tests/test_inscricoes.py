from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import ImproperlyConfigured, PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from atividades.integracoes.participantes import ParticipanteResumo, obter_provedor
from atividades.models import Atividade, Inscricao
from atividades.services import inscrever_participante


class ProvedorAlternativo:
    """Simula somente o contrato do colega, sem implementar seu módulo."""
    origem = "participantes"
    demonstracao = False
    participantes = (ParticipanteResumo("demo-1", "Participante integrado fictício"),)

    def listar(self):
        return self.participantes

    def obter(self, referencia):
        return next((item for item in self.participantes if item.referencia == referencia), None)


class ProvedorRemovido(ProvedorAlternativo):
    def obter(self, referencia):
        return None


class ProvedorVazio(ProvedorAlternativo):
    participantes = ()


class ProvedorIndisponivel:
    def __init__(self):
        raise ImproperlyConfigured("Integração não configurada")


@override_settings(DEBUG=True)
class InscricaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="inscricoes_ficticias")
        cls.usuario.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="atividades", codename__in=("view_atividade", "view_inscricao", "add_inscricao")
        ))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala de teste", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra fictícia", local="Sala de teste", monitor="Fictício")
        cls.url = reverse("atividades:inscricoes", args=[cls.atividade.pk])

    def inscrever(self, referencia="demo-1", atividade=None):
        return inscrever_participante(usuario=self.usuario, atividade_id=(atividade or self.atividade).pk,
                                      participante_referencia=referencia)

    def test_inscricao_valida_persiste_apenas_vinculo_com_usuario_e_data(self):
        inscricao = self.inscrever()
        inscricao.refresh_from_db()
        self.assertEqual(inscricao.atividade_id, self.atividade.pk)
        self.assertEqual(inscricao.participante_referencia, "demo-1")
        self.assertEqual(inscricao.origem_participante, "placeholder")
        self.assertEqual(inscricao.cadastrada_por_id, self.usuario.pk)
        self.assertIsNotNone(inscricao.cadastrada_em)
        self.assertNotIn("nome", {campo.name for campo in Inscricao._meta.fields})

    def test_participante_pode_se_inscrever_em_atividades_diferentes(self):
        self.inscrever()
        self.inscrever(atividade=self.outra)
        self.assertEqual(Inscricao.objects.count(), 2)

    def test_duplicidade_na_mesma_atividade_e_rejeitada_sem_alterar_auditoria(self):
        inscricao = self.inscrever()
        with self.assertRaises(ValidationError):
            self.inscrever()
        self.assertEqual(Inscricao.objects.count(), 1)
        inscricao.refresh_from_db()
        self.assertEqual(inscricao.cadastrada_por_id, self.usuario.pk)

    def test_referencias_invalidas_ou_inexistentes_nao_criam_inscricao(self):
        for referencia in (None, "", "  ", 123, "x" * 65, "nao-cadastrado"):
            with self.subTest(referencia=referencia), self.assertRaises(ValidationError):
                self.inscrever(referencia)
        self.assertFalse(Inscricao.objects.exists())

    def test_anonimo_nao_persistido_e_sem_permissao_nao_inscrevem(self):
        sem_acesso = get_user_model().objects.create_user(username="inscricao_sem_acesso")
        for usuario in (None, AnonymousUser(), get_user_model()(username="nao_salvo"), sem_acesso):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                inscrever_participante(usuario=usuario, atividade_id=self.atividade.pk, participante_referencia="demo-1")
        self.assertFalse(Inscricao.objects.exists())

    def test_conta_desativada_e_permissao_revogada_nao_sao_aceitas_por_cache(self):
        self.assertTrue(self.usuario.has_perm("atividades.add_inscricao"))
        permissao = Permission.objects.get(content_type__app_label="atividades", codename="add_inscricao")
        self.usuario.user_permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            self.inscrever()
        self.usuario.user_permissions.add(permissao)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.inscrever()
        self.assertFalse(Inscricao.objects.exists())

    def test_atividade_inexistente_nao_inscreve(self):
        with self.assertRaises(Atividade.DoesNotExist):
            inscrever_participante(usuario=self.usuario, atividade_id=999999, participante_referencia="demo-1")
        self.assertFalse(Inscricao.objects.exists())

    def test_erro_apos_gravacao_reverte_a_transacao(self):
        original = Inscricao.save

        def salvar_e_falhar(instancia, *args, **kwargs):
            original(instancia, *args, **kwargs)
            raise RuntimeError("Falha de teste")

        with patch.object(Inscricao, "save", salvar_e_falhar), self.assertRaises(RuntimeError):
            self.inscrever()
        self.assertFalse(Inscricao.objects.exists())

    def test_banco_impede_duplicacao_mesmo_fora_do_servico(self):
        inscricao = self.inscrever()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Inscricao.objects.create(atividade=self.atividade, origem_participante="placeholder",
                                     participante_referencia=inscricao.participante_referencia, cadastrada_por=self.usuario)

    @override_settings(DEBUG=False)
    def test_placeholder_nao_funciona_fora_de_desenvolvimento(self):
        with self.assertRaises(ImproperlyConfigured):
            self.inscrever()
        self.assertFalse(Inscricao.objects.exists())

    @override_settings(DEBUG=False, NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorAlternativo")
    def test_provedor_substituivel_sem_mudar_servico_ou_tela(self):
        inscricao = self.inscrever()
        self.assertEqual(inscricao.origem_participante, "participantes")
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Participante integrado fictício")
        self.assertNotContains(resposta, "Demonstração:")

    def test_origem_separa_inscricoes_de_demo_e_identificadores_reais(self):
        self.inscrever()
        self.client.force_login(self.usuario)
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorAlternativo"):
            self.assertContains(self.client.get(self.url), "Nenhuma inscrição registrada")
            self.inscrever()
            resposta = self.client.get(self.url)
            self.assertEqual(resposta.context["pagina"].paginator.count, 1)
            self.assertContains(resposta, "Participante integrado fictício")
        self.assertEqual(Inscricao.objects.count(), 2)

    @override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorRemovido")
    def test_participante_removido_entre_listagem_e_envio_nao_e_inscrito(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.url, {"participante_referencia": "demo-1"})
        self.assertContains(resposta, "Participante não encontrado")
        self.assertFalse(Inscricao.objects.exists())

    def test_interface_inscreve_e_exibe_vinculo_sem_repetir_em_refresh(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(reverse("atividades:lista")), self.url)
        self.assertContains(self.client.get(self.url), "participantes desta tela são fictícios")
        resposta = self.client.post(self.url, {"participante_referencia": "demo-1"}, follow=True)
        self.assertContains(resposta, "Inscrição registrada com sucesso")
        self.assertContains(resposta, "<td>Participante fictício 1</td>", html=True)
        self.client.get(self.url)
        self.assertEqual(Inscricao.objects.count(), 1)
        resposta = self.client.post(self.url, {"participante_referencia": "demo-1"})
        self.assertContains(resposta, "já está inscrito")
        self.assertEqual(Inscricao.objects.count(), 1)

    def test_interface_invalida_e_isolamento_da_atividade(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(self.url, {"participante_referencia": "forjado"}).status_code, 200)
        self.assertFalse(Inscricao.objects.exists())
        self.inscrever(atividade=self.outra)
        self.assertContains(self.client.get(self.url), "Nenhuma inscrição registrada")

    def test_interface_anonima_sem_acesso_e_somente_leitura(self):
        for metodo in (self.client.get, self.client.post):
            self.assertEqual(metodo(self.url).status_code, 302)
        self.usuario.user_permissions.remove(Permission.objects.get(
            content_type__app_label="atividades", codename="add_inscricao"
        ))
        self.client.force_login(self.usuario)
        self.assertNotContains(self.client.get(self.url), "Registrar inscrição")
        self.assertEqual(self.client.post(self.url, {"participante_referencia": "demo-1"}).status_code, 403)
        self.usuario.user_permissions.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_csrf_na_inscricao(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        dados = {"participante_referencia": "demo-1"}
        self.assertEqual(client.post(self.url, dados).status_code, 403)
        self.assertFalse(Inscricao.objects.exists())
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.url, dados | {"csrfmiddlewaretoken": token}).status_code, 302)

    @override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorIndisponivel")
    def test_provedor_indisponivel_exibe_503_sem_dados_ou_escrita(self):
        self.client.force_login(self.usuario)
        for metodo in (self.client.get, self.client.post):
            resposta = metodo(self.url, {"participante_referencia": "demo-1"})
            self.assertContains(resposta, "Cadastro de participantes indisponível", status_code=503)
        self.assertFalse(Inscricao.objects.exists())

    def test_referencia_indisponivel_preserva_inscricao_ao_trocar_cadastro(self):
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorAlternativo"):
            inscricao = self.inscrever()
        self.client.force_login(self.usuario)
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorVazio"):
            self.assertContains(self.client.get(self.url), "Participante indisponível")
        self.assertTrue(Inscricao.objects.filter(pk=inscricao.pk).exists())

    @override_settings(DEBUG=False, NCI_PARTICIPANTES_PROVIDER="atividades.integracoes.participantes_placeholder.ProvedorPlaceholder")
    def test_configuracao_explicita_nao_libera_placeholder_em_producao(self):
        with self.assertRaises(ImproperlyConfigured):
            obter_provedor()
