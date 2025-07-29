<script>
const STAGES = {
  "НДЗ": "5",
  "НДЗ 2": "9",
  "Перезвонить": "IN_PROCESS",
  "Приглашен к рекрутеру": "CONVERTED",
  "NEW": "NEW",
  "OLD": "UC_VTOOIM",
  "База ВВ": "11"
};

fetch("/api/leads/by-stage")
  .then(res => res.json())
  .then(data => {
    const container = document.getElementById("stats");
    container.innerHTML = "";

    for (const [stage, info] of Object.entries(data.data)) {
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

      container.appendChild(block);
    }
  });


const WORK_STAGES = ["НДЗ", "НДЗ 2", "Перезвонить", "Приглашен к рекрутеру"];

function getDateParams() {
  const now = new Date();
  const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  const start = startOfDay.toISOString().slice(0, 19).replace("T", " ");
  const end = now.toISOString().slice(0, 19).replace("T", " ");

  return `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
}

fetch("/api/leads/info-stages-today")
  .then(res => res.json())
  .then(data => {
    const list = document.getElementById("info-list");
    list.innerHTML = "";
    data.info.forEach(stage => {
      const li = document.createElement("li");
      li.textContent = `${stage.name}: ${stage.count} лидов`;
      list.appendChild(li);
    });
  });


async function fetchStageCount(stageCode) {
  const res = await fetch("/api/leads/by-stage");
  const data = await res.json();

  const stageLabel = STAGE_LABELS[stageCode];
  return data.data?.[stageLabel]?.count ?? 0;
}


async function loadFixedStages() {
  const stages = Object.entries(STAGES);
  const list = document.getElementById("fixed_stage_list");
  list.innerHTML = ""; // очищаем "⏳ Загрузка данных..."

  for (const [name, code] of stages) {
    const count = await fetchStageCount(code);
    const item = document.createElement("li");
    item.textContent = `${name}: ${count} лидов`;
    list.appendChild(item);
  }
}

function groupLeadsByStageAndUser(leads) {
  const stageByCode = Object.entries(STAGES).reduce((acc, [name, code]) => {
    acc[code] = name;
    return acc;
  }, {});

  const result = {};

  leads.forEach(lead => {
    const stageName = stageByCode[lead.STAGE_ID];
    const userId = lead.ASSIGNED_BY_ID;

    if (WORK_STAGES.includes(stageName)) {
      if (!result[stageName]) result[stageName] = {};
      if (!result[stageName][userId]) result[stageName][userId] = 0;
      result[stageName][userId]++;
    }
  });

  return result;
}

function renderOperatorTables(data) {
  const container = document.getElementById("operator_stage_tables");
  container.innerHTML = "";

  for (const stage in data) {
    const operators = data[stage];
    if (!operators || Object.keys(operators).length === 0) continue;

    const block = document.createElement("div");
    block.className = "stage-block";

    const table = document.createElement("table");

    const header = document.createElement("tr");
    header.innerHTML = `<th>${stage}</th><th>Лидов</th>`;
    table.appendChild(header);

    for (const [uid, count] of Object.entries(operators)) {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${uid}</td><td>${count}</td>`;
      table.appendChild(row);
    }

    block.appendChild(table);
    container.appendChild(block);
  }
}

async function loadOperatorTables() {
  const res = await fetch("/api/leads/all");
  const data = await res.json();
  const grouped = groupLeadsByStageAndUser(data.leads);
  renderOperatorTables(grouped);
}

window.onload = () => {
  loadFixedStages();
  loadOperatorTables();
};
</script>
