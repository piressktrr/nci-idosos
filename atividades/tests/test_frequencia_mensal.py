from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse

from atividades.models import Atividade, Aula, Frequencia, Inscricao, RegistroCorrecaoFrequencia
from atividades.services import consultar_frequencia_mensal, registrar_frequencias, corrigir_frequencia


@override_settings(DEBUG=True)
class FrequenciaMensalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuario = get_user_model().objects.create_user(username="mensal_ficticio")
        cls.usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("view_atividade", "view_aula", "view_frequencia", "view_inscricao",
                          "add_frequencia", "change_frequencia")))
        cls.atividade = Atividade.objects.create(nome="Atividade fictícia", local="Sala", monitor="Fictício")
        cls.outra = Atividade.objects.create(nome="Outra fictícia", local="Sala", monitor="Fictício")
        cls.inscricao = Inscricao.objects.create(atividade=cls.atividade, origem_participante="placeholder",
            participante_referencia="demo-1", cadastrada_por=cls.usuario)
        cls.aula = cls.criar_aula(cls.atividade, date(2024, 2, 1))
        cls.freq = registrar_frequencias(usuario=cls.usuario, atividade_id=cls.atividade.pk,
            aula_id=cls.aula.pk, registros={cls.inscricao.pk: "presente"})[0]
        cls.url = reverse("atividades:frequencia_mensal")

    @staticmethod
    def criar_aula(atividade, data, **kwargs):
        return Aula.objects.create(atividade=atividade, data=data, inicio=time(9), fim=time(10), **kwargs)

    def consultar(self, **kwargs):
        return consultar_frequencia_mensal(**({"usuario": self.usuario, "ano": 2024, "mes": 2} | kwargs))

    def lancar(self, data, situacao):
        aula = self.criar_aula(self.atividade, data)
        return registrar_frequencias(usuario=self.usuario, atividade_id=self.atividade.pk,
            aula_id=aula.pk, registros={self.inscricao.pk: situacao})[0]

    def test_mes_bissexto_limites_e_tres_situacoes_sem_presumir_ausencias(self):
        self.lancar(date(2024, 2, 29), "ausente_justificado")
        self.lancar(date(2024, 2, 15), "ausente")
        self.lancar(date(2024, 1, 31), "presente")
        self.lancar(date(2024, 3, 1), "presente")
        self.criar_aula(self.atividade, date(2024, 2, 20))
        resultado = self.consultar()
        self.assertEqual(resultado["totais"], {"aulas_realizadas": 4, "presentes": 1,
            "ausentes": 1, "justificados": 1, "total_registros": 3})
        self.assertEqual(len(resultado["linhas"]), 2)
        self.assertEqual(resultado["linhas"][1].total_registros, 0)

    def test_presencas_sao_ocorrencias_e_nao_pessoas_unicas(self):
        self.lancar(date(2024, 2, 2), "presente")
        self.assertEqual(self.consultar()["totais"]["presentes"], 2)

    def test_varios_participantes_na_mesma_aula_nao_multiplicam_aulas(self):
        inscricao = Inscricao.objects.create(atividade=self.atividade, origem_participante="placeholder",
            participante_referencia="demo-2", cadastrada_por=self.usuario)
        registrar_frequencias(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk,
            registros={inscricao.pk: "presente"})
        totais = self.consultar()["totais"]
        self.assertEqual((totais["aulas_realizadas"], totais["presentes"]), (1, 2))

    def test_filtro_por_atividade_e_visao_geral(self):
        inscricao = Inscricao.objects.create(atividade=self.outra, origem_participante="placeholder",
            participante_referencia="demo-2", cadastrada_por=self.usuario)
        aula = self.criar_aula(self.outra, date(2024, 2, 3))
        registrar_frequencias(usuario=self.usuario, atividade_id=self.outra.pk, aula_id=aula.pk,
            registros={inscricao.pk: "ausente"})
        self.assertEqual(self.consultar()["totais"]["total_registros"], 2)
        filtrado = self.consultar(atividade_id=self.outra.pk)
        self.assertEqual([item.pk for item in filtrado["linhas"]], [self.outra.pk])
        self.assertEqual(filtrado["totais"]["presentes"], 0)
        self.assertEqual(filtrado["totais"]["ausentes"], 1)
        with self.assertRaises(Atividade.DoesNotExist):
            self.consultar(atividade_id=999999)

    def test_cancelada_com_historico_nao_entra_na_consulta(self):
        Aula.objects.filter(pk=self.aula.pk).update(situacao="cancelada")
        self.assertEqual(self.consultar()["totais"]["total_registros"], 0)
        self.assertEqual(self.consultar()["totais"]["aulas_realizadas"], 0)
        self.assertTrue(Frequencia.objects.filter(pk=self.freq.pk).exists())

    def test_correcao_atual_refletida_preservando_auditoria(self):
        corrigir_frequencia(usuario=self.usuario, atividade_id=self.atividade.pk, aula_id=self.aula.pk,
            frequencia_id=self.freq.pk, versao_esperada=1, situacao="ausente")
        resultado = self.consultar()["totais"]
        self.assertEqual((resultado["presentes"], resultado["ausentes"]), (0, 1))
        self.assertEqual(RegistroCorrecaoFrequencia.objects.count(), 1)

    def test_origens_nao_misturam_mesmo_com_referencia_igual(self):
        real = Inscricao.objects.create(atividade=self.atividade, origem_participante="participantes",
            participante_referencia="demo-1", cadastrada_por=self.usuario)
        Frequencia.objects.create(aula=self.aula, inscricao=real, situacao="ausente")
        self.assertEqual(self.consultar()["totais"]["ausentes"], 0)
        with override_settings(NCI_PARTICIPANTES_PROVIDER="atividades.tests.test_inscricoes.ProvedorAlternativo"):
            resultado = self.consultar()
            self.assertEqual(resultado["totais"]["presentes"], 0)
            self.assertEqual(resultado["totais"]["ausentes"], 1)
            self.assertFalse(resultado["demonstracao"])

    def test_dezembro_ano_limite_e_mes_sem_movimento(self):
        self.lancar(date(9999, 12, 31), "presente")
        self.assertEqual(self.consultar(ano=9999, mes=12)["totais"]["presentes"], 1)
        self.assertEqual(self.consultar(mes=4)["totais"]["total_registros"], 0)
        for ano, mes in ((True, 2), (2024, True), (0, 2), (10000, 2), (2024, 13), (2024, 0), ("2024", 2)):
            with self.subTest(ano=ano, mes=mes), self.assertRaises(ValidationError):
                self.consultar(ano=ano, mes=mes)

    def test_autorizacao_atual_conta_ativa_e_permissoes_individuais(self):
        self.usuario.has_perms(("atividades.view_atividade", "atividades.view_aula", "atividades.view_frequencia"))
        for codename in ("view_atividade", "view_aula", "view_frequencia"):
            permissao = Permission.objects.get(content_type__app_label="atividades", codename=codename)
            self.usuario.user_permissions.remove(permissao)
            with self.assertRaises(PermissionDenied):
                self.consultar()
            self.usuario.user_permissions.add(permissao)
        get_user_model().objects.filter(pk=self.usuario.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.consultar()
        with self.assertRaises(PermissionDenied):
            self.consultar(usuario=AnonymousUser())

    def test_interface_filtros_totais_escape_e_sem_escrita(self):
        self.client.force_login(self.usuario)
        Atividade.objects.filter(pk=self.atividade.pk).update(nome="<script>fictício</script>")
        antes = (Frequencia.objects.count(), Aula.objects.count(), RegistroCorrecaoFrequencia.objects.count())
        resposta = self.client.get(self.url, {"mes": "2024-02", "atividade": self.atividade.pk})
        self.assertContains(resposta, "&lt;script&gt;fictício&lt;/script&gt;")
        self.assertContains(resposta, "participantes fictícios")
        self.assertEqual(resposta.context["totais"]["presentes"], 1)
        self.assertEqual(antes, (Frequencia.objects.count(), Aula.objects.count(), RegistroCorrecaoFrequencia.objects.count()))

    def test_mes_padrao_local_filtros_invalidos_e_vazio(self):
        self.client.force_login(self.usuario)
        with patch("atividades.views.frequencia.timezone.localdate", return_value=date(2024, 2, 1)):
            self.assertEqual(self.client.get(self.url).context["totais"]["presentes"], 1)
        for dados in ({"mes": "2024-13"}, {"mes": ""}, {"mes": "2024-02-01"},
                      {"mes": "2024-02", "atividade": 999999}):
            resposta = self.client.get(self.url, dados)
            self.assertTrue(resposta.context["form"].errors)
            self.assertNotIn("totais", resposta.context)
        resposta = self.client.get(self.url, {"mes": "2024-04"})
        self.assertContains(resposta, "Nenhuma frequência lançada")

    def test_http_autenticacao_permissao_metodo_e_link(self):
        self.assertEqual(self.client.get(self.url).status_code, 302)
        self.client.force_login(self.usuario)
        self.assertContains(self.client.get(reverse("atividades:lista")), self.url)
        self.assertEqual(self.client.post(self.url).status_code, 405)
        self.usuario.user_permissions.clear()
        self.assertEqual(self.client.get(self.url).status_code, 403)

    @override_settings(DEBUG=False)
    def test_placeholder_indisponivel_em_producao(self):
        self.client.force_login(self.usuario)
        resposta = self.client.get(self.url, {"mes": "2024-02"})
        self.assertEqual(resposta.status_code, 503)
        self.assertNotIn("totais", resposta.context)
