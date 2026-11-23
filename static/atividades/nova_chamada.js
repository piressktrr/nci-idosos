(() => {
  "use strict";
  const form = document.getElementById("escolher-atividade");
  if (!form) return;
  form.elements.namedItem("atividade").addEventListener("change", () => form.requestSubmit());
  const recarregar = document.getElementById("recarregar-participantes");
  if (recarregar) recarregar.addEventListener("click", () => {
    const aula = document.getElementById("form-aula");
    const data = aula.elements.namedItem("data");
    if (!data.reportValidity()) return;
    const destino = new URL(window.location.href);
    destino.search = new URLSearchParams({atividade: aula.elements.namedItem("atividade").value, data: data.value}).toString();
    window.location.assign(destino.href);
  });
  // Um duplo clique em "Salvar chamada" não envia a chamada duas vezes (o servidor também recusa aula repetida).
  const formAula = document.getElementById("form-aula");
  const salvar = formAula && formAula.querySelector("[data-salvar-chamada]");
  if (salvar) {
    const texto = salvar.textContent;
    formAula.addEventListener("submit", evento => {
      if (salvar.disabled) { evento.preventDefault(); return; }
      salvar.disabled = true;
      salvar.textContent = "Salvando…";
    });
    // Ao voltar pelo histórico do navegador, a página restaurada precisa do botão ativo de novo.
    window.addEventListener("pageshow", () => { salvar.disabled = false; salvar.textContent = texto; });
  }
})();
