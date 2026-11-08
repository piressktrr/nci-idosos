(() => {
  "use strict";
  document.querySelectorAll("[data-justificativa]").forEach(linha => {
    const radios = document.querySelectorAll(`input[name="registro_${linha.dataset.justificativa}"]`);
    function atualizar() {
      const justificada = Array.from(radios).some(radio => radio.checked && radio.value === "ausente_justificado");
      linha.hidden = !justificada;
      linha.querySelectorAll("select, textarea").forEach(campo => { campo.disabled = !justificada; });
    }
    radios.forEach(radio => radio.addEventListener("change", atualizar));
    atualizar();
  });
})();
