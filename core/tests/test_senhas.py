"""RNF-SEG-05: senhas guardadas com hash e validadas pelos AUTH_PASSWORD_VALIDATORS. Dados fictícios (RN-SEG-02)."""

from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, get_hasher, identify_hasher
from django.contrib.auth.password_validation import get_default_password_validators, validate_password
from django.core.exceptions import ValidationError
from django.test import TestCase

from usuarios.services import cadastrar_colaborador, definir_senha
from usuarios.tests.base import OUTRA_SENHA_VALIDA, SENHA_VALIDA, administrador, dados_cadastro


class HashDeSenhaTests(TestCase):
    def assert_hash(self, conta, senha):
        conta.refresh_from_db()
        self.assertNotEqual(conta.password, senha)
        self.assertNotIn(senha, conta.password)
        hasher = identify_hasher(conta.password)
        self.assertEqual(hasher.algorithm, get_hasher().algorithm)  # hasher principal do Django
        self.assertTrue(conta.password.startswith(f"{hasher.algorithm}$"))
        self.assertTrue(check_password(senha, conta.password))

    def test_hasher_principal_e_do_django_e_nao_e_inseguro(self):
        self.assertTrue(settings.PASSWORD_HASHERS[0].startswith("django.contrib.auth.hashers."))
        self.assertNotIn(get_hasher().algorithm, {"md5", "unsalted_md5", "unsalted_sha1", "sha1"})

    def test_create_user_guarda_hash(self):
        conta = get_user_model().objects.create_user(username="hash_ficticio", password=SENHA_VALIDA)
        self.assert_hash(conta, SENHA_VALIDA)

    def test_servicos_de_colaboradores_guardam_hash(self):
        admin = administrador()
        nova = cadastrar_colaborador(usuario=admin, **dados_cadastro())
        self.assert_hash(nova, SENHA_VALIDA)
        definir_senha(usuario=admin, conta_id=nova.pk, senha=OUTRA_SENHA_VALIDA)
        self.assert_hash(nova, OUTRA_SENHA_VALIDA)
        self.assertFalse(check_password(SENHA_VALIDA, get_user_model().objects.get(pk=nova.pk).password))


class ValidadoresDeSenhaTests(TestCase):
    def test_validadores_configurados(self):
        nomes = {type(v).__name__: v for v in get_default_password_validators()}
        self.assertLessEqual({"UserAttributeSimilarityValidator", "MinimumLengthValidator",
                              "CommonPasswordValidator", "NumericPasswordValidator"}, set(nomes))
        self.assertGreaterEqual(nomes["MinimumLengthValidator"].min_length, 10)

    def test_recusa_curta_comum_e_numerica(self):
        casos = {"curta": "Gir-2026a", "comum": "password123", "numerica": "8273649150"}
        for nome, senha in casos.items():
            with self.subTest(caso=nome), self.assertRaises(ValidationError):
                validate_password(senha)

    def test_aceita_senha_ficticia_valida_com_10_caracteres(self):
        self.assertIsNone(validate_password("Gir-2026ab"))
        self.assertIsNone(validate_password(SENHA_VALIDA))

    def test_servicos_de_colaboradores_usam_os_validadores(self):
        admin = administrador()
        with patch("usuarios.services.validate_password", wraps=validate_password) as validar:
            nova = cadastrar_colaborador(usuario=admin, **dados_cadastro())
            definir_senha(usuario=admin, conta_id=nova.pk, senha=OUTRA_SENHA_VALIDA)
        self.assertEqual([chamada.args[0] for chamada in validar.call_args_list], [SENHA_VALIDA, OUTRA_SENHA_VALIDA])

    def test_servicos_recusam_senha_fraca_sem_gravar(self):
        admin = administrador()
        for nome, senha in {"curta": "Gir-2026a", "comum": "password123", "numerica": "8273649150"}.items():
            with self.subTest(caso=nome), self.assertRaises(ValidationError) as erro:
                cadastrar_colaborador(usuario=admin, **dados_cadastro(senha=senha))
            self.assertIn("senha", erro.exception.message_dict)
        self.assertFalse(get_user_model().objects.filter(username="nova_colab_ficticia").exists())
        nova = cadastrar_colaborador(usuario=admin, **dados_cadastro())
        antes = nova.password
        with self.assertRaises(ValidationError):
            definir_senha(usuario=admin, conta_id=nova.pk, senha="8273649150")
        nova.refresh_from_db()
        self.assertEqual(nova.password, antes)
