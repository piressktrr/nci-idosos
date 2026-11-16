from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from participantes.categorias import StatusParticipante, TipoMovimentacao
from participantes.models import Movimentacao, Participante, SituacaoSocial
from participantes.services import cadastrar_participante, registrar_situacao_social

PERMISSOES_ATIVIDADES = ("view_atividade", "view_aula", "view_inscricao", "view_frequencia")

# Dados fictícios (RN-SEG-02).
POST_FICTICIO = {
    "nome_completo": "Josefa Exemplo Ficticia", "endereco": "Rua Ficticia, 10",
    "identidade_genero": "mulher_cis", "origem_encaminhamento": "cras", "observacao_encaminhamento": "",
    "telefone_residencial": "", "telefone_celular": "(11) 91234-5678", "data_nascimento": "1950-03-10",
    "raca_cor": "parda", "sexo": "F", "ensino_medio_completo": "True", "data_entrada": "2024-01-15",
}


def _dados_servico(**extra):
    return {"nome_completo": "Ana Ficticia Souza", "data_nascimento": date(1948, 6, 1), "sexo": "F",
            "raca_cor": "branca", "identidade_genero": "mulher_cis", "telefone_celular": "11912345678",
            "telefone_residencial": "", "origem_encaminhamento": "cras", "endereco": "Rua Ficticia, 1",
            "ensino_medio_completo": True, "observacao_encaminhamento": "", "data_entrada": date(2024, 2, 1),
            **extra}


def _usuario(username, *codenames, app="participantes", **extra):
    usuario = get_user_model().objects.create_user(username=username, **extra)
    if codenames:
        usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label=app, codename__in=codenames))
    return usuario


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.gestor = _usuario("gestor_ficticio", "view_participante", "add_participante", "change_participante")
        cls.participante = cadastrar_participante(usuario=cls.gestor, **_dados_servico())

    def urls(self):
        pk = self.participante.pk
        return {
            "lista": reverse("participantes:lista"),
            "novo": reverse("participantes:cadastrar"),
            "detalhe": reverse("participantes:detalhe", args=[pk]),
            "corrigir": reverse("participantes:corrigir", args=[pk]),
            "situacao": reverse("participantes:situacao_social", args=[pk]),
        }


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class AcessoTests(Base):
    """RNF-SEG-03 e RNF-SEG-04."""

    def test_anonimo_vai_para_entrar(self):
        for nome, url in self.urls().items():
            with self.subTest(url=nome):
                resposta = self.client.get(url)
                self.assertRedirects(resposta, f"{reverse('entrar')}?next={url}", fetch_redirect_response=False)
                self.assertTrue(resposta["Location"].startswith("/entrar/"))

    def test_anonimo_post_nao_cadastra(self):
        total = Participante.objects.count()
        resposta = self.client.post(self.urls()["novo"], POST_FICTICIO)
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(resposta["Location"].startswith("/entrar/"))
        self.assertEqual(Participante.objects.count(), total)

    def test_sem_permissao_recebe_403(self):
        self.client.force_login(_usuario("sem_permissao_ficticio"))
        for nome, url in self.urls().items():
            with self.subTest(url=nome):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_view_participante_libera_so_lista_e_detalhe(self):
        self.client.force_login(_usuario("leitor_ficticio", "view_participante"))
        esperado = {"lista": 200, "detalhe": 200, "novo": 403, "corrigir": 403, "situacao": 403}
        for nome, url in self.urls().items():
            with self.subTest(url=nome):
                self.assertEqual(self.client.get(url).status_code, esperado[nome])

    def test_add_exige_view_e_add(self):
        urls = self.urls()
        self.client.force_login(_usuario("so_add_ficticio", "add_participante"))
        self.assertEqual(self.client.get(urls["novo"]).status_code, 403)
        self.client.force_login(_usuario("cadastrador_ficticio", "view_participante", "add_participante"))
        self.assertEqual(self.client.get(urls["novo"]).status_code, 200)
        self.assertEqual(self.client.get(urls["corrigir"]).status_code, 403)
        self.assertEqual(self.client.get(urls["situacao"]).status_code, 403)

    def test_change_libera_corrigir_e_situacao(self):
        urls = self.urls()
        self.client.force_login(_usuario("so_change_ficticio", "change_participante"))
        self.assertEqual(self.client.get(urls["corrigir"]).status_code, 403)
        self.client.force_login(_usuario("corretor_ficticio", "view_participante", "change_participante"))
        for nome in ("corrigir", "situacao"):
            with self.subTest(url=nome):
                self.assertEqual(self.client.get(urls[nome]).status_code, 200)
        self.assertEqual(self.client.get(urls["novo"]).status_code, 403)

    def test_post_sem_permissao_nao_grava(self):
        self.client.force_login(_usuario("leitor_post_ficticio", "view_participante"))
        total = Participante.objects.count()
        self.assertEqual(self.client.post(self.urls()["novo"], POST_FICTICIO).status_code, 403)
        self.assertEqual(Participante.objects.count(), total)
        resposta = self.client.post(self.urls()["situacao"], {"vigente_desde": "2024-03-01"})
        self.assertEqual(resposta.status_code, 403)
        self.assertFalse(SituacaoSocial.objects.filter(participante=self.participante).exists())

    def test_usuario_inativo_nao_acessa(self):
        inativo = _usuario("inativo_ficticio", "view_participante", "add_participante", "change_participante",
                           is_active=False)
        self.client.force_login(inativo)
        for nome, url in self.urls().items():
            with self.subTest(url=nome):
                resposta = self.client.get(url)
                self.assertEqual(resposta.status_code, 302)
                self.assertTrue(resposta["Location"].startswith("/entrar/"))

    def test_usuario_desativado_apos_login_perde_acesso(self):
        usuario = _usuario("desativado_ficticio", "view_participante")
        self.client.force_login(usuario)
        self.assertEqual(self.client.get(self.urls()["lista"]).status_code, 200)
        get_user_model().objects.filter(pk=usuario.pk).update(is_active=False)
        resposta = self.client.get(self.urls()["lista"])
        self.assertEqual(resposta.status_code, 302)
        self.assertTrue(resposta["Location"].startswith("/entrar/"))


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class ListaTests(Base):
    def setUp(self):
        self.client.force_login(self.gestor)

    def test_busca_ignora_acento_e_caixa(self):
        Participante.objects.create(nome_completo="José Ficticio Conceição", data_nascimento=date(1945, 1, 1),
                                    sexo="M", raca_cor="preta", identidade_genero="homem_cis", endereco="Rua X",
                                    telefone_celular="11912345678", origem_encaminhamento="cras")
        url = reverse("participantes:lista")
        for termo in ("jose", "JOSÉ", "conceicao", "  CONCEIÇÃO   jose ", "conceicao jose"):
            with self.subTest(termo=termo):
                resposta = self.client.get(url, {"q": termo})
                self.assertContains(resposta, "José Ficticio Conceição")
                self.assertNotContains(resposta, "Ana Ficticia Souza")
                self.assertContains(resposta, "1 encontrado para")
        resposta = self.client.get(url, {"q": "inexistente"})
        self.assertContains(resposta, "Nenhum participante encontrado")

    def test_sem_termo_lista_todos_com_status_e_contato(self):
        resposta = self.client.get(reverse("participantes:lista"))
        self.assertContains(resposta, "Ana Ficticia Souza")
        self.assertContains(resposta, "(11) 91234-5678")
        self.assertContains(resposta, '<td class="status-ativo">Ativo</td>', html=True)
        self.assertContains(resposta, "1 participante cadastrado")
        self.assertContains(resposta, reverse("participantes:cadastrar"))

    def test_status_inativo_exibido(self):
        Participante.objects.filter(pk=self.participante.pk).update(status=StatusParticipante.INATIVO)
        self.assertContains(self.client.get(reverse("participantes:lista")), "Inativo")

    def test_paginacao_de_20(self):
        for i in range(24):
            Participante.objects.create(nome_completo=f"Pessoa Ficticia {i:02d}", data_nascimento=date(1950, 1, 1),
                                        sexo="F", raca_cor="parda", identidade_genero="mulher_cis", endereco="Rua",
                                        telefone_celular="11912345678", origem_encaminhamento="cras")
        url = reverse("participantes:lista")
        primeira = self.client.get(url)
        self.assertEqual(len(primeira.context["pagina"].object_list), 20)
        self.assertContains(primeira, "Página 1 de 2")
        self.assertContains(primeira, "Próxima")
        segunda = self.client.get(url, {"page": 2})
        self.assertEqual(len(segunda.context["pagina"].object_list), 5)
        self.assertContains(segunda, "Anterior")
        # Página inválida cai numa página válida.
        self.assertEqual(self.client.get(url, {"page": "xyz"}).context["pagina"].number, 1)
        self.assertEqual(self.client.get(url, {"page": 99}).context["pagina"].number, 2)

    def test_paginacao_preserva_termo(self):
        for i in range(21):
            Participante.objects.create(nome_completo=f"Lúcia Ficticia {i:02d}", data_nascimento=date(1950, 1, 1),
                                        sexo="F", raca_cor="parda", identidade_genero="mulher_cis", endereco="Rua",
                                        telefone_celular="11912345678", origem_encaminhamento="cras")
        resposta = self.client.get(reverse("participantes:lista"), {"q": "lucia"})
        self.assertContains(resposta, "21 encontrados")
        self.assertContains(resposta, "?q=lucia&amp;page=2")

    def test_sem_add_nao_mostra_botao_novo(self):
        self.client.force_login(_usuario("leitor_lista_ficticio", "view_participante"))
        self.assertNotContains(self.client.get(reverse("participantes:lista")), reverse("participantes:cadastrar"))

    def test_post_nao_permitido(self):
        self.assertEqual(self.client.post(reverse("participantes:lista")).status_code, 405)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class CadastroTests(Base):
    def setUp(self):
        self.client.force_login(self.gestor)
        self.url = reverse("participantes:cadastrar")

    def test_get_mostra_data_entrada_e_nao_status(self):
        resposta = self.client.get(self.url)
        self.assertTemplateUsed(resposta, "participantes/formulario.html")
        self.assertContains(resposta, 'name="data_entrada"')
        self.assertContains(resposta, "Data de entrada")
        self.assertNotContains(resposta, 'name="status"')
        self.assertNotContains(resposta, 'name="confirmar_duplicidade"')

    def test_post_completo_cadastra_ativo_com_entrada(self):
        resposta = self.client.post(self.url, POST_FICTICIO)
        participante = Participante.objects.get(nome_completo="Josefa Exemplo Ficticia")
        self.assertRedirects(resposta, reverse("participantes:detalhe", args=[participante.pk]),
                             fetch_redirect_response=False)
        self.assertEqual(participante.telefone_celular, "11912345678")
        self.assertEqual(participante.status, StatusParticipante.ATIVO)
        entrada = Movimentacao.objects.get(participante=participante)
        self.assertEqual(entrada.tipo, TipoMovimentacao.ENTRADA)
        self.assertEqual(entrada.data, date(2024, 1, 15))
        self.assertEqual(entrada.usuario, self.gestor)
        detalhe = self.client.get(resposta["Location"])
        self.assertContains(detalhe, "Participante cadastrado com sucesso.")

    def test_status_enviado_e_ignorado(self):
        self.client.post(self.url, {**POST_FICTICIO, "status": StatusParticipante.CANCELADO})
        self.assertEqual(Participante.objects.get(nome_completo="Josefa Exemplo Ficticia").status,
                         StatusParticipante.ATIVO)

    def test_post_com_erros_rerenderiza_em_portugues(self):
        total = Participante.objects.count()
        resposta = self.client.post(self.url, {**POST_FICTICIO, "nome_completo": "", "telefone_celular": "",
                                               "data_entrada": "", "sexo": ""})
        self.assertEqual(resposta.status_code, 200)
        self.assertTemplateUsed(resposta, "participantes/formulario.html")
        self.assertContains(resposta, "Este campo é obrigatório.")
        self.assertEqual(Participante.objects.count(), total)

    def test_erros_do_servico_em_portugues(self):
        resposta = self.client.post(self.url, {**POST_FICTICIO, "telefone_celular": "", "telefone_residencial": ""})
        self.assertContains(resposta, "Informe pelo menos um telefone do próprio participante")
        resposta = self.client.post(self.url, {**POST_FICTICIO, "telefone_celular": "(11) 1234-5678"})
        self.assertContains(resposta, "Informe o celular com DDD e 9 dígitos")
        resposta = self.client.post(self.url, {**POST_FICTICIO, "data_entrada": "2999-01-01"})
        self.assertContains(resposta, "A data não pode estar no futuro.")
        self.assertFalse(Participante.objects.filter(nome_completo="Josefa Exemplo Ficticia").exists())

    def test_fluxo_de_duplicidade(self):
        dados = {**POST_FICTICIO, "nome_completo": "ANA FICTÍCIA  souza", "data_nascimento": "1948-06-01"}
        primeira = self.client.post(self.url, dados)
        self.assertEqual(primeira.status_code, 200)
        self.assertContains(primeira, "Já existe participante com o mesmo nome e data de nascimento")
        self.assertContains(primeira, 'name="confirmar_duplicidade"')
        self.assertContains(primeira, 'name="confirmar_duplicidade_exibida"')
        self.assertEqual(Participante.objects.filter(data_nascimento=date(1948, 6, 1)).count(), 1)

        # Reenvio com o alerta exibido mas sem marcar: continua bloqueado.
        sem_marcar = self.client.post(self.url, {**dados, "confirmar_duplicidade_exibida": "1"})
        self.assertContains(sem_marcar, "Já existe participante com o mesmo nome e data de nascimento")
        self.assertEqual(Participante.objects.filter(data_nascimento=date(1948, 6, 1)).count(), 1)

        segunda = self.client.post(self.url, {**dados, "confirmar_duplicidade_exibida": "1",
                                              "confirmar_duplicidade": "on"})
        novo = Participante.objects.filter(data_nascimento=date(1948, 6, 1)).exclude(pk=self.participante.pk).get()
        self.assertRedirects(segunda, reverse("participantes:detalhe", args=[novo.pk]))
        self.assertEqual(novo.status, StatusParticipante.ATIVO)
        self.assertTrue(novo.movimentacoes.filter(tipo=TipoMovimentacao.ENTRADA).exists())

    def test_confirmacao_sem_alerta_exibido_nao_vale(self):
        dados = {**POST_FICTICIO, "nome_completo": "Ana Ficticia Souza", "data_nascimento": "1948-06-01",
                 "confirmar_duplicidade": "on"}
        resposta = self.client.post(self.url, dados)
        self.assertContains(resposta, "Já existe participante com o mesmo nome e data de nascimento")
        self.assertEqual(Participante.objects.filter(data_nascimento=date(1948, 6, 1)).count(), 1)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class CorrigirTests(Base):
    def test_get_preenche_e_post_corrige(self):
        self.client.force_login(self.gestor)
        url = reverse("participantes:corrigir", args=[self.participante.pk])
        resposta = self.client.get(url)
        self.assertContains(resposta, 'value="2024-02-01"')
        self.assertNotContains(resposta, 'name="status"')
        dados = {**POST_FICTICIO, "nome_completo": "Ana Ficticia Souza", "data_nascimento": "1948-06-01",
                 "telefone_celular": "(21) 99876-5432", "data_entrada": "2024-02-05"}
        resposta = self.client.post(url, dados)
        self.assertRedirects(resposta, reverse("participantes:detalhe", args=[self.participante.pk]))
        self.participante.refresh_from_db()
        self.assertEqual(self.participante.telefone_celular, "21998765432")
        self.assertEqual(self.participante.data_entrada, date(2024, 2, 5))


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class DetalheTests(Base):
    def url(self):
        return reverse("participantes:detalhe", args=[self.participante.pk])

    def test_mostra_dados_entrada_e_status(self):
        self.client.force_login(self.gestor)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Ana Ficticia Souza")
        self.assertContains(resposta, "Data de entrada")
        self.assertContains(resposta, "01/02/2024")
        self.assertContains(resposta, "Ativo")
        self.assertContains(resposta, "(11) 91234-5678")

    def test_sem_entrada_mostra_traco(self):
        sem_entrada = Participante.objects.create(
            nome_completo="Sem Entrada Ficticia", data_nascimento=date(1950, 1, 1), sexo="F", raca_cor="parda",
            identidade_genero="mulher_cis", endereco="Rua", telefone_celular="11912345678",
            origem_encaminhamento="cras")
        self.client.force_login(self.gestor)
        resposta = self.client.get(reverse("participantes:detalhe", args=[sem_entrada.pk]))
        self.assertIsNone(resposta.context["data_entrada"])
        self.assertContains(resposta, '<dd class="col-sm-8">—</dd>', html=True)

    def test_inexistente_404(self):
        self.client.force_login(self.gestor)
        self.assertEqual(self.client.get(reverse("participantes:detalhe", args=[999999])).status_code, 404)

    def test_historico_so_com_change(self):
        self.client.force_login(self.gestor)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Histórico de alterações")
        self.assertIsNotNone(resposta.context["registros"])
        self.assertContains(resposta, reverse("participantes:corrigir", args=[self.participante.pk]))

        self.client.force_login(_usuario("leitor_detalhe_ficticio", "view_participante"))
        resposta = self.client.get(self.url())
        self.assertEqual(resposta.status_code, 200)
        self.assertNotContains(resposta, "Histórico de alterações")
        self.assertIsNone(resposta.context["registros"])
        self.assertNotContains(resposta, reverse("participantes:corrigir", args=[self.participante.pk]))
        self.assertNotContains(resposta, reverse("participantes:situacao_social", args=[self.participante.pk]))

    def _com_atividades(self, username):
        usuario = _usuario(username, "view_participante")
        usuario.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
                                                                codename__in=PERMISSOES_ATIVIDADES))
        return usuario

    def test_cartao_frequencia_com_permissoes_de_atividades(self):
        self.client.force_login(self._com_atividades("freq_ficticio"))
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "Atividades e frequência")
        self.assertEqual(resposta.context["frequencias"], [])
        self.assertContains(resposta, "Nenhuma inscrição em atividades.")

    def test_cartao_frequencia_some_sem_alguma_permissao(self):
        for faltando in PERMISSOES_ATIVIDADES:
            with self.subTest(sem=faltando):
                usuario = _usuario(f"freq_sem_{faltando}", "view_participante")
                usuario.user_permissions.add(*Permission.objects.filter(
                    content_type__app_label="atividades",
                    codename__in=[p for p in PERMISSOES_ATIVIDADES if p != faltando]))
                self.client.force_login(usuario)
                resposta = self.client.get(self.url())
                self.assertEqual(resposta.status_code, 200)
                self.assertNotContains(resposta, "Atividades e frequência")
                self.assertIsNone(resposta.context["frequencias"])

    @override_settings(NCI_CONSULTA_FREQUENCIA_PARTICIPANTE="")
    def test_cartao_frequencia_some_sem_consulta_configurada(self):
        self.client.force_login(self._com_atividades("freq_sem_consulta_ficticio"))
        resposta = self.client.get(self.url())
        self.assertNotContains(resposta, "Atividades e frequência")
        self.assertIsNone(resposta.context["frequencias"])

    def test_situacao_social_atual_destacada(self):
        registrar_situacao_social(usuario=self.gestor, participante_id=self.participante.pk,
                                  vigente_desde=date(2024, 3, 1), mora_sozinho=True, tem_apoio=False,
                                  possui_deficiencia=False, recebe_bpc=True, imigrante_refugiado=False)
        self.client.force_login(self.gestor)
        resposta = self.client.get(self.url())
        self.assertContains(resposta, "01/03/2024 (atual)")


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class SituacaoSocialViewTests(Base):
    def url(self):
        return reverse("participantes:situacao_social", args=[self.participante.pk])

    def test_get_sem_situacao_comeca_hoje(self):
        from django.utils import timezone
        self.client.force_login(self.gestor)
        resposta = self.client.get(self.url())
        form = resposta.context["form"]
        self.assertEqual(form.initial["vigente_desde"], timezone.localdate())
        self.assertContains(resposta, f'value="{timezone.localdate():%Y-%m-%d}"')
        for campo in ("mora_sozinho", "tem_apoio", "possui_deficiencia", "recebe_bpc", "imigrante_refugiado"):
            self.assertFalse(form.initial.get(campo))
            self.assertNotIn("checked", str(form[campo]))

    def test_get_preenche_com_situacao_vigente(self):
        registrar_situacao_social(usuario=self.gestor, participante_id=self.participante.pk,
                                  vigente_desde=date(2023, 1, 1), mora_sozinho=False, tem_apoio=False,
                                  possui_deficiencia=False, recebe_bpc=False, imigrante_refugiado=False)
        registrar_situacao_social(usuario=self.gestor, participante_id=self.participante.pk,
                                  vigente_desde=date(2024, 3, 1), mora_sozinho=True, tem_apoio=False,
                                  possui_deficiencia=True, recebe_bpc=False, imigrante_refugiado=True)
        self.client.force_login(self.gestor)
        resposta = self.client.get(self.url())
        form = resposta.context["form"]
        self.assertIs(form.initial["mora_sozinho"], True)
        self.assertIs(form.initial["possui_deficiencia"], True)
        self.assertIs(form.initial["imigrante_refugiado"], True)
        self.assertIs(form.initial["tem_apoio"], False)
        html = str(form["mora_sozinho"])
        self.assertIn("checked", html)
        self.assertNotIn("checked", str(form["tem_apoio"]))

    def test_post_cria_e_redireciona(self):
        self.client.force_login(self.gestor)
        resposta = self.client.post(self.url(), {"vigente_desde": "2024-04-01", "mora_sozinho": "on",
                                                 "recebe_bpc": "on"})
        self.assertRedirects(resposta, reverse("participantes:detalhe", args=[self.participante.pk]),
                             fetch_redirect_response=False)
        situacao = SituacaoSocial.objects.get(participante=self.participante)
        self.assertEqual(situacao.vigente_desde, date(2024, 4, 1))
        self.assertTrue(situacao.mora_sozinho)
        self.assertTrue(situacao.recebe_bpc)
        self.assertFalse(situacao.tem_apoio)
        self.assertContains(self.client.get(resposta["Location"]), "Situação social registrada.")

    def test_post_mesma_data_corrige(self):
        self.client.force_login(self.gestor)
        self.client.post(self.url(), {"vigente_desde": "2024-04-01"})
        self.client.post(self.url(), {"vigente_desde": "2024-04-01", "tem_apoio": "on"})
        situacao = SituacaoSocial.objects.get(participante=self.participante)
        self.assertTrue(situacao.tem_apoio)

    def test_post_data_futura_rerenderiza_com_erro(self):
        self.client.force_login(self.gestor)
        resposta = self.client.post(self.url(), {"vigente_desde": "2999-01-01"})
        self.assertEqual(resposta.status_code, 200)
        self.assertContains(resposta, "A data de início não pode estar no futuro.")
        self.assertFalse(SituacaoSocial.objects.filter(participante=self.participante).exists())
