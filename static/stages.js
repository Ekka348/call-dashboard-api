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

document.addEventListener('DOMContentLoaded', () => {
  const stagesContainer = document.getElementById('fixed_stage_list');

  async function fetchStages() {
    try {
      const response = await fetch('/api/leads/stages');
      if (!response.ok) throw new Error(`Ошибка: ${response.status}`);

      const data = await response.json();
      renderStages(data.stages);
    } catch (error) {
      console.error('Не удалось загрузить стадии:', error);
      stagesContainer.innerHTML = '<li>⚠️ Ошибка загрузки стадий.</li>';
    }
  }

 function renderStages(stages) {
  const stagesContainer = document.getElementById('fixed_stage_list');
  stagesContainer.innerHTML = '';

  const infoStages = ['NEW', 'OLD', 'База ВВ'];
  const workStages = ['НДЗ', 'НДЗ 2', 'Перезвонить', 'Приглашен к рекрутеру'];

  // 🔷 Верхний блок — “информационные”
  const infoBlock = document.createElement('div');
  infoBlock.classList.add('block');
  infoBlock.innerHTML = '<h3>🗂️ Инфо-стадии</h3><ul></ul>';
  const infoList = infoBlock.querySelector('ul');

  // 🔶 Нижний блок — “рабочие”
  const workBlock = document.createElement('div');
  workBlock.classList.add('block');
  workBlock.innerHTML = '<h3>⚙️ Рабочие стадии</h3><ul></ul>';
  const workList = workBlock.querySelector('ul');

  stages.forEach(stage => {
    const li = document.createElement('li');
    li.innerHTML = `<span class="stage-name">${stage.name}</span>: ${stage.count}`;

    if (infoStages.includes(stage.name)) {
      infoList.appendChild(li);
    } else if (workStages.includes(stage.name)) {
      workList.appendChild(li);
    }
  });

  stagesContainer.appendChild(infoBlock);
  stagesContainer.appendChild(workBlock);
}


  fetchStages();
});

window.onload = () => {
  loadFixedStages();
};
