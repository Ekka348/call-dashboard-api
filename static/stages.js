const STAGES = {
  "НДЗ": "5",
  "НДЗ 2": "9",
  "Перезвонить": "IN_PROCESS",
  "Приглашен к рекрутеру": "CONVERTED",
  "NEW": "NEW",
  "База ВВ": "UC_VTOOIM",
  "OLD": "11"
  "На согласовании": "UC_A2DF81"
};

const STAGE_LABELS = Object.entries(STAGES).reduce((acc, [label, id]) => {
  acc[id] = label;
  return acc;
}, {});

const WORK_STAGES = ["Перезвонить", "На согласовании": "UC_A2DF81" , "Приглашен к рекрутеру"];


function renderStageBlock(stage, info) {
  const container = document.getElementById("stats");
  const block = document.createElement("div");
  block.className = "stage-block";

  if (info.grouped) {
    block.innerHTML = `<h3>Стадия: ${stage}</h3><p>Всего: ${info.count}</p>`;
  } else {
    const rows = info.details
      .map(x => `<tr><td>${x.operator}</td><td>${x.count}</td></tr>`)
      .join("");
    block.innerHTML = `
      <h3>Стадия: ${stage}</h3>
      <table><thead><tr><th>Оператор</th><th>Количество</th></tr></thead>
      <tbody>${rows}</tbody></table>`;
  }

  return block;
}

async function fetchStages() {
  try {
    const res = await fetch("/api/leads/by-stage");
    const data = await res.json();
    if (!data || !data.data) return;

    const container = document.getElementById("stats");
    container.innerHTML = "";

    for (const [stage, info] of Object.entries(data.data)) {
      container.appendChild(renderStageBlock(stage, info));
    }

    document.getElementById("update-log").textContent =
      `Обновлено: ${new Date().toLocaleTimeString("ru-RU")}`;

  } catch (err) {
    console.error("Ошибка при загрузке стадий:", err);
  }
}

// ⏱️ Запуск при загрузке и каждые 2 минуты
window.onload = () => {
  fetchStages();
  setInterval(fetchStages, 120000); // 2 мин = 120 000 мс
};

