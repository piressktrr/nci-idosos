from datetime import date

from django.test import SimpleTestCase

from participantes.regras import (celular_valido, chave_nome, data_minima_nascimento, faixa_etaria_fmr,
                                  faixa_etaria_fmr_no_mes, inicio_do_mes,
                                  formatar_telefone, idade_em, normalizar_espacos, residencial_valido, so_digitos)


class IdadeTests(SimpleTestCase):
    def test_idade_conta_ano_completo_somente_apos_o_aniversario(self):
        nascimento = date(1950, 6, 15)
        self.assertEqual(idade_em(nascimento, date(2020, 6, 14)), 69)
        self.assertEqual(idade_em(nascimento, date(2020, 6, 15)), 70)
        self.assertEqual(idade_em(nascimento, date(2020, 6, 16)), 70)

    def test_idade_considera_mes_antes_do_dia(self):
        nascimento = date(1950, 6, 15)
        self.assertEqual(idade_em(nascimento, date(2020, 5, 31)), 69)
        self.assertEqual(idade_em(nascimento, date(2020, 7, 1)), 70)

    def test_nascido_em_29_de_fevereiro_completa_anos_em_1_de_marco_em_ano_nao_bissexto(self):
        nascimento = date(1952, 2, 29)
        self.assertEqual(idade_em(nascimento, date(2021, 2, 28)), 68)
        self.assertEqual(idade_em(nascimento, date(2021, 3, 1)), 69)
        self.assertEqual(idade_em(nascimento, date(2024, 2, 29)), 72)


class FaixaEtariaFmrTests(SimpleTestCase):
    referencia = date(2025, 3, 10)

    def faixa_com_idade(self, idade, *, aniversario_hoje=True):
        """Nascimento que resulta em `idade` na referência (no dia do aniversário ou na véspera)."""
        if aniversario_hoje:
            return faixa_etaria_fmr(date(self.referencia.year - idade, 3, 10), self.referencia)
        return faixa_etaria_fmr(date(self.referencia.year - idade - 1, 3, 11), self.referencia)

    def test_abaixo_de_60_anos_nao_tem_faixa_do_fmr(self):
        self.assertIsNone(self.faixa_com_idade(59))
        self.assertIsNone(self.faixa_com_idade(59, aniversario_hoje=False))
        self.assertIsNone(self.faixa_com_idade(30))

    def test_fronteiras_das_faixas_no_dia_do_aniversario(self):
        esperado = {60: "60 a 64 anos", 64: "60 a 64 anos", 65: "65 a 69 anos", 69: "65 a 69 anos",
                    70: "70 a 74 anos", 74: "70 a 74 anos", 75: "75 anos ou mais", 100: "75 anos ou mais"}
        for idade, rotulo in esperado.items():
            with self.subTest(idade=idade):
                self.assertEqual(self.faixa_com_idade(idade), rotulo)

    def test_vespera_do_aniversario_ainda_fica_na_faixa_anterior(self):
        esperado = {60: "60 a 64 anos", 64: "60 a 64 anos", 69: "65 a 69 anos", 74: "70 a 74 anos"}
        for idade, rotulo in esperado.items():
            with self.subTest(idade=idade):
                self.assertEqual(self.faixa_com_idade(idade, aniversario_hoje=False), rotulo)


class FaixaEtariaNoMesTests(SimpleTestCase):
    """RN-PAR-07 (P01, NCI 20/11/2026): faixa do mês pela idade no dia 1º."""

    def test_inicio_do_mes(self):
        self.assertEqual(inicio_do_mes(date(2025, 3, 31)), date(2025, 3, 1))
        self.assertEqual(inicio_do_mes(date(2024, 2, 29)), date(2024, 2, 1))

    def test_aniversario_durante_o_mes_so_muda_a_faixa_no_mes_seguinte(self):
        nascimento = date(1955, 3, 15)  # faz 70 em 15/03/2025
        for dia in (1, 14, 15, 31):
            with self.subTest(dia=dia):
                self.assertEqual(faixa_etaria_fmr_no_mes(nascimento, date(2025, 3, dia)), "65 a 69 anos")
        self.assertEqual(faixa_etaria_fmr_no_mes(nascimento, date(2025, 4, 1)), "70 a 74 anos")

    def test_aniversario_no_dia_1_ja_conta_no_proprio_mes(self):
        self.assertEqual(faixa_etaria_fmr_no_mes(date(1965, 3, 1), date(2025, 3, 20)), "60 a 64 anos")
        self.assertIsNone(faixa_etaria_fmr_no_mes(date(1965, 3, 2), date(2025, 3, 20)))


class NormalizacaoNomeTests(SimpleTestCase):
    def test_normalizar_espacos_colapsa_e_apara_espacos_tabs_e_quebras(self):
        self.assertEqual(normalizar_espacos("  Maria \t da\n  Silva  "), "Maria da Silva")
        self.assertEqual(normalizar_espacos("   "), "")
        self.assertEqual(normalizar_espacos(""), "")

    def test_chave_nome_ignora_acentos_caixa_e_espacos(self):
        self.assertEqual(chave_nome("  JOSÉ   da Conceição "), "jose da conceicao")
        self.assertEqual(chave_nome("Ângela Müller"), chave_nome("angela muller"))

    def test_chave_nome_usa_casefold_para_esszett(self):
        self.assertEqual(chave_nome("Weiß Fictício"), "weiss ficticio")
        self.assertEqual(chave_nome("WEISS FICTICIO"), chave_nome("weiß fictício"))

    def test_chave_nome_mantem_nomes_diferentes_distintos(self):
        self.assertNotEqual(chave_nome("Ana Fictícia"), chave_nome("Ana Ficticia Souza"))

    def test_data_minima_de_nascimento_e_1_de_janeiro_de_1900(self):
        self.assertEqual(data_minima_nascimento(), date(1900, 1, 1))


class TelefoneTests(SimpleTestCase):
    def test_so_digitos_remove_mascara_espacos_e_pontuacao(self):
        self.assertEqual(so_digitos("(61) 91234-5678"), "61912345678")
        self.assertEqual(so_digitos(" 61 3123.4567 "), "6131234567")
        self.assertEqual(so_digitos(""), "")
        self.assertEqual(so_digitos(None), "")

    def test_celular_valido_exige_11_digitos_com_9_na_terceira_posicao(self):
        self.assertTrue(celular_valido("61912345678"))
        self.assertFalse(celular_valido("6191234567"))  # 10 dígitos
        self.assertFalse(celular_valido("619123456789"))  # 12 dígitos
        self.assertFalse(celular_valido("61812345678"))  # 3º dígito não é 9
        self.assertFalse(celular_valido(""))

    def test_celular_rejeita_ddd_com_zero(self):
        self.assertFalse(celular_valido("01912345678"))
        self.assertFalse(celular_valido("60912345678"))

    def test_residencial_valido_exige_10_digitos_com_terceiro_de_2_a_5(self):
        for terceiro in "2345":
            with self.subTest(terceiro=terceiro):
                self.assertTrue(residencial_valido(f"61{terceiro}1234567"))
        for terceiro in "016789":
            with self.subTest(terceiro=terceiro):
                self.assertFalse(residencial_valido(f"61{terceiro}1234567"))
        self.assertFalse(residencial_valido("613123456"))  # 9 dígitos
        self.assertFalse(residencial_valido("61312345678"))  # 11 dígitos
        self.assertFalse(residencial_valido(""))

    def test_residencial_rejeita_ddd_com_zero(self):
        self.assertFalse(residencial_valido("0131234567"))
        self.assertFalse(residencial_valido("6031234567"))

    def test_formatar_telefone_aplica_mascara_de_celular_e_fixo(self):
        self.assertEqual(formatar_telefone("61912345678"), "(61) 91234-5678")
        self.assertEqual(formatar_telefone("6131234567"), "(61) 3123-4567")

    def test_formatar_telefone_devolve_sem_mascara_tamanhos_inesperados(self):
        self.assertEqual(formatar_telefone(""), "")
        self.assertEqual(formatar_telefone("12345"), "12345")
