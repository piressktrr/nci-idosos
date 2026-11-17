"""RF-USR-01 / RF-USR-03 / RN-USR-01: telas de colaboradores, acesso, menu e entrada. Dados fictícios (RN-SEG-02)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse

from core.perfis import GRUPO_ADMINISTRADOR, GRUPO_EQUIPE
from usuarios.models import RegistroConta
from usuarios.services import cadastrar_colaborador, perfil_de

from .base import OUTRA_SENHA_VALIDA, SENHA_VALIDA, administrador, conta, dados_cadastro, equipe


def _post_cadastro(**alterar):
    dados = dados_cadastro(**alterar)
    dados["confirmacao_senha"] = alterar.pop("confirmacao_senha", dados["senha"])
    return dados


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class AcessoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()
        cls.colab = cadastrar_colaborador(usuario=cls.admin, **dados_cadastro())

    def _urls(self):
        return [reverse("usuarios:lista"), reverse("usuarios:cadastrar"),
                reverse("usuarios:editar", args=[self.colab.pk]), reverse("usuarios:senha", args=[self.colab.pk])]

    def test_anonimo_vai_para_entrar(self):
        for url in self._urls():
            with self.subTest(url=url):
                self.assertRedirects(self.client.get(url), f"{reverse('entrar')}?next={url}",
                                     fetch_redirect_response=False)

    def test_equipe_sem_perfil_e_staff_recebem_403(self):
        staff = conta("staff_colab_ficticio", is_staff=True)
        for usuario in (equipe(), conta("sem_perfil_colab_ficticio"), staff):
            self.client.force_login(usuario)
            for url in self._urls():
                with self.subTest(usuario=usuario.username, url=url):
                    resposta = self.client.get(url)
                    self.assertEqual(resposta.status_code, 403)
                    self.assertTemplateUsed(resposta, "403.html")
            resposta = self.client.post(reverse("usuarios:cadastrar"), _post_cadastro(username="invasora_ficticia"))
            self.assertEqual(resposta.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username="invasora_ficticia").exists())

    def test_administrador_e_superusuario_acessam(self):
        superusuario = get_user_model().objects.create_superuser("super_colab_ficticio", password=None)
        for usuario in (self.admin, superusuario):
            self.client.force_login(usuario)
            for url in self._urls():
                with self.subTest(usuario=usuario.username, url=url):
                    self.assertEqual(self.client.get(url).status_code, 200)

    def test_administrador_inativo_nao_acessa(self):
        inativo = administrador("admin_inativo_colab_ficticio", is_active=False)
        self.client.force_login(inativo)
        url = reverse("usuarios:lista")
        self.assertRedirects(self.client.get(url), f"{reverse('entrar')}?next={url}", fetch_redirect_response=False)

    def test_desativado_depois_do_login_perde_acesso(self):
        self.client.force_login(self.admin)
        get_user_model().objects.filter(pk=self.admin.pk).update(is_active=False)
        self.assertNotEqual(self.client.get(reverse("usuarios:lista")).status_code, 200)

    def test_removido_do_grupo_recebe_403(self):
        self.client.force_login(self.admin)
        self.admin.groups.clear()
        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 403)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class MenuTests(TestCase):
    def test_menu_e_cartao_so_para_administrador(self):
        url = reverse("usuarios:lista")
        casos = {
            "admin": (administrador(), True),
            "super": (get_user_model().objects.create_superuser("super_menu_ficticio", password=None), True),
            "equipe": (equipe(), False),
            "staff_com_view_user": (conta("staff_menu_ficticio", is_staff=True), False),
        }
        casos["staff_com_view_user"][0].user_permissions.add(
            Permission.objects.get(content_type__app_label="auth", codename="view_user"))
        for nome, (usuario, aparece) in casos.items():
            with self.subTest(caso=nome):
                self.client.force_login(usuario)
                resposta = self.client.get(reverse("inicio"))
                if aparece:
                    self.assertContains(resposta, "Gestão de Colaboradores", count=2)  # menu e cartão
                    self.assertContains(resposta, f'<a class="nci-modulo" href="{url}">')
                    self.assertContains(resposta, f'<a href="{url}">Gestão de Colaboradores</a>')
                else:
                    self.assertNotContains(resposta, "Gestão de Colaboradores")
                    self.assertNotContains(resposta, url)
                self.assertNotContains(resposta, reverse("admin:auth_user_changelist"))

    def test_menu_marca_colaboradores_como_ativo(self):
        self.client.force_login(administrador())
        resposta = self.client.get(reverse("usuarios:lista"))
        self.assertContains(resposta, f'<a href="{reverse("usuarios:lista")}" class="ativo" aria-current="page">'
                                      "Gestão de Colaboradores</a>")


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class ListaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador(first_name="Beatriz", last_name="Administradora")
        cls.equipe = equipe(first_name="Carlos", last_name="Fictício", email="carlos@example.org")
        cls.sem_perfil = conta("sem_perfil_lista_ficticio", first_name="Denise", is_active=False)

    def setUp(self):
        self.client.force_login(self.admin)

    def test_mostra_colunas_e_perfis(self):
        resposta = self.client.get(reverse("usuarios:lista"))
        self.assertContains(resposta, "Carlos Fictício")
        self.assertContains(resposta, "equipe_colab_ficticia")
        self.assertContains(resposta, "carlos@example.org")
        linhas = {linha["conta"].username: linha["perfil"] for linha in resposta.context["linhas"]}
        self.assertEqual(linhas, {"admin_colab_ficticio": GRUPO_ADMINISTRADOR, "equipe_colab_ficticia": GRUPO_EQUIPE,
                                  "sem_perfil_lista_ficticio": ""})
        self.assertContains(resposta, "Sem perfil")
        self.assertContains(resposta, '<td class="status-inativo">Inativo</td>', html=True)
        self.assertContains(resposta, '<td class="status-ativo">Ativo</td>', count=2, html=True)
        self.assertContains(resposta, reverse("usuarios:cadastrar"))
        self.assertContains(resposta, reverse("usuarios:editar", args=[self.equipe.pk]))

    def test_busca_por_nome_sobrenome_e_usuario(self):
        casos = {"carlos": {"equipe_colab_ficticia"}, "FICTÍCIO": {"equipe_colab_ficticia"},
                 "sem_perfil": {"sem_perfil_lista_ficticio"}, "beatriz admin": {"admin_colab_ficticio"},
                 "ninguém": set()}
        for termo, esperados in casos.items():
            with self.subTest(termo=termo):
                resposta = self.client.get(reverse("usuarios:lista"), {"q": termo})
                self.assertEqual({linha["conta"].username for linha in resposta.context["linhas"]}, esperados)
        self.assertContains(self.client.get(reverse("usuarios:lista"), {"q": "ninguém"}),
                            "Nenhum colaborador encontrado")

    def test_paginacao(self):
        for numero in range(25):
            conta(f"pagina_ficticia_{numero:02d}", first_name="Zuleica")
        primeira = self.client.get(reverse("usuarios:lista"), {"q": "zuleica"})
        self.assertEqual(len(primeira.context["linhas"]), 20)
        self.assertContains(primeira, "Página 1 de 2")
        self.assertContains(primeira, "?q=zuleica&amp;page=2")
        segunda = self.client.get(reverse("usuarios:lista"), {"q": "zuleica", "page": 2})
        self.assertEqual(len(segunda.context["linhas"]), 5)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class CadastroViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()

    def setUp(self):
        self.client.force_login(self.admin)

    def test_cadastra_e_volta_para_lista(self):
        resposta = self.client.post(reverse("usuarios:cadastrar"), _post_cadastro(perfil=GRUPO_ADMINISTRADOR),
                                    follow=True)
        self.assertRedirects(resposta, reverse("usuarios:lista"))
        self.assertContains(resposta, "Colaborador nova_colab_ficticia cadastrado com sucesso.")
        nova = get_user_model().objects.get(username="nova_colab_ficticia")
        self.assertEqual(perfil_de(nova), GRUPO_ADMINISTRADOR)
        self.assertTrue(nova.check_password(SENHA_VALIDA))
        self.assertTrue(RegistroConta.objects.filter(conta=nova, acao="cadastro", usuario=self.admin).exists())

    def test_senha_fraca_mostra_erro(self):
        resposta = self.client.post(reverse("usuarios:cadastrar"), _post_cadastro(senha="1234567890",
                                                                                 confirmacao_senha="1234567890"))
        self.assertEqual(resposta.status_code, 200)
        self.assertTrue(resposta.context["form"].errors["senha"])
        self.assertContains(resposta, "inteiramente numérica")
        self.assertFalse(get_user_model().objects.filter(username="nova_colab_ficticia").exists())

    def test_senhas_divergentes(self):
        resposta = self.client.post(reverse("usuarios:cadastrar"), _post_cadastro(confirmacao_senha=OUTRA_SENHA_VALIDA))
        self.assertEqual(resposta.context["form"].errors["confirmacao_senha"], ["As senhas não conferem."])
        self.assertFalse(get_user_model().objects.filter(username="nova_colab_ficticia").exists())

    def test_campos_obrigatorios_e_usuario_repetido(self):
        resposta = self.client.post(reverse("usuarios:cadastrar"), _post_cadastro(first_name="", perfil=""))
        self.assertEqual(set(resposta.context["form"].errors), {"first_name", "perfil"})
        resposta = self.client.post(reverse("usuarios:cadastrar"), _post_cadastro(username="ADMIN_colab_ficticio"))
        self.assertIn("Já existe uma conta com este usuário.", resposta.context["form"].errors["username"])

    def test_senha_nao_volta_preenchida_no_formulario(self):
        resposta = self.client.post(reverse("usuarios:cadastrar"), _post_cadastro(confirmacao_senha="outra-coisa"))
        self.assertNotContains(resposta, SENHA_VALIDA)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class EdicaoViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()
        cls.colab = cadastrar_colaborador(usuario=cls.admin, **dados_cadastro())

    def setUp(self):
        self.client.force_login(self.admin)

    def _post(self, conta_alvo, **alterar):
        dados = {"first_name": conta_alvo.first_name, "last_name": conta_alvo.last_name, "email": conta_alvo.email,
                 "perfil": perfil_de(conta_alvo)} | alterar
        return self.client.post(reverse("usuarios:editar", args=[conta_alvo.pk]), dados, follow=True)

    def test_edita_e_mostra_historico_so_do_que_mudou(self):
        resposta = self._post(self.colab, last_name="Corrigida")
        self.assertRedirects(resposta, reverse("usuarios:editar", args=[self.colab.pk]))
        self.assertContains(resposta, "Dados do colaborador atualizados.")
        evento = RegistroConta.objects.get(conta=self.colab, acao="correcao")
        self.assertEqual(evento.anteriores, {"last_name": "Fictícia"})
        self.assertEqual(evento.novos, {"last_name": "Corrigida"})
        self.assertContains(resposta, "Histórico da conta")
        self.assertContains(resposta, "<td>Correção</td>", html=True)
        self.assertContains(resposta, "<td>Cadastro</td>", count=5, html=True)  # um por campo do cadastro
        self.assertContains(resposta, "<td>Corrigida</td>", html=True)

    def test_tela_de_outra_conta_tem_perfil_e_usuario_so_leitura(self):
        resposta = self.client.get(reverse("usuarios:editar", args=[self.colab.pk]))
        self.assertIn("perfil", resposta.context["form"].fields)
        self.assertNotIn("username", resposta.context["form"].fields)
        self.assertContains(resposta, reverse("usuarios:senha", args=[self.colab.pk]))
        self.assertContains(resposta, "Ativo")

    def test_propria_conta_sem_campo_de_perfil(self):
        resposta = self.client.get(reverse("usuarios:editar", args=[self.admin.pk]))
        self.assertNotIn("perfil", resposta.context["form"].fields)
        self.assertContains(resposta, "Você não pode alterar o seu próprio perfil")
        # Mesmo forjando o campo, o perfil não muda.
        resposta = self._post(self.admin, perfil=GRUPO_EQUIPE, first_name="Bete")
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.first_name, "Bete")
        self.assertEqual(perfil_de(self.admin), GRUPO_ADMINISTRADOR)

    def test_conta_inexistente_404(self):
        self.assertEqual(self.client.get(reverse("usuarios:editar", args=[999999])).status_code, 404)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class SenhaViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()
        cls.admin.set_password(SENHA_VALIDA)
        cls.admin.save()
        cls.colab = cadastrar_colaborador(usuario=cls.admin, **dados_cadastro())

    def setUp(self):
        self.client.force_login(self.admin)

    def _post(self, conta_alvo, senha, confirmacao=None):
        return self.client.post(reverse("usuarios:senha", args=[conta_alvo.pk]),
                                {"senha": senha, "confirmacao_senha": confirmacao or senha}, follow=True)

    def test_nova_senha_permite_entrar(self):
        resposta = self._post(self.colab, OUTRA_SENHA_VALIDA)
        self.assertRedirects(resposta, reverse("usuarios:editar", args=[self.colab.pk]))
        self.assertContains(resposta, "Nova senha definida para nova_colab_ficticia.")
        self.assertContains(resposta, "<td>Nova senha</td>", html=True)
        self.client.logout()
        self.assertFalse(self.client.login(username="nova_colab_ficticia", password=SENHA_VALIDA))
        self.assertTrue(self.client.login(username="nova_colab_ficticia", password=OUTRA_SENHA_VALIDA))
        evento = RegistroConta.objects.get(conta=self.colab, acao="senha")
        self.assertEqual(evento.novos, {"senha": "redefinida"})
        self.colab.refresh_from_db()
        self.assertNotIn(self.colab.password, f"{evento.anteriores} {evento.novos}")

    def test_divergente_e_fraca(self):
        resposta = self._post(self.colab, OUTRA_SENHA_VALIDA, "Diferente-Ficticia-1")
        self.assertEqual(resposta.context["form"].errors["confirmacao_senha"], ["As senhas não conferem."])
        resposta = self._post(self.colab, "qwertyuiop")
        self.assertTrue(resposta.context["form"].errors["senha"])
        self.assertFalse(RegistroConta.objects.filter(acao="senha").exists())

    def test_propria_senha_mantem_a_sessao(self):
        self._post(self.admin, OUTRA_SENHA_VALIDA)
        self.assertEqual(self.client.get(reverse("usuarios:lista")).status_code, 200)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False)
class LoginIndividualTests(TestCase):
    """RF-USR-01: cada integrante entra com o próprio usuário e senha."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()
        cls.colab = cadastrar_colaborador(usuario=cls.admin, **dados_cadastro())

    def _entrar(self, username, senha):
        return self.client.post(reverse("entrar"), {"username": username, "password": senha})

    def test_entra_com_as_proprias_credenciais(self):
        resposta = self._entrar("nova_colab_ficticia", SENHA_VALIDA)
        self.assertRedirects(resposta, reverse("inicio"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.colab.pk)

    def test_senha_errada_ou_conta_inativa_nao_entram(self):
        self.assertEqual(self._entrar("nova_colab_ficticia", OUTRA_SENHA_VALIDA).status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        get_user_model().objects.filter(pk=self.colab.pk).update(is_active=False)
        self.assertEqual(self._entrar("nova_colab_ficticia", SENHA_VALIDA).status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
