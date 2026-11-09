from datetime import date, time
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import Client, TestCase
from django.urls import reverse

from atividades.classificacao import salvar_categoria, classificar_atividade
from atividades.models import (Atividade, Aula, CategoriaFMR, ClassificacaoAtividade,
                     RegistroCategoriaFMR, RegistroClassificacaoAtividade)


class ClassificacaoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser(username="admin_ficticio", password=None)
        cls.equipe = get_user_model().objects.create_user(username="equipe_ficticia", is_staff=True)
        cls.equipe.user_permissions.add(*Permission.objects.filter(content_type__app_label="atividades",
            codename__in=("view_atividade", "view_aula", "change_atividade")))
        cls.atividade = Atividade.objects.create(nome="Fictícia", local="Sala", monitor="Fictício")
        cls.cat = salvar_categoria(usuario=cls.admin, nome="Categoria fictícia")
        cls.outra = salvar_categoria(usuario=cls.admin, nome="Outra fictícia")
        cls.url = reverse("atividades:classificacao_fmr", args=[cls.atividade.pk])

    def classificar(self, **kwargs):
        return classificar_atividade(**({"usuario": self.equipe, "atividade_id": self.atividade.pk,
            "categoria_id": self.cat.pk, "inicio": date(2024, 1, 1)} | kwargs))

    def aula(self, data, **kwargs):
        return Aula.objects.create(atividade=self.atividade, data=data, inicio=time(9), fim=time(10), **kwargs)

    def test_catalogo_auditado_renomeacao_desativacao_e_sem_exclusao(self):
        salvar_categoria(usuario=self.admin, categoria_id=self.cat.pk, nome="Renomeada", ativa=False)
        evento = RegistroCategoriaFMR.objects.filter(categoria=self.cat).latest("pk")
        self.assertEqual(evento.anteriores, {"nome": "Categoria fictícia", "ativa": True})
        self.assertEqual(evento.novos, {"nome": "Renomeada", "ativa": False})
        self.assertEqual(evento.usuario, self.admin)
        self.assertIsNotNone(evento.registrado_em)

    def test_somente_superusuario_ativo_administra_catalogo(self):
        with self.assertRaises(PermissionDenied):
            salvar_categoria(usuario=self.equipe, nome="Proibida")
        self.admin.is_active = False
        self.admin.save()
        with self.assertRaises(PermissionDenied):
            salvar_categoria(usuario=self.admin, nome="Proibida")

    def test_vigencias_limites_e_aula_digitada_depois(self):
        self.classificar()
        self.classificar(categoria_id=self.outra.pk, inicio=date(2024, 2, 15))
        for data in (date(2023, 12, 31), date(2024, 1, 1), date(2024, 2, 14), date(2024, 2, 15)):
            self.aula(data)
        ids = list(Aula.objects.com_categoria_fmr().order_by("data").values_list("categoria_fmr_id", flat=True))
        self.assertEqual(ids, [None, self.cat.pk, self.cat.pk, self.outra.pk])

    def test_destaque_atual_usa_hoje_e_ignora_troca_futura(self):
        self.classificar()
        self.classificar(categoria_id=self.outra.pk, inicio=date(2024, 2, 1))
        self.client.force_login(self.equipe)
        for hoje, esperado in ((date(2024, 1, 31), "Categoria fictícia"), (date(2024, 2, 1), "Outra fictícia")):
            with self.subTest(hoje=hoje), patch("django.utils.timezone.localdate", return_value=hoje):
                self.assertContains(self.client.get(reverse("atividades:lista")), "Categoria atual: " + esperado)
                resposta = self.client.get(self.url)
                self.assertContains(resposta, "Categoria atual: " + esperado)
                self.assertContains(resposta, "Vigente hoje", count=1)

    def test_indicador_sem_categoria_antes_da_primeira_vigencia(self):
        self.classificar(inicio=date(2024, 2, 1))
        self.client.force_login(self.equipe)
        with patch("django.utils.timezone.localdate", return_value=date(2024, 1, 31)):
            for url in (reverse("atividades:lista"), self.url):
                self.assertContains(self.client.get(url), "Sem categoria")
                self.assertNotContains(self.client.get(url), "Vigente hoje")

    def test_filtro_categoria_vigente_sem_categoria_e_inativa(self):
        self.classificar()
        self.classificar(categoria_id=self.outra.pk, inicio=date(2024, 2, 1))
        sem = Atividade.objects.create(nome="Sem fictícia", local="Sala", monitor="Fictício")
        self.client.force_login(self.equipe)
        url = reverse("atividades:lista")
        with patch("django.utils.timezone.localdate", return_value=date(2024, 1, 31)):
            self.assertEqual(self.client.get(url, {"categoria": self.cat.pk}).context["pagina"].paginator.count, 1)
            self.assertEqual(self.client.get(url, {"categoria": self.outra.pk}).context["pagina"].paginator.count, 0)
            resposta = self.client.get(url, {"categoria": "sem_categoria"})
            self.assertEqual([item.pk for item in resposta.context["pagina"]], [sem.pk])
            salvar_categoria(usuario=self.admin, categoria_id=self.cat.pk, nome=self.cat.nome, ativa=False)
            self.assertEqual(self.client.get(url, {"categoria": self.cat.pk}).context["pagina"].paginator.count, 1)
        resposta = self.client.get(url, {"categoria": "invalida"})
        self.assertTrue(resposta.context["filtro_categoria"].errors)

    def test_paginacao_preserva_filtro_categoria(self):
        self.classificar()
        for indice in range(21):
            atividade = Atividade.objects.create(nome=f"Fictícia {indice:02}", local="Sala", monitor="Fictício")
            ClassificacaoAtividade.objects.create(atividade=atividade, categoria=self.cat,
                categoria_nome=self.cat.nome, inicio=date(2024, 1, 1))
        self.client.force_login(self.equipe)
        resposta = self.client.get(reverse("atividades:lista"), {"categoria": self.cat.pk})
        self.assertContains(resposta, f"?page=2&amp;categoria={self.cat.pk}")
        self.assertEqual(resposta.context["pagina"].paginator.count, 22)

    def test_renomear_desativar_preserva_historico_e_novos_vinculos_bloqueados(self):
        self.classificar()
        aula = self.aula(date(2024, 1, 20))
        salvar_categoria(usuario=self.admin, categoria_id=self.cat.pk, nome="Novo nome", ativa=False)
        self.assertEqual(Aula.objects.com_categoria_fmr().get(pk=aula.pk).categoria_fmr_nome, "Categoria fictícia")
        with self.assertRaises(ValidationError):
            self.classificar(inicio=date(2024, 2, 1))
        self.classificar()  # Manter o vínculo não reescreve o snapshot.
        self.assertEqual(RegistroClassificacaoAtividade.objects.count(), 1)

    def test_correcao_de_vigencia_auditada_sem_alterar_outros_periodos(self):
        vinculo = self.classificar()
        self.classificar(inicio=date(2024, 3, 1))
        self.classificar(categoria_id=self.outra.pk)
        self.assertEqual(ClassificacaoAtividade.objects.count(), 2)
        evento = vinculo.registros.latest("pk")
        self.assertEqual(evento.anteriores["categoria_id"], self.cat.pk)
        self.assertEqual(evento.novos["categoria_id"], self.outra.pk)
        self.assertEqual(evento.usuario, self.equipe)

    def test_canceladas_sao_filtradas_do_contrato_de_totais(self):
        self.classificar()
        self.aula(date(2024, 1, 1))
        self.aula(date(2024, 1, 2), situacao="cancelada")
        self.assertEqual(Aula.objects.realizadas().com_categoria_fmr().filter(categoria_fmr_id=self.cat.pk).count(), 1)

    def test_isola_atividades_e_nao_inventa_classificacao_legada(self):
        self.classificar()
        outra = Atividade.objects.create(nome="Outra", local="Sala", monitor="Fictício")
        aula = Aula.objects.create(atividade=outra, data=date(2024, 1, 20), inicio=time(9), fim=time(10))
        self.assertIsNone(Aula.objects.com_categoria_fmr().get(pk=aula.pk).categoria_fmr_id)

    def test_rollback_se_auditoria_falhar(self):
        with patch("atividades.classificacao.RegistroCategoriaFMR.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                salvar_categoria(usuario=self.admin, nome="Reverter")
        self.assertFalse(CategoriaFMR.objects.filter(nome="Reverter").exists())
        with patch("atividades.classificacao.RegistroClassificacaoAtividade.objects.create", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.classificar()
        self.assertFalse(ClassificacaoAtividade.objects.exists())

    def test_permissao_atual_revogada_e_conta_desativada(self):
        self.equipe.has_perm("atividades.change_atividade")
        self.equipe.user_permissions.clear()
        with self.assertRaises(PermissionDenied):
            self.classificar()
        self.equipe.is_active = False
        self.equipe.save()
        with self.assertRaises(PermissionDenied):
            self.classificar()

    def test_validacoes_e_constraint(self):
        for nome in (" ", "x" * 151, None):
            with self.assertRaises(ValidationError):
                salvar_categoria(usuario=self.admin, nome=nome)
        with self.assertRaises(ValidationError):
            self.classificar(inicio="2024-01-01")
        with self.assertRaises(ValidationError):
            self.classificar(categoria_id=999999)
        self.classificar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ClassificacaoAtividade.objects.create(atividade=self.atividade, categoria=self.cat,
                categoria_nome=self.cat.nome, inicio=date(2024, 1, 1))

    def test_interface_catalogo_cria_edita_desativa_com_csrf(self):
        url = reverse("atividades:categorias_fmr")
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(self.equipe)
        self.assertEqual(self.client.get(url).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(url, {"nome": "Criada na tela", "ativa": "on"}).status_code, 302)
        categoria = CategoriaFMR.objects.get(nome="Criada na tela")
        self.assertEqual(self.client.post(reverse("atividades:editar_categoria_fmr", args=[categoria.pk]),
            {"nome": "Editada"}).status_code, 302)
        categoria.refresh_from_db()
        self.assertFalse(categoria.ativa)
        cliente = Client(enforce_csrf_checks=True)
        cliente.force_login(self.admin)
        self.assertEqual(cliente.post(url, {"nome": "Sem token"}).status_code, 403)

    def test_interface_classifica_exibe_aulas_historicas_e_escape(self):
        self.client.force_login(self.equipe)
        self.assertEqual(self.client.post(self.url, {"categoria": self.cat.pk, "inicio": "2024-01-01"}).status_code, 302)
        self.aula(date(2024, 1, 2))
        self.assertContains(self.client.get(reverse("atividades:aulas", args=[self.atividade.pk])), "Categoria fictícia")
        ClassificacaoAtividade.objects.update(categoria_nome="<script>fictício</script>")
        self.assertContains(self.client.get(self.url), "&lt;script&gt;fictício&lt;/script&gt;")
        self.assertEqual(RegistroClassificacaoAtividade.objects.count(), 1)

    def test_leitura_sem_escrita_filtros_inativos_404_e_sem_permissao_post(self):
        salvar_categoria(usuario=self.admin, categoria_id=self.cat.pk, nome=self.cat.nome, ativa=False)
        self.client.force_login(self.equipe)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertFalse(ClassificacaoAtividade.objects.exists())
        resposta = self.client.post(self.url, {"categoria": self.cat.pk, "inicio": "2024-01-01"})
        self.assertTrue(resposta.context["form"].errors)
        self.assertEqual(self.client.get(reverse("atividades:classificacao_fmr", args=[999999])).status_code, 404)
        self.equipe.user_permissions.remove(Permission.objects.get(content_type__app_label="atividades", codename="change_atividade"))
        self.assertEqual(self.client.post(self.url, {}).status_code, 403)
