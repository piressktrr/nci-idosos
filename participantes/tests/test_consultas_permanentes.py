"""Alternativa `permanentes_com_pendencias` a `permanentes_em` (RN-FMR-12). Dados fictícios (RN-SEG-02)."""

from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase

from participantes.consultas import permanentes_com_pendencias, permanentes_em
from participantes.models import MotivoDesligamento, Movimentacao
from participantes.tests.test_models import criar_participante


class PermanentesComPendenciasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()
        cls.equipe = Usuario.objects.create_user(username="equipe_pend_ficticia")
        cls.equipe.groups.add(Group.objects.get(name="Equipe"))
        cls.ana = criar_participante(nome_completo="Ana Fictícia Permanente")
        Movimentacao.objects.create(participante=cls.ana, usuario=cls.equipe, tipo="entrada", data=date(2024, 1, 10))
        cls.bia = criar_participante(nome_completo="Bia Fictícia Desligada")
        Movimentacao.objects.create(participante=cls.bia, usuario=cls.equipe, tipo="entrada", data=date(2024, 1, 5))
        Movimentacao.objects.create(participante=cls.bia, usuario=cls.equipe, tipo="desligamento",
                                    data=date(2024, 2, 1), motivo=MotivoDesligamento.objects.create(
                                        descricao="Motivo fictício de teste"),
                                    motivo_descricao="Motivo fictício de teste")

    def consultar(self, data=date(2024, 2, 29)):
        return permanentes_com_pendencias(usuario=self.equipe, data_referencia=data)

    def refs(self, resumos):
        return [r.referencia for r in resumos]

    def test_acervo_completo_igual_a_permanentes_em(self):
        resultado = self.consultar()
        self.assertTrue(resultado.completo)
        self.assertEqual(resultado.pendentes, ())
        self.assertEqual(resultado.permanentes, permanentes_em(usuario=self.equipe, data_referencia=date(2024, 2, 29)))
        self.assertEqual(self.refs(resultado.permanentes), [str(self.ana.pk)])
        self.assertEqual(self.refs(self.consultar(date(2024, 1, 31)).permanentes), [str(self.ana.pk), str(self.bia.pk)])

    def test_cadastro_sem_entrada_vai_para_pendentes_sem_anular_o_resto(self):
        sem_entrada = criar_participante(nome_completo="Caio Fictício Sem Entrada")
        resultado = self.consultar()
        self.assertFalse(resultado.completo)
        self.assertEqual(self.refs(resultado.permanentes), [str(self.ana.pk)])
        self.assertEqual(self.refs(resultado.pendentes), [str(sem_entrada.pk)])
        self.assertIsNone(permanentes_em(usuario=self.equipe, data_referencia=date(2024, 2, 29)))  # contrato mantido

    def test_status_legado_vai_para_pendentes(self):
        type(self.ana).objects.filter(pk=self.ana.pk).update(status="inativo")
        resultado = self.consultar()
        self.assertEqual(resultado.permanentes, ())
        self.assertEqual(self.refs(resultado.pendentes), [str(self.ana.pk)])
        self.assertIsNone(permanentes_em(usuario=self.equipe, data_referencia=date(2024, 2, 29)))

    def test_permissao_e_data_validadas(self):
        sem_perfil = get_user_model().objects.create_user(username="sem_perfil_pend_ficticio")
        with self.assertRaises(PermissionDenied):
            permanentes_com_pendencias(usuario=sem_perfil, data_referencia=date(2024, 2, 29))
        with self.assertRaises(ValidationError):
            self.consultar("2024-02-29")
