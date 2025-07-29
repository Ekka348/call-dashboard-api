const STAGES = {
  "НДЗ": "5",
  "НДЗ 2": "9",
  "Перезвонить": "IN_PROCESS",
  "Приглашен к рекрутеру": "CONVERTED",
  "NEW": "NEW",
  "OLD": "11",
  "База ВВ": "UC_VTOOIM"
};

function getDateParams() {
  const now = new Date().toISOString().slice(0, 19).replace("T", " ");
  return `start=2020-01-01 00:00:00&end=${encodeURIComponent(now)}`;
}

async function fetchStageCount(stageCode) {
  const params = getDateParams();
  const res = await fetch(`/summary_stage?stage=${encodeURIComponent(stageCode)}&${params}`);
  const data = await res.json();
  return data.count ?? 0;
}

async function loadFixedStages() {
  const ul = document.getElementById("fixed_stage_list");
  ul.innerHTML = "⏳ Получение данных...";

  const results = [];
  for (const [name, code] of Object.entries(STAGES)) {
    const count = await fetchStageCount(code);
    results.push(`<li><span class="stage-name">${name}</span>: ${count}</li>`);
  }

  ul.innerHTML = results.join("");
}

window.onload = () => {
  loadFixedStages();
};
