const STAGE_LABELS = ["Перезвонить", "На согласовании", "Приглашен к рекрутеру"];

async function updateStage(stageName) {
  try {
    const response = await fetch(`/update_stage/${stageName}`);
    if (!response.ok) {
      throw new Error(`Ошибка загрузки: ${response.status}`);
    }
    const data = await response.json();
    const stageData = data[stageName];
    const container = document.getElementById(`table-${stageName}`);
    container.innerHTML = '';

    if (stageData.grouped) {
      container.innerHTML = `<p>Всего лидов: ${stageData.count}</p>`;
    } else if (stageData.details && stageData.details.length > 0) {
      const list = document.createElement('ul');
      stageData.details.forEach(item => {
        const li = document.createElement('li');
        li.textContent = `${item.operator} — ${item.count}`;
        list.appendChild(li);
      });
      container.appendChild(list);
    } else {
      container.innerHTML = `<p>Нет лидов в стадии</p>`;
    }
  } catch (error) {
    console.error(error);
    const container = document.getElementById(`table-${stageName}`);
    container.innerHTML = `<p>Ошибка загрузки данных</p>`;
  }
}

fetch("/update_stage/Перезвонить?range=week")

window.onload = () => {
  STAGE_LABELS.forEach(updateStage);
};
