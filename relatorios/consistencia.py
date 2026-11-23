"""Conferências do FMR sobre os valores autorizados para a consulta mensal."""


def verificar_consistencia(dados):
    avisos = []

    def avisar(secao, campo, mensagem):
        avisos.append({"secao": secao, "campo": campo, "mensagem": mensagem})

    permanentes = dados["permanentes"]["total"]
    if permanentes is not None and permanentes < 0:
        avisar("participantes-permanecem", "Permanentes",
               f"O total no último dia do mês é negativo ({permanentes}).")

    # RN-FMR-01 na forma do portal da SMADS (Q4): vieram + ingressaram (portal) − saíram = permanecem,
    # com ingressaram (portal) = ingressaram + reativados.
    etaria = dados["movimentacao_etaria"]
    for linha in etaria["linhas"]:
        anterior, entradas, retornos, saidas, fechamento = (
            linha[chave] for chave in ("vieram_mes_anterior", "ingressaram", "reativados", "sairam", "permanecem")
        )
        if None in (anterior, entradas, retornos, saidas, fechamento):
            continue
        campo = f"Movimentação · {linha['faixa']} · {linha['sexo']}"
        portal = linha.get("ingressaram_portal", entradas + retornos)
        if portal != entradas + retornos:
            avisar("movimentacao-etaria", campo,
                   f"Ingressaram (portal) é {portal}, mas deve ser ingressaram + reativados = {entradas + retornos}.")
        saldo = anterior + portal - saidas
        if saldo != fechamento or fechamento < 0:
            avisar("movimentacao-etaria", campo,
                   f"Pela equação do portal, vieram + ingressaram (portal) − saíram = "
                   f"{anterior} + {portal} − {saidas} = {saldo}. "
                   f"O fechamento informado é {fechamento} e deve coincidir com o saldo e ser pelo menos zero.")

    # Tabela por faixa + menores de 60 anos (fora das faixas) = totais dos outros blocos, que contam todas as idades.
    pendentes = dados["permanentes"].get("cadastros_pendentes")
    dica = (f" Há {len(pendentes)} cadastro(s) fora do cálculo, que podem explicar a diferença." if pendentes else "")
    totais, fora = etaria.get("totais") or {}, etaria.get("fora_faixas") or {}
    for chave, rotulo, outro, descricao in (
        ("permanecem", "Permanecem", permanentes, "o total de permanentes no fim do mês"),
        ("sairam", "Saíram", dados["desligamentos_motivo"].get("total"), "o total de desligamentos por motivo"),
        ("ingressaram", "Ingressaram", dados.get("ingressantes_encaminhamento", {}).get("total_ingressantes"),
         "o total de ingressantes por encaminhamento"),
    ):
        tabela, menores = totais.get(chave), fora.get(chave)
        if None in (tabela, menores, outro):
            continue
        if tabela + menores != outro:
            avisar("movimentacao-etaria", f"Movimentação · total de {rotulo}",
                   f"A tabela por faixa ({tabela}) mais os menores de 60 anos ({menores}) somam {tabela + menores}, "
                   f"mas {descricao} é {outro}.{dica}")

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

    # RF-FMR-10: as categorias repartem as aulas e as presenças do mês, sem sobra nem duplicidade.
    categorias = dados.get("categorias_atividades") or {}
    indicadores = {indicador["codigo"]: indicador["valor"] for indicador in dados.get("indicadores", [])}
    for chave, codigo, rotulo in (("total_aulas", "aulas_realizadas", "Aulas por categoria"),
                                  ("total_participacoes", "participacoes", "Participações por categoria")):
        soma, geral = categorias.get(chave), indicadores.get(codigo)
        if None not in (soma, geral) and soma != geral:
            avisar("categorias-atividades", rotulo,
                   f"A soma por categoria é {soma}, mas o total do mês é {geral}.")

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
