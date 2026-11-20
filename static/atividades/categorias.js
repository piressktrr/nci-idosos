(() => {
  "use strict";
  const formulario = document.getElementById("formulario-categoria");
  const lista = document.getElementById("lista-categorias");
  if (!formulario || !lista) return;
  const tabela = lista.querySelector(".table-scroll");
  if (!tabela) return;
  const corpo = tabela.querySelector("tbody");
  const cabecalho = tabela.querySelector("thead");
  if (!corpo || !cabecalho) return;
  const ajustar = () => {
    const limite = formulario.getBoundingClientRect().height * 2;
    const estilo = getComputedStyle(lista);
    const numero = valor => parseFloat(valor) || 0;
    const bordas = numero(estilo.paddingTop) + numero(estilo.paddingBottom)
      + numero(estilo.borderTopWidth) + numero(estilo.borderBottomWidth);
    const cabecalhos = Array.from(lista.children).filter(item => item !== tabela)
      .reduce((altura, item) => {
        const css = getComputedStyle(item);
        return altura + item.getBoundingClientRect().height + numero(css.marginTop) + numero(css.marginBottom);
      }, 0);
    const estiloTabela = getComputedStyle(tabela);
    const moldura = numero(estiloTabela.borderTopWidth) + numero(estiloTabela.borderBottomWidth);
    const rolagemHorizontal = Math.max(0, tabela.offsetHeight - tabela.clientHeight - moldura);
    corpo.style.maxHeight = `${Math.max(80, limite - bordas - cabecalhos
      - cabecalho.getBoundingClientRect().height - moldura - rolagemHorizontal)}px`;
  };
  ajustar();
  if (window.ResizeObserver) new ResizeObserver(ajustar).observe(formulario);
  window.addEventListener("resize", ajustar);
})();
