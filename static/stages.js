<script>
const STAGES = {
  "НДЗ": "5",
  "НДЗ 2": "9",
  "Перезвонить": "IN_PROCESS",
  "Приглашен к рекрутеру": "CONVERTED",
  "NEW": "NEW",
  "OLD": "11",
  "База ВВ": "UC_VTOOIM"
};

const WORK_STAGES = ["НДЗ", "НДЗ 2", "Перезвонить", "Приглашен к рекрутеру"];

function getDateParams() {
  const now = new Date();
  const startOfDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const start = startOfDay.toISOString().slice(0, 19).replace("T", " ");
  const end = now.toISOString().slice(0, 19).replace("T", " ");
  return `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`;
}

async function fetchStageCount(stageCode) {
  const params = getDateParams();
  const res = await fetch(`/summary_stage?stage=${encodeURIComponent(stageCode)}&${params}`);
  const data = await res.json();
  return data.count ?? 0;
}

async function loadFixedStages() {
  const list = document.getElementById("fixed_stage_list");
  list.innerHTML = "";
  for (const [name, code] of Object.entries(STAGES)) {
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
    table.innerHTML = `<tr><th>${stage}</th><th>Лидов</th></tr>`;
    for (const [uid, count] of Object.entries(operators)) {
      const row = document.createElement("tr");
      row.innerHTML = `<td>${uid}</td><td>${count}</td>`;
      table.appendChild(row);
    }
    block.appendChild(table);
    container.appendChild(block);
  }
}

async function updateDashboard() {
  try {
    await loadFixedStages();

    const res = await fetch("/api/leads/all");
    const data = await res.json();
    const grouped = groupLeadsByStageAndUser(data.leads);
    renderOperatorTables(grouped);

    const now = new Date().toLocaleTimeString();
    document.getElementById("last-update").textContent = now;
  } catch (err) {
    document.getElementById("last-update").textContent = "⚠ Ошибка обновления";
  }
}

// ⏱ Автообновление каждые 30 сек
updateDashboard();
setInterval(updateDashboard, 30000);
</script>
