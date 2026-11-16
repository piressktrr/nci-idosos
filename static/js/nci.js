// Funções pequenas usadas pelo Alpine.js nos templates. Carregar antes do alpine.min.js.

// Máscara de telefone durante a digitação. O servidor guarda só os dígitos e valida de novo.
window.mascaraTelefone = function (campo) {
  const d = campo.value.replace(/\D/g, "").slice(0, 11);
  let v = d;
  if (d.length > 2) v = `(${d.slice(0, 2)}) ${d.slice(2)}`;
  if (d.length > 6) {
    const meio = d.length === 11 ? 7 : 6;
    v = `(${d.slice(0, 2)}) ${d.slice(2, meio)}-${d.slice(meio)}`;
  }
  campo.value = v;
};
