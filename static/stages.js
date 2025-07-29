function showStageLoading(stage) {
  const spinner = document.getElementById("spinner");
  spinner.style.display = "block";
  spinner.innerText = `🔄 Обновляем: ${stage}`;
}

function showWarning(msg = "⚠️ Выберите период") {
  const spinner = document.getElementById("spinner");
  spinner.style.display = "block";
  spinner.innerText = msg;
}

function hideLoading(success = true) {
  const now = new Date().toLocaleTimeString();
  const update = document.getElementById("lastupdate");
  update.style.color = success ? "#28a745" : "red";
  update.innerText = success
    ? `✅ Последнее обновление: ${now}`
    : `❌ Ошибка обновления`;
  document.getElementById("spinner").style.display = "none";
}

function getDateParams() {
  const range = document.getElementById("range").value;
  let params = `range=${range}`;
  if (range === "custom") {
    const start = document.getElementById("startdate").value;
    const end = document.getElementById("enddate").value;
    if (start && end) {
      params += `&start=${start}&end=${end}`;
    } else {
      return null;
    }
  }
  return params;
}

async function loadStatsFor(stage, targetId) {
  try {
    showStageLoading(stage);
    const params = getDateParams();
    if (!params) {
      showWarning();
      return;
    }
    const res = await fetch(`/stats_data?label=${encodeURIComponent(stage)}&${params}`);
    const data = await res.json();
    renderMiniTable(data, targetId);
  } catch {
    document.getElementById(targetId).innerHTML =
      `<p>❌ Ошибка загрузки для стадии "${stage}"</p>`;
  }
}

function renderMiniTable(data, targetId) {
  const sorted = data.labels.map((name, i) => ({ name, count: data.values[i] }))
    .sort((a, b) => b.count - a.count);

  let html = `<h4>📋 ${data.stage}</h4>`;
  html += `<p>Всего лидов: ${data.total}</p><table><tr><th>Сотрудник</th><th>Лидов</th></tr>`;
  for (const row of sorted) {
    html += `<tr><td>${row.name}</td><td>${row.count}</td></tr>`;
  }
  html += `</table>`;
  document.getElementById(targetId).innerHTML = html;
}

async function loadSummaryOLD() {
  try {
    const params = getDateParams();
    if (!params) {
      document.getElementById("vv_count").innerText = "⏳ Укажите период";
      return;
    }
    const res = await fetch("/summary_vv?" + params);
    const data = await res.json();
    document.getElementById("vv_count").innerText = data.count ?? "Нет данных";
  } catch {
    document.getElementById("vv_count").innerText = "❌ Ошибка загрузки";
  }
}


async function updateLoop() {
  const params = getDateParams();
  if (!params) {
    showWarning();
    return setTimeout(updateLoop, 1000);
  }

  await loadStatsFor("НДЗ", "report_ndz");
  await loadStatsFor("НДЗ 2", "report_ndz2");
  await loadStatsFor("Перезвонить", "report_call");
  await loadStatsFor("Приглашен к рекрутеру", "report_recruiter");
  await loadSummaryOLD(); // 🎯 Добавлено сюда
  await loadSummaryVV();

  hideLoading(true);
  requestAnimationFrame(() => setTimeout(updateLoop, 100));
}

function attachReactiveListeners() {
  ["range", "startdate", "enddate"].forEach(id => {
    document.getElementById(id).onchange = () => updateLoop();
  });
}

window.onload = () => {
  attachReactiveListeners();
  updateLoop();
};
