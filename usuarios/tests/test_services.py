"""RF-USR-03 / RN-USR-01 / RNF-SEG-07: serviços de colaboradores e auditoria das contas. Dados fictícios (RN-SEG-02)."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from core.models import AuditoriaImutavel, tipos_do_modelo
from core.perfis import GRUPO_ADMINISTRADOR, GRUPO_EQUIPE, e_administrador
from usuarios.models import RegistroConta
from usuarios.services import (
    alterar_situacao_conta,
    cadastrar_colaborador,
    corrigir_colaborador,
    definir_senha,
    garantir_administrador_restante,
    perfil_de,
)

from .base import OUTRA_SENHA_VALIDA, SENHA_VALIDA, administrador, conta, dados_cadastro, equipe


def _texto(evento):
    return f"{evento.anteriores} {evento.novos}"


class CadastroTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()

    def test_cadastra_com_perfil_senha_e_auditoria(self):
        nova = cadastrar_colaborador(usuario=self.admin, **dados_cadastro())
        nova.refresh_from_db()
        self.assertTrue(nova.is_active)
        self.assertFalse(nova.is_staff or nova.is_superuser)
        self.assertEqual(list(nova.groups.values_list("name", flat=True)), [GRUPO_EQUIPE])
        self.assertTrue(nova.check_password(SENHA_VALIDA))
        evento = RegistroConta.objects.get(conta=nova)
        self.assertEqual(evento.acao, "cadastro")
        self.assertEqual(evento.usuario, self.admin)
        self.assertIsNone(evento.anteriores)
        self.assertEqual(evento.novos, {"username": "nova_colab_ficticia", "first_name": "Maria",
                                        "last_name": "Fictícia", "email": "maria.ficticia@example.org",
                                        "perfil": GRUPO_EQUIPE})
        self.assertNotIn(SENHA_VALIDA, _texto(evento))
        self.assertNotIn(nova.password, _texto(evento))

    def test_perfil_administrador_vai_para_o_grupo_administrador(self):
        nova = cadastrar_colaborador(usuario=self.admin, **dados_cadastro(perfil=GRUPO_ADMINISTRADOR))
        self.assertEqual(list(nova.groups.values_list("name", flat=True)), [GRUPO_ADMINISTRADOR])
        self.assertTrue(e_administrador(nova))

    def test_senhas_fracas_sao_recusadas_sem_criar_conta(self):
        for senha in ("curta123", "1234567890123", "qwertyuiop", "nova_colab_ficticia"):
            with self.subTest(senha=senha), self.assertRaises(ValidationError) as erro:
                cadastrar_colaborador(usuario=self.admin, **dados_cadastro(senha=senha))
            self.assertIn("senha", erro.exception.message_dict)
        self.assertFalse(get_user_model().objects.filter(username="nova_colab_ficticia").exists())
        self.assertFalse(RegistroConta.objects.exists())

    def test_usuario_repetido_mesmo_com_outra_caixa_e_recusado(self):
        conta("Ana_Ficticia")
        with self.assertRaises(ValidationError) as erro:
            cadastrar_colaborador(usuario=self.admin, **dados_cadastro(username="ana_ficticia"))
        self.assertIn("username", erro.exception.message_dict)

    def test_usuario_invalido_e_perfil_invalido(self):
        with self.assertRaises(ValidationError) as erro:
            cadastrar_colaborador(usuario=self.admin, **dados_cadastro(username="com espaço", perfil="Oficineiro"))
        self.assertIn("username", erro.exception.message_dict)
        self.assertIn("perfil", erro.exception.message_dict)

    def test_somente_administrador_cadastra(self):
        superusuario = get_user_model().objects.create_superuser("super_colab_ficticio", password=None)
        cadastrar_colaborador(usuario=superusuario, **dados_cadastro())
        comum = equipe()
        # Nem permissões avulsas de contas bastam: o critério é ser administrador (RN-USR-01).
        comum.user_permissions.add(*Permission.objects.filter(content_type__app_label="auth",
                                                              codename__in=["add_user", "change_user"]))
        inativo = administrador("admin_inativo_colab_ficticio", is_active=False)
        for usuario in (None, comum, inativo):
            with self.subTest(usuario=usuario), self.assertRaises(PermissionDenied):
                cadastrar_colaborador(usuario=usuario, **dados_cadastro(username="outra_colab_ficticia"))
        self.assertFalse(get_user_model().objects.filter(username="outra_colab_ficticia").exists())


class CorrecaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()
        cls.colab = cadastrar_colaborador(usuario=cls.admin, **dados_cadastro())

    def _corrigir(self, usuario=None, conta_alvo=None, **alterar):
        alvo = conta_alvo or self.colab
        dados = {"first_name": alvo.first_name, "last_name": alvo.last_name, "email": alvo.email,
                 "perfil": perfil_de(alvo)} | alterar
        return corrigir_colaborador(usuario=usuario or self.admin, conta_id=alvo.pk, **dados)

    def test_audita_so_o_que_mudou(self):
        self._corrigir(email="maria.nova@example.org", perfil=GRUPO_ADMINISTRADOR)
        evento = RegistroConta.objects.get(conta=self.colab, acao="correcao")
        self.assertEqual(evento.anteriores, {"email": "maria.ficticia@example.org", "perfil": GRUPO_EQUIPE})
        self.assertEqual(evento.novos, {"email": "maria.nova@example.org", "perfil": GRUPO_ADMINISTRADOR})
        self.colab.refresh_from_db()
        self.assertEqual(self.colab.email, "maria.nova@example.org")
        self.assertEqual(perfil_de(self.colab), GRUPO_ADMINISTRADOR)
        self.assertEqual(self.colab.groups.count(), 1)

    def test_sem_mudanca_nao_grava_evento(self):
        self._corrigir(first_name="  Maria  ")
        self.assertFalse(RegistroConta.objects.filter(acao="correcao").exists())

    def test_email_invalido_e_nome_vazio(self):
        with self.assertRaises(ValidationError) as erro:
            self._corrigir(email="sem-arroba", first_name="")
        self.assertIn("email", erro.exception.message_dict)
        self.assertIn("first_name", erro.exception.message_dict)
        self.assertFalse(RegistroConta.objects.filter(acao="correcao").exists())

    def test_nao_altera_o_proprio_perfil(self):
        with self.assertRaises(ValidationError) as erro:
            self._corrigir(conta_alvo=self.admin, perfil=GRUPO_EQUIPE)
        self.assertIn("perfil", erro.exception.message_dict)
        self.assertTrue(e_administrador(self.admin))
        # Os demais dados da própria conta podem ser corrigidos.
        self._corrigir(conta_alvo=self.admin, first_name="Administradora")
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.first_name, "Administradora")

    def test_nao_deixa_o_sistema_sem_administrador_ativo(self):
        with self.assertRaises(ValidationError) as erro:
            garantir_administrador_restante(self.admin, GRUPO_EQUIPE)
        self.assertIn("perfil", erro.exception.message_dict)
        garantir_administrador_restante(self.admin, GRUPO_ADMINISTRADOR)
        administrador("outra_admin_ficticia")
        garantir_administrador_restante(self.admin, GRUPO_EQUIPE)

    def test_administrador_inativo_ou_superusuario_contam_corretamente(self):
        administrador("admin_inativa_ficticia", is_active=False)
        with self.assertRaises(ValidationError):
            garantir_administrador_restante(self.admin, GRUPO_EQUIPE)
        get_user_model().objects.create_superuser("super_restante_ficticio", password=None)
        garantir_administrador_restante(self.admin, GRUPO_EQUIPE)

    def test_rebaixa_outro_administrador_quando_resta_um(self):
        outro = administrador("admin_rebaixado_ficticio", first_name="Rita")
        self._corrigir(conta_alvo=outro, perfil=GRUPO_EQUIPE)
        self.assertFalse(e_administrador(outro))

    def test_equipe_nao_corrige(self):
        with self.assertRaises(PermissionDenied):
            self._corrigir(usuario=equipe(), first_name="Outra")


class SenhaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()
        cls.colab = cadastrar_colaborador(usuario=cls.admin, **dados_cadastro())

    def test_redefine_e_audita_sem_senha_nem_hash(self):
        definir_senha(usuario=self.admin, conta_id=self.colab.pk, senha=OUTRA_SENHA_VALIDA)
        self.colab.refresh_from_db()
        self.assertTrue(self.colab.check_password(OUTRA_SENHA_VALIDA))
        self.assertFalse(self.colab.check_password(SENHA_VALIDA))
        evento = RegistroConta.objects.get(conta=self.colab, acao="senha")
        self.assertEqual(evento.usuario, self.admin)
        self.assertIsNone(evento.anteriores)
        self.assertEqual(evento.novos, {"senha": "redefinida"})
        for evento in RegistroConta.objects.filter(conta=self.colab):
            with self.subTest(acao=evento.acao):
                self.assertNotIn(OUTRA_SENHA_VALIDA, _texto(evento))
                self.assertNotIn(self.colab.password, _texto(evento))
                self.assertNotIn("pbkdf2", _texto(evento))

    def test_senha_fraca_e_recusada(self):
        with self.assertRaises(ValidationError) as erro:
            definir_senha(usuario=self.admin, conta_id=self.colab.pk, senha="1234567890")
        self.assertIn("senha", erro.exception.message_dict)
        self.colab.refresh_from_db()
        self.assertTrue(self.colab.check_password(SENHA_VALIDA))
        self.assertFalse(RegistroConta.objects.filter(acao="senha").exists())

    def test_equipe_nao_redefine(self):
        with self.assertRaises(PermissionDenied):
            definir_senha(usuario=equipe(), conta_id=self.colab.pk, senha=OUTRA_SENHA_VALIDA)


class AuditoriaContaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = administrador()
        cls.colab = cadastrar_colaborador(usuario=cls.admin, **dados_cadastro())

    def test_proxy_registrado_para_user(self):
        self.assertIn("RegistroConta", tipos_do_modelo(get_user_model()))
        evento = RegistroConta.objects.get(conta=self.colab)
        self.assertEqual(evento.conta, self.colab)
        self.assertEqual(evento.conta_id, self.colab.pk)

    def test_eventos_sao_imutaveis(self):
        with self.assertRaises(AuditoriaImutavel):
            RegistroConta.objects.filter(conta=self.colab).update(novos={})
        with self.assertRaises(AuditoriaImutavel):
            RegistroConta.objects.get(conta=self.colab).delete()

    def test_conta_auditada_nao_pode_ser_excluida(self):
        # User não herda ProtegidoPorAuditoria: o pre_delete do core levanta dentro da transação do Collector.
        with self.assertRaises(ProtectedError), transaction.atomic():
            self.colab.delete()
        with self.assertRaises(ProtectedError), transaction.atomic():
            get_user_model().objects.filter(pk=self.colab.pk).delete()
        self.assertTrue(get_user_model().objects.filter(pk=self.colab.pk).exists())

    def test_ninguem_do_grupo_tem_permissao_de_excluir_contas(self):
        self.assertFalse(Permission.objects.filter(group__isnull=False, content_type__app_label="auth",
                                                   codename="delete_user").exists())

    def test_admin_do_django_nao_exclui_contas_nem_para_superusuario(self):
        """Contas estão fora do admin do Django (RNF-SEG-07): nem a exclusão nem a lista existem lá."""
        superusuario = get_user_model().objects.create_superuser("super_exclui_ficticio", password=None)
        self.client.force_login(superusuario)
        with self.settings(DEBUG=True, SECURE_SSL_REDIRECT=False):
            resposta = self.client.post(f"/admin/auth/user/{self.colab.pk}/delete/", {"post": "yes"})
            self.assertEqual(resposta.status_code, 404)
            self.assertEqual(self.client.get("/admin/auth/user/").status_code, 404)
        self.assertTrue(get_user_model().objects.filter(pk=self.colab.pk).exists())


class ProtecaoSuperusuarioTests(TestCase):
    """RN-USR-01: membro do grupo Administrador não altera a conta de um superusuário."""

    def setUp(self):
        self.admin = administrador()
        self.super = get_user_model().objects.create_superuser(username="super_ficticio", password=SENHA_VALIDA,
                                                              email="super.ficticio@example.org")

    def test_administrador_comum_nao_altera_superusuario(self):
        tentativas = {
            "senha": lambda: definir_senha(usuario=self.admin, conta_id=self.super.pk, senha=OUTRA_SENHA_VALIDA),
            "dados": lambda: corrigir_colaborador(usuario=self.admin, conta_id=self.super.pk, first_name="Outro",
                                                  last_name="", email="tomada@example.org", perfil=""),
            "situacao": lambda: alterar_situacao_conta(usuario=self.admin, conta_id=self.super.pk, ativo=False),
        }
        for nome, tentativa in tentativas.items():
            with self.subTest(acao=nome), self.assertRaises(PermissionDenied):
                tentativa()
        self.super.refresh_from_db()
        self.assertTrue(self.super.check_password(SENHA_VALIDA))
        self.assertTrue(self.super.is_active)
        self.assertEqual(self.super.email, "super.ficticio@example.org")
        self.assertFalse(RegistroConta.objects.filter(alvo_id=self.super.pk).exists())

    def test_superusuario_altera_outro_superusuario(self):
        outro = get_user_model().objects.create_superuser(username="super_dois_ficticio", password=SENHA_VALIDA,
                                                          email="super.dois@example.org")
        definir_senha(usuario=self.super, conta_id=outro.pk, senha=OUTRA_SENHA_VALIDA)
        outro.refresh_from_db()
        self.assertTrue(outro.check_password(OUTRA_SENHA_VALIDA))

    def test_administrador_comum_continua_alterando_contas_comuns(self):
        colab = equipe()
        definir_senha(usuario=self.admin, conta_id=colab.pk, senha=OUTRA_SENHA_VALIDA)
        colab.refresh_from_db()
        self.assertTrue(colab.check_password(OUTRA_SENHA_VALIDA))
