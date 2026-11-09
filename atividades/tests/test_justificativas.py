from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from atividades.models import Atividade, Aula, Inscricao, Frequencia, MotivoFalta, RegistroMotivoFalta, RegistroLancamentoFrequencia
from atividades.services import registrar_frequencias, salvar_motivo_falta


@override_settings(DEBUG=True)
class JustificativaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="justificativa_ficticia")
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades", codename__in=(
            "view_atividade", "view_aula", "view_inscricao", "view_frequencia", "add_frequencia",
            "view_motivofalta", "add_motivofalta", "change_motivofalta",
        )))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala", monitor="Fictício")
        cls.aula = Aula.objects.create(atividade=cls.atividade, data=date(2024, 2, 29), inicio=time(9), fim=time(10))
        cls.inscricao = Inscricao.objects.create(atividade=cls.atividade, origem_participante="placeholder",
                                               participante_referencia="demo-1", cadastrada_por=cls.usuario)
        cls.motivo = MotivoFalta.objects.create(descricao="Motivo fictício para teste")
        cls.inativo = MotivoFalta.objects.create(descricao="Motivo desativado fictício", ativo=False)
        cls.url = reverse("atividades:chamada", args=[cls.atividade.pk, cls.aula.pk])
        cls.post_url = reverse("atividades:lancar_frequencias", args=[cls.atividade.pk, cls.aula.pk])
        cls.catalogo = reverse("atividades:motivos_falta")

    def lancar(self, dados=None, situacao="ausente_justificado"):
        return registrar_frequencias(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk,
            registros={self.inscricao.pk: situacao}, justificativas={self.inscricao.pk: dados} if dados is not None else None)

    def post(self, **alteracoes):
        i = self.inscricao.pk
        return {f"registro_{i}": "ausente_justificado", f"motivo_{i}": str(self.motivo.pk),
                f"observacao_{i}": "Observação fictícia", **alteracoes}

    def test_motivo_observacao_e_auditoria_persistem_juntos(self):
        freq = self.lancar({"motivo_id": self.motivo.pk, "observacao": "  Observação fictícia  "})[0]
        freq.refresh_from_db()
        self.assertEqual(freq.motivo_id, self.motivo.pk)
        self.assertEqual(freq.motivo_descricao, self.motivo.descricao)
        self.assertEqual(freq.observacao, "Observação fictícia")
        self.assertEqual(freq.registro_lancamento.dados["motivo_id"], self.motivo.pk)
        self.assertEqual(freq.registro_lancamento.dados["observacao"], freq.observacao)

    def test_justificada_sem_detalhes_mantem_contrato_opcional(self):
        freq = self.lancar()[0]
        self.assertIsNone(freq.motivo_id)
        self.assertEqual(freq.observacao, "")

    def test_motivo_inativo_inexistente_ou_malformado_nao_grava(self):
        for motivo_id in (self.inativo.pk, 999999, "texto", True):
            with self.subTest(motivo_id=motivo_id), self.assertRaises(ValidationError):
                self.lancar({"motivo_id": motivo_id})
        self.assertFalse(Frequencia.objects.exists())

    def test_detalhes_invalidos_ou_incompativeis_nao_gravam(self):
        for dados in ({"observacao": 123}, {"observacao": "x" * 1001}, {"campo_inventado": "x"}):
            with self.subTest(dados=dados), self.assertRaises(ValidationError):
                self.lancar(dados)
        with self.assertRaises(ValidationError):
            self.lancar({"motivo_id": self.motivo.pk}, situacao="presente")
        self.assertFalse(Frequencia.objects.exists())

    def test_catalogo_editavel_auditado_preserva_descricao_original_da_frequencia(self):
        motivo = salvar_motivo_falta(usuario=self.usuario, descricao="  Outro motivo fictício  ")
        self.assertEqual(motivo.descricao, "Outro motivo fictício")
        self.assertIsNone(RegistroMotivoFalta.objects.get(motivo=motivo).anteriores)
        freq = self.lancar({"motivo_id": self.motivo.pk})[0]
        salvar_motivo_falta(usuario=self.usuario, motivo_id=self.motivo.pk, descricao="Motivo renomeado", ativo=False)
        freq.refresh_from_db()
        self.assertEqual(freq.motivo_descricao, "Motivo fictício para teste")
        self.assertEqual(freq.registro_lancamento.dados["motivo_descricao"], freq.motivo_descricao)
        evento = RegistroMotivoFalta.objects.get(motivo=self.motivo)
        self.assertTrue(evento.anteriores["ativo"])
        self.assertFalse(evento.novos["ativo"])

    def test_catalogo_valida_descricao_e_situacao(self):
        for descricao in (" ", "x" * 151, None):
            with self.subTest(descricao=descricao), self.assertRaises(ValidationError):
                salvar_motivo_falta(usuario=self.usuario, descricao=descricao)
        self.assertFalse(RegistroMotivoFalta.objects.exists())

    def test_catalogo_exige_permissao_atual_e_conta_ativa(self):
        self.assertTrue(self.usuario.has_perm("atividades.change_motivofalta"))
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="change_motivofalta"))
        with self.assertRaises(PermissionDenied):
            salvar_motivo_falta(usuario=self.usuario, motivo_id=self.motivo.pk, descricao="Tentativa")
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            salvar_motivo_falta(usuario=self.usuario, descricao="Tentativa")

    def test_falha_na_auditoria_reverte_catalogo_e_frequencia(self):
        with patch("atividades.services.RegistroMotivoFalta.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                salvar_motivo_falta(usuario=self.usuario, motivo_id=self.motivo.pk, descricao="Alteração temporária")
        self.motivo.refresh_from_db()
        self.assertEqual(self.motivo.descricao, "Motivo fictício para teste")
        with patch("atividades.services.RegistroLancamentoFrequencia.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.lancar({"motivo_id": self.motivo.pk})
        self.assertFalse(Frequencia.objects.exists())

    def test_interface_lanca_e_exibe_justificativa_sem_editar_lancados(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.post_url, self.post(), follow=True)
        self.assertContains(resposta, "Motivo fictício para teste")
        self.assertContains(resposta, "Observação fictícia")
        self.assertEqual(Frequencia.objects.get().motivo_id, self.motivo.pk)
        self.assertNotContains(resposta, f'name="observacao_{self.inscricao.pk}"')

    def test_interface_rejeita_motivo_inativo_e_mantem_observacao_apos_erro(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.post_url, self.post(**{f"motivo_{self.inscricao.pk}": str(self.inativo.pk)}))
        self.assertTrue(resposta.context["form"].errors)
        self.assertContains(resposta, "Observação fictícia")
        self.assertFalse(Frequencia.objects.exists())

    def test_interface_nao_descarta_detalhes_quando_situacao_nao_justificada(self):
        self.client.force_login(self.usuario)
        resposta = self.client.post(self.post_url, self.post(**{f"registro_{self.inscricao.pk}": "presente"}))
        self.assertTrue(resposta.context["form"].errors)
        self.assertFalse(Frequencia.objects.exists())

    def test_observacao_html_e_escapada_na_leitura(self):
        self.lancar({"observacao": "<script>alert(1)</script>"})
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "&lt;script&gt;")
        self.assertNotContains(resposta, "<script>alert(1)</script>")

    def test_interface_catalogo_cadastra_edita_e_desativa(self):
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(self.catalogo, {"descricao": "Motivo da interface", "ativo": "on"}).status_code, 302)
        motivo = MotivoFalta.objects.get(descricao="Motivo da interface")
        url = reverse("atividades:editar_motivo_falta", args=[motivo.pk])
        self.assertEqual(self.client.post(url, {"descricao": "Motivo alterado"}).status_code, 302)
        motivo.refresh_from_db()
        self.assertFalse(motivo.ativo)
        self.assertEqual(RegistroMotivoFalta.objects.filter(motivo=motivo).count(), 2)

    def test_catalogo_somente_leitura_nao_altera_e_csrf_e_obrigatorio(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.usuario)
        self.assertEqual(client.post(self.catalogo, {"descricao": "Teste"}).status_code, 403)
        self.usuario.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="add_motivofalta"))
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.get(self.catalogo).status_code, 200)
        self.assertEqual(self.client.post(self.catalogo, {"descricao": "Teste"}).status_code, 403)
