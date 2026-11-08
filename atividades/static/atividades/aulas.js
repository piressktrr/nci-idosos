(() => {
  "use strict";
  const form = document.getElementById("form-aula");
  if (!form) return;
  const config = JSON.parse(document.getElementById("sugestoes-aula").textContent);
  const tipo = form.elements.namedItem("tipo");
  const data = form.elements.namedItem("data");
  const inicio = form.elements.namedItem("inicio");
  const fim = form.elements.namedItem("fim");
  const selecao = document.getElementById("selecao-grade");
  const escolha = document.getElementById("horario-sugerido");
  const aviso = document.getElementById("aviso-sugestao");
  const horaAtual = () => new Intl.DateTimeFormat("en-GB", {
    timeZone: config.fuso, hourCycle: "h23", hour: "2-digit", minute: "2-digit",
  }).format(new Date());
  const normalizarHora = valor => valor.slice(0, 5);
  let ultimaSugestao = form.dataset.bound === "false" ? { inicio: inicio.value, fim: fim.value } : null;
  let horariosDoDia = [];

  function aplicar(horario) {
    inicio.value = normalizarHora(horario.inicio);
    fim.value = normalizarHora(horario.fim);
    ultimaSugestao = { inicio: inicio.value, fim: fim.value };
    aviso.textContent = "Horários sugeridos pela grade. Você pode ajustar os valores antes de registrar.";
  }

  function atualizar(aplicarSugestao) {
    const dia = data.value ? (new Date(`${data.value}T00:00:00Z`).getUTCDay() + 6) % 7 : null;
    horariosDoDia = tipo.value === "regular" ? config.horarios.filter(item => item.dia_semana === dia) : [];
    escolha.replaceChildren(new Option("Selecione um horário ou preencha manualmente", ""));
    for (const item of horariosDoDia) {
      escolha.add(new Option(`${normalizarHora(item.inicio)} – ${normalizarHora(item.fim)}`, String(item.pk)));
    }
    selecao.hidden = horariosDoDia.length < 2;
    if (aplicarSugestao && ultimaSugestao) {
      // Remove só valores ainda iguais à sugestão anterior; preserva ajustes manuais.
      if (normalizarHora(inicio.value) === normalizarHora(ultimaSugestao.inicio)) inicio.value = "";
      if (normalizarHora(fim.value) === normalizarHora(ultimaSugestao.fim)) fim.value = horaAtual();
      ultimaSugestao = null;
    }
    if (horariosDoDia.length === 1) {
      if (aplicarSugestao) aplicar(horariosDoDia[0]);
      else aviso.textContent = "Há um horário da grade para este dia. Confira os valores informados.";
    } else if (horariosDoDia.length > 1) {
      aviso.textContent = "Há mais de um horário neste dia. Escolha uma faixa da grade ou preencha manualmente.";
    } else {
      aviso.textContent = tipo.value === "regular"
        ? "Sem horário sugerido para este dia. Você pode informar os horários manualmente."
        : "Confira os horários efetivos antes de registrar a aula.";
    }
  }

  tipo.addEventListener("change", () => atualizar(true));
  data.addEventListener("change", () => atualizar(true));
  escolha.addEventListener("change", () => {
    const horario = horariosDoDia.find(item => String(item.pk) === escolha.value);
    if (horario) aplicar(horario);
  });
  // Não sobrescreve dados reapresentados após erro de validação no backend.
  atualizar(false);
})();
