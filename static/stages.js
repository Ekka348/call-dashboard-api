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

function groupLeadsByStageAndUser(leads) {
  const workStages = ['НДЗ', 'НДЗ 2', 'Перезвонить', 'Приглашен к рекрутеру'];
  const stageByCode = Object.entries(STAGES).reduce((acc, [name, code]) => {
    acc[code] = name;
    return acc;
  }, {});

  const result = {};

  leads.forEach(lead => {
    const stageName = stageByCode[lead.STAGE_ID];
    const userId = lead.ASSIGNED_BY_ID;

    if (workStages.includes(stageName)) {
      if (!result[stageName]) result[stageName] = {};
      if (!result[stageName][userId]) result[stageName][userId] = 0;

      result[stageName][userId]++;
    }
  });

  return result;
}

function renderOperatorTables(data) {
  const container = document.getElementById('operator_stage_tables');
  container.innerHTML = '';

  for (const stage in data) {
    const operators = data[stage];
    if (!operators || Object

window.onload = () => {
  loadFixedStages();
};
