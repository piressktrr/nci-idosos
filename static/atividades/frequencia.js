(() => {
  "use strict";
  document.querySelectorAll("[data-justificativa]").forEach(linha => {
    const nomeCampo = linha.dataset.registro || `registro_${linha.dataset.justificativa}`;
    const radios = document.querySelectorAll(`input[name="${nomeCampo}"]`);
    function atualizar() {
      const justificada = Array.from(radios).some(radio => radio.checked && radio.value === "ausente_justificado");
      linha.hidden = !justificada;
      linha.querySelectorAll("select, textarea").forEach(campo => { campo.disabled = !justificada; });
    }
    radios.forEach(radio => radio.addEventListener("change", atualizar));
    atualizar();
  });
})();
