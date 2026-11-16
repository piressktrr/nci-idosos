from datetime import date

from django.test import TestCase

from participantes.consultas import situacoes_vigentes_em
from participantes.models import Participante, SituacaoSocial

# RN-SEG-02: somente dados fictícios.
DADOS = {
    "data_nascimento": date(1950, 3, 10),
    "sexo": "F",
    "raca_cor": "parda",
    "identidade_genero": "mulher_cis",
    "telefone_celular": "61912345678",
    "origem_encaminhamento": "cras",
    "endereco": "Rua Fictícia, 100",
    "ensino_medio_completo": True,
}
INDICADORES = {"mora_sozinho": False, "tem_apoio": False, "possui_deficiencia": False,
               "recebe_bpc": False, "imigrante_refugiado": False}
DATAS = (date(2023, 12, 31), date(2024, 1, 1), date(2024, 2, 15), date(2024, 3, 1), date(2024, 3, 31),
         date(2024, 6, 1), date(2030, 1, 1))


def participante(nome):
    return Participante.objects.create(nome_completo=nome, **DADOS)


def situacao(pessoa, vigente_desde, **indicadores):
    return SituacaoSocial.objects.create(participante=pessoa, vigente_desde=vigente_desde,
                                         **(INDICADORES | indicadores))


class SituacoesVigentesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.ana = participante("Ana Fictícia")
        cls.bia = participante("Bia Fictícia")
        cls.cida = participante("Cida Fictícia")  # sem situação social
        # Criadas fora de ordem para não depender da ordem de inserção.
        situacao(cls.ana, date(2024, 3, 1), recebe_bpc=True)
        situacao(cls.ana, date(2024, 1, 1), mora_sozinho=True)
        situacao(cls.ana, date(2024, 6, 1), tem_apoio=True)
        situacao(cls.bia, date(2024, 2, 15), possui_deficiencia=True)
        situacao(cls.bia, date(2023, 6, 1))
        cls.todos = (cls.ana, cls.bia, cls.cida)

    def test_bate_com_vigente_em_para_varios_participantes_e_datas(self):
        for data in DATAS:
            with self.subTest(data=data):
                resultado = situacoes_vigentes_em(data)
                self.assertEqual(set(resultado), {pessoa.pk for pessoa in self.todos})
                for pessoa in self.todos:
                    self.assertEqual(resultado[pessoa.pk], SituacaoSocial.vigente_em(pessoa, data), pessoa)

    def test_valores_esperados(self):
        resultado = situacoes_vigentes_em(date(2024, 3, 15))
        self.assertTrue(resultado[self.ana.pk].recebe_bpc)
        self.assertEqual(resultado[self.ana.pk].vigente_desde, date(2024, 3, 1))
        self.assertEqual(resultado[self.bia.pk].vigente_desde, date(2024, 2, 15))
        self.assertIsNone(resultado[self.cida.pk])
        self.assertIsNone(situacoes_vigentes_em(date(2023, 12, 31))[self.ana.pk])

    def test_aceita_none_queryset_instancias_e_pks(self):
        data = date(2024, 2, 20)
        esperado = {pessoa.pk: SituacaoSocial.vigente_em(pessoa, data) for pessoa in (self.ana, self.cida)}
        entradas = {
            "queryset": Participante.objects.filter(pk__in=[self.ana.pk, self.cida.pk]),
            "instancias": [self.ana, self.cida],
            "pks": [self.ana.pk, self.cida.pk],
        }
        for nome, participantes in entradas.items():
            with self.subTest(entrada=nome):
                self.assertEqual(situacoes_vigentes_em(data, participantes), esperado)
        self.assertEqual(set(situacoes_vigentes_em(data, None)), {pessoa.pk for pessoa in self.todos})

    def test_lista_vazia_devolve_vazio_sem_consulta(self):
        with self.assertNumQueries(0):
            self.assertEqual(situacoes_vigentes_em(date(2024, 1, 1), []), {})
        with self.assertNumQueries(0):
            self.assertEqual(situacoes_vigentes_em(date(2024, 1, 1), Participante.objects.none()), {})

    def test_numero_de_consultas_constante(self):
        data = date(2024, 4, 1)

        def consultas(participantes):
            # Cada chamada é medida pelo assertNumQueries, inclusive o acesso aos campos do resultado.
            resultado = situacoes_vigentes_em(data, participantes)
            return [s.mora_sozinho for s in resultado.values() if s is not None]

        with self.assertNumQueries(2):
            consultas(None)
        with self.assertNumQueries(2):
            consultas(Participante.objects.all())
        with self.assertNumQueries(1):
            consultas(list(self.todos))
        with self.assertNumQueries(1):
            consultas([pessoa.pk for pessoa in self.todos])

        novos = [participante(f"Pessoa Fictícia {indice}") for indice in range(12)]
        for indice, pessoa in enumerate(novos):
            situacao(pessoa, date(2024, 1, 1 + indice))
            situacao(pessoa, date(2024, 2, 1 + indice), mora_sozinho=True)
        self.assertEqual(len(situacoes_vigentes_em(data)), 15)
        with self.assertNumQueries(2):
            consultas(None)
        with self.assertNumQueries(2):
            consultas(Participante.objects.all())
        with self.assertNumQueries(1):
            consultas([*self.todos, *novos])
        with self.assertNumQueries(1):
            consultas([pessoa.pk for pessoa in (*self.todos, *novos)])
        resultado = situacoes_vigentes_em(data, novos)
        self.assertTrue(all(resultado[pessoa.pk].mora_sozinho for pessoa in novos))
