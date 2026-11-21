"""RF-USR-05 (NCI 20/11/2026): "esqueci minha senha" por e-mail. Dados fictícios (RN-SEG-02)."""

import re

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from usuarios.models import RegistroConta
from usuarios.services import cadastrar_colaborador, corrigir_colaborador, perfil_de

from .base import OUTRA_SENHA_VALIDA, SENHA_VALIDA, administrador, dados_cadastro, equipe

LINK = re.compile(r"https?://[^\s]+/entrar/redefinir/[^\s]+/")


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False,
                   MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}})
class RecuperacaoDeSenhaTests(TestCase):
    def setUp(self):
        self.conta = equipe(email="carlos.ficticio@example.org")
        self.conta.set_password(SENHA_VALIDA)
        self.conta.save()

    def pedir(self, email):
        return self.client.post(reverse("recuperar_senha"), {"email": email})

    def link(self):
        self.assertEqual(len(mail.outbox), 1)
        return LINK.search(mail.outbox[0].body).group(0)

    def test_login_tem_link_para_esqueci_minha_senha(self):
        resposta = self.client.get(reverse("entrar"))
        self.assertContains(resposta, reverse("recuperar_senha"))
        self.assertContains(resposta, "Esqueci minha senha")

    def test_pedido_envia_link_so_para_o_email_da_conta(self):
        resposta = self.pedir("carlos.ficticio@example.org")
        self.assertRedirects(resposta, reverse("recuperacao_enviada"))
        self.assertEqual(mail.outbox[0].to, ["carlos.ficticio@example.org"])
        self.assertEqual(mail.outbox[0].subject, "NCI Idade Dourada: criar nova senha")
        self.assertIn(self.conta.get_username(), mail.outbox[0].body)
        self.assertNotIn(SENHA_VALIDA, mail.outbox[0].body)

    def test_email_desconhecido_responde_igual_e_nao_envia(self):
        resposta = self.pedir("ninguem.ficticio@example.org")
        self.assertRedirects(resposta, reverse("recuperacao_enviada"))
        self.assertEqual(mail.outbox, [])

    def test_conta_inativa_nao_recebe_email(self):
        get_user_model().objects.filter(pk=self.conta.pk).update(is_active=False)
        self.pedir("carlos.ficticio@example.org")
        self.assertEqual(mail.outbox, [])

    def test_link_redefine_a_senha_audita_e_so_vale_uma_vez(self):
        self.pedir("carlos.ficticio@example.org")
        link = self.link()
        formulario = self.client.get(link, follow=True)
        self.assertContains(formulario, "Criar nova senha")
        url_form = formulario.redirect_chain[-1][0]
        nova = {"new_password1": OUTRA_SENHA_VALIDA, "new_password2": OUTRA_SENHA_VALIDA}
        resposta = self.client.post(url_form, nova)
        self.assertRedirects(resposta, reverse("recuperacao_concluida"))
        self.conta.refresh_from_db()
        self.assertTrue(self.conta.check_password(OUTRA_SENHA_VALIDA))
        self.assertFalse(self.conta.check_password(SENHA_VALIDA))
        evento = RegistroConta.objects.get(alvo_id=self.conta.pk, acao="senha_recuperada")
        self.assertEqual(evento.usuario, self.conta)
        self.assertEqual(evento.novos, {"senha": "recuperada por e-mail"})
        self.assertNotIn(OUTRA_SENHA_VALIDA, str(evento.novos))
        # O mesmo link não serve de novo.
        self.client.logout()
        self.assertContains(self.client.get(link, follow=True), "Este link é inválido ou já foi usado.")

    def test_senha_fraca_e_recusada_pelos_validadores(self):
        self.pedir("carlos.ficticio@example.org")
        formulario = self.client.get(self.link(), follow=True)
        url_form = formulario.redirect_chain[-1][0]
        resposta = self.client.post(url_form, {"new_password1": "8273649150", "new_password2": "8273649150"})
        self.assertEqual(resposta.status_code, 200)
        self.conta.refresh_from_db()
        self.assertTrue(self.conta.check_password(SENHA_VALIDA))
        self.assertFalse(RegistroConta.objects.filter(acao="senha_recuperada").exists())

    def test_link_adulterado_e_recusado(self):
        resposta = self.client.get(reverse("redefinir_senha", args=["MQ", "token-ficticio-invalido"]))
        self.assertContains(resposta, "Este link é inválido ou já foi usado.")


class EmailObrigatorioTests(TestCase):
    """O e-mail passa a ser obrigatório nas contas, porque é o caminho para recuperar a senha."""

    def test_cadastro_sem_email_e_recusado(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError) as erro:
            cadastrar_colaborador(usuario=administrador(), **dados_cadastro(email=""))
        self.assertIn("email", erro.exception.message_dict)

    def test_correcao_nao_pode_apagar_o_email(self):
        from django.core.exceptions import ValidationError
        admin = administrador()
        colab = cadastrar_colaborador(usuario=admin, **dados_cadastro())
        with self.assertRaises(ValidationError) as erro:
            corrigir_colaborador(usuario=admin, conta_id=colab.pk, first_name=colab.first_name,
                                 last_name=colab.last_name, email="", perfil=perfil_de(colab))
        self.assertIn("email", erro.exception.message_dict)


@override_settings(DEBUG=True, SECURE_SSL_REDIRECT=False,
                   MAILERS={"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}})
class RecuperacaoReforcadaTests(TestCase):
    """Reforços do review de 20/11: link invalidado na desativação, gravação atômica, validade curta."""

    def setUp(self):
        self.conta = equipe(email="carlos.reforco@example.org")
        self.conta.set_password(SENHA_VALIDA)
        self.conta.save()
        self.client.post(reverse("recuperar_senha"), {"email": "carlos.reforco@example.org"})
        self.link = LINK.search(mail.outbox[0].body).group(0)

    def test_link_pedido_antes_da_desativacao_deixa_de_valer(self):
        get_user_model().objects.filter(pk=self.conta.pk).update(is_active=False)
        self.assertContains(self.client.get(self.link, follow=True), "Este link é inválido ou já foi usado.")

    def test_falha_na_auditoria_nao_troca_a_senha(self):
        from unittest.mock import patch
        url_form = self.client.get(self.link, follow=True).redirect_chain[-1][0]
        nova = {"new_password1": OUTRA_SENHA_VALIDA, "new_password2": OUTRA_SENHA_VALIDA}
        with patch("usuarios.recuperacao.RegistroConta.objects.create", side_effect=RuntimeError("falha fictícia")):
            with self.assertRaises(RuntimeError):
                self.client.post(url_form, nova)
        self.conta.refresh_from_db()
        self.assertTrue(self.conta.check_password(SENHA_VALIDA))

    def test_link_vale_duas_horas(self):
        from django.conf import settings
        self.assertEqual(settings.PASSWORD_RESET_TIMEOUT, 2 * 60 * 60)
        self.assertIn("vale por 2 horas", mail.outbox[0].body)


class EmailUnicoTests(TestCase):
    """RF-USR-01/05: cada conta tem o seu e-mail, para o link de recuperação não cair na caixa de outra pessoa."""

    def test_cadastro_com_email_de_outra_conta_e_recusado(self):
        from django.core.exceptions import ValidationError
        admin = administrador()
        equipe(username="dona_do_email_ficticia", email="compartilhado@example.org")
        with self.assertRaises(ValidationError) as erro:
            cadastrar_colaborador(usuario=admin, **dados_cadastro(email="COMPARTILHADO@example.org"))
        self.assertIn("email", erro.exception.message_dict)

    def test_correcao_para_email_de_outra_conta_e_recusada(self):
        from django.core.exceptions import ValidationError
        admin = administrador()
        equipe(username="outra_ficticia", email="ocupado@example.org")
        colab = cadastrar_colaborador(usuario=admin, **dados_cadastro())
        with self.assertRaises(ValidationError) as erro:
            corrigir_colaborador(usuario=admin, conta_id=colab.pk, first_name=colab.first_name,
                                 last_name=colab.last_name, email="ocupado@example.org", perfil=perfil_de(colab))
        self.assertIn("email", erro.exception.message_dict)
