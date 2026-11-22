from datetime import date
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from participantes.models import Movimentacao, MotivoDesligamento, PerfilDemografico
from participantes.movimentacoes import movimentar_participante
from participantes.relatorios import movimentacao_etaria_mensal
from participantes.tests.test_models import novo_participante
from relatorios.services import consultar_movimentacao_etaria_fmr


class CalculoEtarioTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(username="calculo_etario_ficticio")
        self.usuario.groups.add(Group.objects.get(name="Equipe"))
        self.motivo = MotivoDesligamento.objects.create(descricao="Motivo fictício")

    def pessoa(self, nascimento, entrada=date(2024, 1, 1), sexo="F", perfil=True):
        pessoa = novo_participante(data_nascimento=nascimento, sexo=sexo)
        pessoa.save()
        Movimentacao.objects.create(participante=pessoa, usuario=self.usuario, tipo="entrada", data=entrada)
        if perfil:  # Os serviços de cadastro gravam o perfil vigente desde a entrada.
            self.perfil(pessoa, entrada, sexo)
        return pessoa

    def perfil(self, pessoa, desde, sexo):
        return PerfilDemografico.objects.create(participante=pessoa, vigente_desde=desde, sexo=sexo,
                                                raca_cor="parda", identidade_genero="cisgenero")

    def mover(self, pessoa, tipo, dia):
        return movimentar_participante(usuario=self.usuario, participante_id=pessoa.pk, tipo=tipo,
            data=date(2024, 2, dia), motivo_id=self.motivo.pk if tipo == "desligamento" else None)

    def consultar(self):
        return consultar_movimentacao_etaria_fmr(usuario=self.usuario, ano=2024, mes=2)

    def linhas(self, resultado):
        return {(r["faixa"], r["sexo_codigo"]): r for r in resultado["linhas"]}

    def test_aniversario_no_dia_um_e_durante_o_mes_usam_a_mesma_referencia(self):
        self.pessoa(date(1959, 2, 1))
        self.pessoa(date(1959, 2, 15))
        resultado = self.consultar()
        linhas = self.linhas(resultado)
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
            "reativados": 1, "ingressaram_portal": 1, "sairam": 2, "permanecem": 1})
        for linha in resultado["linhas"]:
            self.assertEqual(linha["vieram_mes_anterior"] + linha["ingressaram"] + linha["reativados"] - linha["sairam"], linha["permanecem"])
            # Equação do portal da SMADS (Q4): o reativado entra em "ingressaram".
            self.assertEqual(linha["ingressaram_portal"], linha["ingressaram"] + linha["reativados"])
            self.assertEqual(linha["vieram_mes_anterior"] + linha["ingressaram_portal"] - linha["sairam"], linha["permanecem"])

    def test_entradas_nos_limites_do_mes_e_futuro_nao_alteram_passado(self):
        self.pessoa(date(1960, 1, 1), entrada=date(2024, 2, 1))
        self.pessoa(date(1960, 1, 1), entrada=date(2024, 2, 29))
        self.pessoa(date(1960, 1, 1), entrada=date(2024, 3, 1))
        resultado = self.consultar()["totais"]
        self.assertEqual((resultado["vieram_mes_anterior"], resultado["ingressaram"], resultado["permanecem"]), (0, 2, 2))

    def test_cadastro_pendente_fica_fora_sem_anular_a_tabela_e_menor_de_60_e_explicitado(self):
        # Antes: um cadastro sem entrada anulava a tabela inteira (totais None). Agora ele fica fora do cálculo
        # (listado como pendente na tela do FMR) e o restante é calculado.
        pessoa = self.pessoa(date(1980, 1, 1))
        resultado = self.consultar()
        self.assertEqual(resultado["totais"]["permanecem"], 0)
        self.assertEqual(resultado["fora_faixas"]["permanecem"], 1)
        self.assertEqual(resultado["menores_60"], 1)
        self.pessoa(date(1950, 1, 1))
        pessoa.movimentacoes.all().delete()
        resultado = self.consultar()
        self.assertEqual(resultado["totais"]["permanecem"], 1)
        self.assertEqual(resultado["fora_faixas"]["permanecem"], 0)
        self.assertEqual(resultado["menores_60"], 0)
        self.assertEqual(resultado["pendencias"], [])

    def test_status_inativo_ou_cancelado_fica_fora_sem_converter_status(self):
        inativo = self.pessoa(date(1950, 1, 1))
        cancelado = self.pessoa(date(1950, 1, 1))
        self.pessoa(date(1950, 1, 1))
        type(inativo).objects.filter(pk=inativo.pk).update(status="inativo")
        type(cancelado).objects.filter(pk=cancelado.pk).update(status="cancelado")
        resultado = self.consultar()
        self.assertEqual(resultado["totais"]["permanecem"], 1)
        inativo.refresh_from_db()
        cancelado.refresh_from_db()
        self.assertEqual((inativo.status, cancelado.status), ("inativo", "cancelado"))

    def test_sexo_vem_do_perfil_vigente_no_fim_do_mes_e_nao_do_cadastro_atual(self):
        mudou_no_mes = self.pessoa(date(1950, 1, 1), sexo="F")
        self.perfil(mudou_no_mes, date(2024, 2, 20), "M")
        mudou_depois = self.pessoa(date(1950, 1, 1), sexo="F")
        self.perfil(mudou_depois, date(2024, 3, 1), "M")
        cadastro_diverge = self.pessoa(date(1950, 1, 1), sexo="F", perfil=False)
        self.perfil(cadastro_diverge, date(2024, 1, 1), "M")  # Participante.sexo continua F
        linhas = self.linhas(self.consultar())
        self.assertEqual(linhas[("70–74", "M")]["permanecem"], 2)
        self.assertEqual(linhas[("70–74", "F")]["permanecem"], 1)

    def test_tabela_etaria_e_sexo_raca_usam_o_mesmo_sexo(self):
        pessoa = self.pessoa(date(1950, 1, 1), sexo="F")
        self.perfil(pessoa, date(2024, 2, 10), "M")
        from relatorios.services import consultar_perfil_demografico_fmr
        raca = consultar_perfil_demografico_fmr(usuario=self.usuario, ano=2024, mes=2)["blocos"][0]
        masculino = next(linha for linha in raca["linhas"] if linha["rotulo"] == "Masculino")
        totais = self.consultar()["totais"]
        self.assertEqual(masculino["valores"][-1], 1)
        self.assertEqual(self.linhas(self.consultar())[("70–74", "M")]["permanecem"], totais["permanecem"])

    def test_perfil_ausente_vira_pendencia_e_nao_zero(self):
        self.pessoa(date(1950, 1, 1))
        self.pessoa(date(1950, 1, 1), perfil=False)
        self.pessoa(date(1980, 1, 1), perfil=False)  # Menor de 60 não precisa de sexo: vai para fora das faixas.
        fonte = movimentacao_etaria_mensal(usuario=self.usuario, ano=2024, mes=2)
        self.assertEqual(fonte["sem_perfil"], 1)
        self.assertTrue(all(linha[campo] is None for linha in fonte["linhas"]
                            for campo in ("vieram_mes_anterior", "ingressaram", "reativados", "sairam", "permanecem")))
        self.assertTrue(all(valor is None for valor in fonte["totais"].values()))
        self.assertEqual(fonte["fora_faixas"]["permanecem"], 1)
        resultado = self.consultar()
        self.assertEqual([p["codigo"] for p in resultado["pendencias"]], ["PERFIL"])
        self.assertIsNone(resultado["totais"]["ingressaram_portal"])

    def test_perfil_posterior_ao_fim_do_mes_nao_completa_o_passado(self):
        pessoa = self.pessoa(date(1950, 1, 1), perfil=False)
        self.perfil(pessoa, date(2024, 3, 1), "F")
        self.assertEqual(movimentacao_etaria_mensal(usuario=self.usuario, ano=2024, mes=2)["sem_perfil"], 1)
        self.assertEqual(movimentacao_etaria_mensal(usuario=self.usuario, ano=2024, mes=3)["sem_perfil"], 0)

    def test_numero_de_consultas_nao_cresce_com_participantes(self):
        self.pessoa(date(1950, 1, 1))

        def contar():
            with CaptureQueriesContext(connection) as consultas:
                movimentacao_etaria_mensal(usuario=self.usuario, ano=2024, mes=2)
            return len(consultas)

        uma = contar()
        for _ in range(5):
            self.pessoa(date(1950, 1, 1), sexo="M")
        self.assertEqual(contar(), uma)
