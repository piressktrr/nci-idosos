from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from atividades.models import Atividade, Aula, Inscricao, Frequencia, MotivoFalta, RegistroCorrecaoFrequencia
from atividades.services import registrar_frequencias, corrigir_frequencia, consultar_frequencia


@override_settings(DEBUG=True)
class CorrecaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="correcao_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades", codename__in=(
            "view_atividade", "view_aula", "view_inscricao", "view_frequencia", "add_frequencia", "change_frequencia",
        )))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra fictícia", local="Sala", monitor="Fictício")
        cls.aula = Aula.objects.create(atividade=cls.atividade, data=date(2024, 2, 29), inicio=time(9), fim=time(10))
        cls.inscricao = Inscricao.objects.create(atividade=cls.atividade, origem_participante="placeholder",
                                               participante_referencia="demo-1", cadastrada_por=cls.usuario)
        cls.freq = registrar_frequencias(usuario=cls.usuario, atividade_id=cls.atividade.pk, aula_id=cls.aula.pk,
                                        registros={cls.inscricao.pk: "presente"})[0]
        cls.motivo = MotivoFalta.objects.create(descricao="Motivo fictício")
        cls.outro_motivo = MotivoFalta.objects.create(descricao="Outro fictício", ativo=False)
        cls.url = reverse("atividades:detalhe_frequencia", args=[cls.atividade.pk, cls.aula.pk, cls.freq.pk])

    def corrigir(self, **dados):
        return corrigir_frequencia(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk,
            frequencia_id=self.freq.pk, **({"versao_esperada": 1, "situacao": "ausente"} | dados))

    def test_preserva_lancamento_original_e_grava_antes_depois_autor_data(self):
        original = self.freq.registro_lancamento.dados.copy()
        frequencia = self.corrigir()
        self.assertEqual(frequencia.situacao, "ausente")
        self.assertEqual(frequencia.versao, 2)
        evento = frequencia.correcoes.get()
        self.assertEqual(evento.anteriores["situacao"], "presente")
        self.assertEqual(evento.novos["situacao"], "ausente")
        self.assertEqual(evento.usuario_id, self.usuario.pk)
        self.assertIsNotNone(evento.registrado_em)
        self.assertEqual(frequencia.registro_lancamento.dados, original)
        self.assertEqual(frequencia.aula.data, date(2024, 2, 29))

    def test_varias_correcoes_formam_cadeia_e_sem_alteracao_nao_cria_evento(self):
        self.corrigir()
        self.corrigir(versao_esperada=2, situacao="presente")
        self.corrigir(versao_esperada=3, situacao="presente")
        eventos = list(self.freq.correcoes.all())
        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[1].anteriores, eventos[0].novos)

    def test_formulario_antigo_nao_sobrescreve_correcao_mais_recente(self):
        self.corrigir()
        with self.assertRaises(ValidationError):
            self.corrigir(situacao="presente")
        self.freq.refresh_from_db()
        self.assertEqual(self.freq.situacao, "ausente")
        self.assertEqual(self.freq.correcoes.count(), 1)

    def test_justificativa_e_remocao_sao_auditadas(self):
        self.corrigir(situacao="ausente_justificado", motivo_id=self.motivo.pk, observacao="Nota fictícia")
        self.corrigir(versao_esperada=2, situacao="presente")
        self.freq.refresh_from_db()
        self.assertIsNone(self.freq.motivo_id)
        self.assertEqual(self.freq.observacao, "")
        ultimo = self.freq.correcoes.last()
        self.assertEqual(ultimo.anteriores["observacao"], "Nota fictícia")
        self.assertEqual(ultimo.novos["motivo_descricao"], "")

    def test_motivo_ja_associado_pode_ser_mantido_inativo_sem_trocar_snapshot(self):
        self.corrigir(situacao="ausente_justificado", motivo_id=self.motivo.pk)
        MotivoFalta.objects.filter(pk=self.motivo.pk).update(ativo=False, descricao="Renomeado")
        self.corrigir(versao_esperada=2, situacao="ausente_justificado", motivo_id=self.motivo.pk, observacao="Nova nota")
        self.freq.refresh_from_db()
        self.assertEqual(self.freq.motivo_descricao, "Motivo fictício")

    def test_motivo_novo_inativo_status_invalido_e_detalhes_incompativeis_rejeitados(self):
        for dados in ({"situacao": "invalida"}, {"situacao": "ausente_justificado", "motivo_id": self.outro_motivo.pk},
                      {"observacao": "Nota"}, {"situacao": "ausente_justificado", "observacao": "x" * 1001},
                      {"versao_esperada": True}):
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                self.corrigir(**dados)
        self.assertFalse(RegistroCorrecaoFrequencia.objects.exists())

    def test_falha_na_auditoria_reverte_frequencia_e_versao(self):
        with patch("atividades.services.RegistroCorrecaoFrequencia.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.corrigir()
        self.freq.refresh_from_db()
        self.assertEqual(self.freq.situacao, "presente")
        self.assertEqual(self.freq.versao, 1)

    def test_permissao_de_correcao_e_separada_da_de_lancamento(self):
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="add_frequencia"))
        self.corrigir()
        self.assertEqual(self.freq.correcoes.count(), 1)

    def test_permissao_revogada_e_usuario_inativo_nao_corrigem(self):
        self.assertTrue(self.usuario.has_perm("atividades.change_frequencia"))
        permissao = Permission.objects.get(content_type__app_label="atividades", codename="change_frequencia")
        self.usuario.user_permissions.remove(permissao)
        with self.assertRaises(PermissionDenied):
            self.corrigir()
        self.usuario.user_permissions.add(permissao)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.corrigir()

    def test_anonimo_e_vinculo_incorreto_nao_acessam(self):
        with self.assertRaises(PermissionDenied):
            consultar_frequencia(usuario=AnonymousUser(), atividade_id=self.atividade.pk, aula_id=self.aula.pk, frequencia_id=self.freq.pk)
        with self.assertRaises(Frequencia.DoesNotExist):
            consultar_frequencia(usuario=self.usuario, atividade_id=self.outra.pk, aula_id=self.aula.pk, frequencia_id=self.freq.pk)
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorAlternativo"):
            with self.assertRaises(Frequencia.DoesNotExist):
                self.corrigir()

    def test_correcao_historica_nao_restaura_aula_cancelada(self):
        Aula.objects.filter(pk=self.aula.pk).update(situacao="cancelada")
        self.corrigir()
        self.aula.refresh_from_db()
        self.assertEqual(self.aula.situacao, "cancelada")
        self.assertFalse(Aula.objects.realizadas().exists())

    def test_interface_exibe_historico_corrige_e_rejeita_reenvio_antigo(self):
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(self.url), "Lançamento inicial")
        dados = {"situacao": "ausente", "versao_esperada": 1}
        resposta = self.client.post(self.url, dados, follow=True)
        self.assertContains(resposta, "Correção registrada com sucesso")
        self.assertContains(resposta, "Correção 1")
        self.assertContains(resposta, self.usuario.username)
        resposta = self.client.post(self.url, dados)
        self.assertContains(resposta, "Este registro foi alterado")
        self.assertEqual(self.freq.correcoes.count(), 1)

    def test_somente_leitura_ve_historico_mas_nao_pode_corrigir(self):
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="change_frequencia"))
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Lançamento inicial")
        self.assertNotContains(resposta, "Salvar correção")
        self.assertEqual(self.client.post(self.url, {"situacao": "ausente", "versao_esperada": 1}).status_code, 403)

    def test_csrf_e_ids_adulterados_na_interface(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        dados = {"situacao": "ausente", "versao_esperada": 1}
        self.assertEqual(client.post(self.url, dados).status_code, 403)
        client.get(self.url)
        token = client.cookies["csrftoken"].value
        self.assertEqual(client.post(self.url, dados | {"csrfmiddlewaretoken": token}).status_code, 302)
        errado = reverse("atividades:detalhe_frequencia", args=[self.outra.pk, self.aula.pk, self.freq.pk])
        self.assertEqual(client.get(errado).status_code, 404)

    def test_modo_correcao_oculta_links_por_padrao_e_exibe_somente_quando_ativado(self):
        self.client.force_login(self.usuario)
        chamada = reverse("atividades:chamada", args=[self.atividade.pk, self.aula.pk])
        resposta = self.client.get(chamada)
        self.assertContains(resposta, "Ativar modo de correção")
        self.assertNotContains(resposta, self.url)
        resposta = self.client.get(chamada, {"correcao": "1"})
        self.assertContains(resposta, self.url)
        self.assertContains(resposta, "Desativar modo de correção")
        self.assertNotContains(self.client.get(chamada), self.url)
        self.assertFalse(RegistroCorrecaoFrequencia.objects.exists())

    def test_modo_nao_concede_permissao_de_correcao_por_parametro(self):
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="change_frequencia"))
        self.client.force_login(self.usuario)
        chamada = reverse("atividades:chamada", args=[self.atividade.pk, self.aula.pk])
        resposta = self.client.get(chamada, {"correcao": "1"})
        self.assertNotContains(resposta, self.url)
        self.assertNotContains(resposta, "Ativar modo de correção")
        self.assertFalse(resposta.context["modo_correcao"])
