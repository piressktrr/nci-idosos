(() => {
  "use strict";
  const formulario = document.getElementById("formulario-categoria");
  const lista = document.getElementById("lista-categorias");
  if (!formulario || !lista) return;
  const tabela = lista.querySelector(".table-scroll");
  if (!tabela) return;
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
    lista.style.maxHeight = `${limite}px`;
    tabela.style.maxHeight = `${Math.max(0, limite - bordas - cabecalhos)}px`;
  };
  ajustar();
  if (window.ResizeObserver) new ResizeObserver(ajustar).observe(formulario);
  window.addEventListener("resize", ajustar);
})();
