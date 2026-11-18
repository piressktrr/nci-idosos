(() => {
  "use strict";
  const form = document.getElementById("escolher-atividade");
  if (!form) return;
  form.elements.namedItem("atividade").addEventListener("change", () => form.requestSubmit());
})();
