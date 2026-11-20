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
})();
