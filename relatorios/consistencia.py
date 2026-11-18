"""Conferências do FMR sobre os valores autorizados para a consulta mensal."""


def verificar_consistencia(dados):
    avisos = []

    def avisar(secao, campo, mensagem):
        avisos.append({"secao": secao, "campo": campo, "mensagem": mensagem})

    permanentes = dados["permanentes"]["total"]
    if permanentes is not None and permanentes < 0:
        avisar("participantes-permanecem", "Permanentes",
               f"O total no último dia do mês é negativo ({permanentes}).")

    for linha in dados["movimentacao_etaria"]["linhas"]:
        anterior, entradas, retornos, saidas, fechamento = (
            linha[chave] for chave in ("vieram_mes_anterior", "ingressaram", "reativados", "sairam", "permanecem")
        )
        if None in (anterior, entradas, retornos, saidas, fechamento):
            continue
        saldo = anterior + entradas + retornos - saidas
        if saldo != fechamento or fechamento < 0:
            avisar("movimentacao-etaria", f"Movimentação · {linha['faixa']} · {linha['sexo']}",
                   f"O saldo de anteriores, ingressos, reativações e saídas é "
                   f"{anterior} + {entradas} + {retornos} − {saidas} = {saldo}. "
                   f"O fechamento informado é {fechamento} e deve coincidir com o saldo e ser pelo menos zero.")

    # O total de eventos inclui também as saídas fora das faixas etárias oficiais.
    tempo = dados["tempo_permanencia"]
    total_saidas = tempo["total_desligamentos"]
    for bloco, secao, campo in (
        (dados["desligamentos_motivo"], "desligamentos-motivo", "Saídas por motivo"),
        (tempo, "tempo-permanencia", "Saídas por tempo de permanência"),
    ):
        if bloco["total"] is None or total_saidas is None:
            continue
        quantidades = [linha["quantidade"] for linha in bloco["linhas"]]
        if None in quantidades:
            continue
        soma = sum(quantidades)
        if soma != total_saidas or soma != bloco["total"]:
            avisar(secao, campo, f"A soma das quantidades é {soma} e o total da tabela é {bloco['total']}. "
                   f"O mês registra {total_saidas} desligamento(s).")

    social = {linha["codigo"]: linha["quantidade"] for linha in dados["situacao_social"]["linhas"]}
    sozinhos = social.get("moram_sozinhos")
    com_apoio = social.get("moram_sozinhos_com_apoio")
    if None not in (com_apoio, sozinhos) and com_apoio > sozinhos:
        avisar("indicadores-sociais", "Apoio da família ou comunidade",
               f"A quantidade de pessoas que moram sozinhas e têm apoio ({com_apoio}) "
               f"supera o total de pessoas que moram sozinhas ({sozinhos}).")

    if permanentes is None:
        return avisos
    if sozinhos is not None and sozinhos > permanentes:
        avisar("indicadores-sociais", "Pessoas que moram sozinhas",
               f"A quantidade de pessoas que moram sozinhas ({sozinhos}) supera o total de permanentes ({permanentes}).")

    for bloco in dados["perfil_demografico"]["blocos"]:
        total = bloco["total"]
        if total is not None and total != permanentes:
            avisar(f"demografico-{bloco['codigo']}", bloco["titulo"],
                   f"O total classificado é {total}. No último dia do mês permanecem {permanentes} pessoa(s).")

    presencas = dados.get("presencas")
    if presencas:
        criterio = presencas["criterio"]
        if criterio == "ocorrencias":
            explicacao = "A contagem por aula pode incluir a mesma pessoa mais de uma vez no dia."
        else:
            explicacao = "A contagem considera cada pessoa uma vez no dia."
        for dia in presencas["dias"]:
            quantidade = dia[criterio]
            if quantidade > permanentes:
                avisar("presencas-por-data", f"Presenças em {dia['data']:%d/%m/%Y}",
                       f"A contagem do dia ({quantidade}) supera o total de permanentes no fechamento "
                       f"({permanentes}). {explicacao} Confira os valores para a transcrição ao FMR.")
    return avisos
