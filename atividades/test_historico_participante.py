from datetime import date, time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Atividade, Aula, Inscricao, Frequencia, RegistroCorrecaoFrequencia
from .services import consultar_historico_participante, registrar_frequencias, corrigir_frequencia


@override_settings(DEBUG=True)
class HistoricoParticipanteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="historico_ficticio")
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("view_atividade", "view_aula", "view_inscricao", "view_frequencia", "add_frequencia", "change_frequencia")))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala", monitor="Fictício")
        cls.inscricao = Inscricao.objects.create(atividade=cls.atividade, origem_participante="placeholder",
            participante_referencia="demo-1", cadastrada_por=cls.usuario)
        cls.aula = Aula.objects.create(atividade=cls.atividade, data=date(2024, 2, 29), inicio=time(9), fim=time(10))
        cls.freq = registrar_frequencias(usuario=cls.usuario, atividade_id=cls.atividade.pk,
            aula_id=cls.aula.pk, registros={cls.inscricao.pk: "presente"})[0]
        cls.url = reverse("atividades:historico_participante", args=[cls.atividade.pk, cls.inscricao.pk])

    def consultar(self, **kwargs):
        return consultar_historico_participante(**({"usuario": self.usuario, "atividade_id": self.atividade.pk,
            "inscricao_id": self.inscricao.pk} | kwargs))

    def test_todas_situacoes_ordenacao_data_ocorrencia_e_total(self):
        for dia, situacao in ((1, "presente"), (2, "ausente"), (3, "ausente_justificado")):
            aula = Aula.objects.create(atividade=self.atividade, data=date(2023, 1, dia), inicio=time(9), fim=time(10))
            Frequencia.objects.create(aula=aula, inscricao=self.inscricao, situacao=situacao)
        resultado = self.consultar()
        self.assertEqual(resultado["total_presencas"], 2)
        self.assertEqual([item.aula.data for item in resultado["frequencias"]],
            [date(2024, 2, 29), date(2023, 1, 3), date(2023, 1, 2), date(2023, 1, 1)])

    def test_cancelada_permanece_no_historico_fora_do_total(self):
        Aula.objects.filter(pk=self.aula.pk).update(situacao="cancelada")
        resultado = self.consultar()
        self.assertEqual(resultado["total_presencas"], 0)
        self.assertEqual(resultado["frequencias"].get().pk, self.freq.pk)
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(self.url), "Cancelada")

    def test_correcao_atual_refletida_sem_modificar_original(self):
        corrigir_frequencia(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk,
            frequencia_id=self.freq.pk, versao_esperada=1, situacao="ausente")
        resultado = self.consultar()
        self.assertEqual(resultado["total_presencas"], 0)
        self.assertEqual(resultado["frequencias"].get().situacao, "ausente")
        self.assertEqual(self.freq.registro_lancamento.dados["situacao"], "presente")

    def test_isolamento_inscricao_atividade_e_origem(self):
        outra = Atividade.objects.create(nome="Outra", local="Sala", monitor="Fictício")
        with self.assertRaises(Inscricao.DoesNotExist):
            self.consultar(atividade_id=outra.pk)
        outra_inscricao = Inscricao.objects.create(atividade=self.atividade, origem_participante="placeholder",
            participante_referencia="demo-2", cadastrada_por=self.usuario)
        Frequencia.objects.create(aula=self.aula, inscricao=outra_inscricao, situacao="presente")
        self.assertEqual(self.consultar()["total_presencas"], 1)
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.test_inscricoes.ProvedorAlternativo"):
            with self.assertRaises(Inscricao.DoesNotExist):
                self.consultar()

    def test_identidade_indisponivel_preserva_historico(self):
        Inscricao.objects.filter(pk=self.inscricao.pk).update(participante_referencia="removido-ficticio")
        resultado = self.consultar()
        self.assertEqual(resultado["nome"], "Participante indisponível")
        self.assertEqual(resultado["total_presencas"], 1)

    def test_sem_lancamentos_nao_inventa_faltas(self):
        inscricao = Inscricao.objects.create(atividade=self.atividade, origem_participante="placeholder",
            participante_referencia="demo-3", cadastrada_por=self.usuario)
        resultado = self.consultar(inscricao_id=inscricao.pk)
        self.assertEqual(resultado["total_presencas"], 0)
        self.assertFalse(resultado["frequencias"].exists())

    def test_permissoes_atuais_e_conta_desativada(self):
        self.usuario.has_perm("atividades.view_frequencia")
        for codename in ("view_atividade", "view_aula", "view_inscricao", "view_frequencia"):
            perm = Permission.objects.get(content_type__app_label="atividades", codename=codename)
            self.usuario.user_permissions.remove(perm)
            with self.assertRaises(PermissionDenied):
                self.consultar()
            self.usuario.user_permissions.add(perm)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.consultar()
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())

    def test_interface_justificativa_escape_hhmm_e_sem_escrita(self):
        Frequencia.objects.filter(pk=self.freq.pk).update(situacao="ausente_justificado",
            motivo_descricao="Motivo histórico", observacao="<script>fictício</script>")
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertContains(resposta, "Motivo histórico")
        self.assertContains(resposta, "&lt;script&gt;fictício&lt;/script&gt;")
        self.assertContains(resposta, "09:00–10:00")
        self.assertNotContains(resposta, "09:00:00")
        self.assertEqual(Frequencia.objects.count(), 1)
        self.assertEqual(RegistroCorrecaoFrequencia.objects.count(), 0)
        self.assertContains(self.client.get(reverse("atividades:inscricoes", args=[self.atividade.pk])), self.url)

    def test_paginacao_mantem_total_de_todo_historico(self):
        for dia in range(1, 22):
            aula = Aula.objects.create(atividade=self.atividade, data=date(2024, 1, dia), inicio=time(9), fim=time(10))
            Frequencia.objects.create(aula=aula, inscricao=self.inscricao, situacao="presente")
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url, {"page": 2})
        self.assertEqual(resposta.context["total_presencas"], 22)
        self.assertEqual(len(resposta.context["pagina"]), 2)

    def test_http_login_permissoes_metodos_e_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.usuario)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.assertEqual(self.client.get(reverse("atividades:historico_participante", args=[self.atividade.pk, 99999])).status_code, 404)
        self.usuario.user_permissions.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    @override_settings(DEBUG=False)
    def test_placeholder_indisponivel(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url)
        self.assertEqual(resposta.status_code, 503)
        self.assertNotContains(resposta, "Participante fictício", status_code=503)
