from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from participantes.models import Movimentacao, MotivoDesligamento
from participantes.movimentacoes import movimentar_participante
from participantes.tests.test_models import novo_participante
from relatorios.services import consultar_movimentacao_etaria_fmr


class CalculoEtarioTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="calculo_etario_ficticio")
        self.usuario.groups.add(Group.objects.get(name="Equipe"))
        self.motivo = MotivoDesligamento.objects.create(descricao="Motivo fictício")

    def pessoa(self, nascimento, entrada=date(2024, 1, 1), sexo="F"):
        pessoa = novo_participante(data_nascimento=nascimento, sexo=sexo)
        pessoa.save()
        Movimentacao.objects.create(participante=pessoa, usuario=self.usuario, tipo="entrada", data=entrada)
        return pessoa

    def mover(self, pessoa, tipo, dia):
        return movimentar_participante(usuario=self.usuario, participante_id=pessoa.pk, tipo=tipo,
            data=date(2024, 2, dia), motivo_id=self.motivo.pk if tipo == "desligamento" else None)

    def consultar(self):
        return consultar_movimentacao_etaria_fmr(usuario=self.usuario, ano=2024, mes=2)

    def test_aniversario_no_dia_um_e_durante_o_mes_usam_a_mesma_referencia(self):
        self.pessoa(date(1959, 2, 1))
        self.pessoa(date(1959, 2, 15))
        resultado = self.consultar()
        linhas = {(r["faixa"], r["sexo_codigo"]): r for r in resultado["linhas"]}
        self.assertEqual(linhas[("65–69", "F")]["permanecem"], 1)
        self.assertEqual(linhas[("60–64", "F")]["permanecem"], 1)
        self.assertEqual(resultado["data_referencia_idade"], date(2024, 2, 1))

    def test_ciclos_multiplos_afastamento_e_retornos_preservam_balanco(self):
        pessoa = self.pessoa(date(1950, 1, 1), sexo="M")
        self.mover(pessoa, "desligamento", 2)
        self.mover(pessoa, "reativacao", 3)
        self.mover(pessoa, "desligamento", 4)
        outra = self.pessoa(date(1940, 1, 1))
        self.mover(outra, "afastamento", 10)
        resultado = self.consultar()
        self.assertEqual(resultado["totais"], {"vieram_mes_anterior": 2, "ingressaram": 0,
            "reativados": 1, "sairam": 2, "permanecem": 1})
        for linha in resultado["linhas"]:
            self.assertEqual(linha["vieram_mes_anterior"] + linha["ingressaram"] + linha["reativados"] - linha["sairam"], linha["permanecem"])

    def test_entradas_nos_limites_do_mes_e_futuro_nao_alteram_passado(self):
        self.pessoa(date(1960, 1, 1), entrada=date(2024, 2, 1))
        self.pessoa(date(1960, 1, 1), entrada=date(2024, 2, 29))
        self.pessoa(date(1960, 1, 1), entrada=date(2024, 3, 1))
        resultado = self.consultar()["totais"]
        self.assertEqual((resultado["vieram_mes_anterior"], resultado["ingressaram"], resultado["permanecem"]), (0, 2, 2))

    def test_dados_incompletos_nao_viram_zero_e_fora_da_faixa_e_explicitado(self):
        pessoa = self.pessoa(date(1980, 1, 1))
        resultado = self.consultar()
        self.assertEqual(resultado["totais"]["permanecem"], 0)
        self.assertEqual(resultado["fora_faixas"]["permanecem"], 1)
        pessoa.movimentacoes.all().delete()
        resultado = self.consultar()
        self.assertIsNone(resultado["totais"])
        self.assertTrue(resultado["pendencias"])
