(() => {
  "use strict";
  document.querySelectorAll(".nci-tabela-rolavel").forEach(painel => {
    const cabecalho = painel.querySelector("thead");
    const corpo = painel.querySelector("tbody");
    if (!cabecalho || !corpo) return;
    const ajustar = () => {
      const quantidade = Number.parseInt(painel.dataset.linhasVisiveis, 10);
      if (quantidade > 0) {
        const linhas = Array.from(corpo.rows).slice(0, quantidade);
        const altura = Math.ceil(linhas.reduce((total, linha) => total + linha.getBoundingClientRect().height, 0));
        if (altura > 0 && corpo.style.maxHeight !== `${altura}px`) corpo.style.maxHeight = `${altura}px`;
      }
      const espaco = `${Math.max(0, corpo.offsetWidth - corpo.clientWidth)}px`;
      if (cabecalho.style.paddingInlineEnd !== espaco) cabecalho.style.paddingInlineEnd = espaco;
    };
    ajustar();
    if (window.ResizeObserver) {
      const observador = new ResizeObserver(ajustar);
      observador.observe(painel);
      observador.observe(corpo);
    }
    window.addEventListener("resize", ajustar);
    if (document.fonts) document.fonts.ready.then(ajustar);
  });
})();
