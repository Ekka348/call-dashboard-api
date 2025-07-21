function showStageLoading(stage) {
  document.getElementById("spinner").style.display = "inline";
  document.getElementById("status").style.color = "gray";
  document.getElementById("status").innerText = `🔄 Обновляем: ${stage}`;
}

function hideLoading(success = true) {
  const now = new Date().toLocaleTimeString();
  document.getElementById("spinner").style.display = "none";
  document.getElementById("status").style.color = success ? "#28a745" : "red";
  document.getElementById("status").innerText = success
    ? `✅ Обновлено: ${now} — успешно`
    : `❌ Ошибка обновления`;
}

function getDateParams() {
  const range = document.getElementById("range").value;
  let params = `range=${range}`;
  if (range === "custom") {
    const start = document.getElementById("startdate").value;
    const end = document.getElementById("enddate").value;
    if (start && end) params += `&start=${start}&end=${end}`;
  }
  return params;
}

async function loadStatsFor(stage, targetId) {
  try {
    showStageLoading(stage);
    const params = getDateParams();
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

async function updateLoop() {
  await loadStatsFor("НДЗ", "report_ndz");
  await loadStatsFor("НДЗ 2", "report_ndz2");
  await loadStatsFor("Перезвонить", "report_call");
  await loadStatsFor("Приглашен к рекрутеру", "report_recruiter");
  hideLoading(true);
  requestAnimationFrame(() => setTimeout(updateLoop, 100)); // запуск снова
}

function attachReactiveListeners() {
  ["range", "startdate", "enddate"].forEach(id => {
    document.getElementById(id).onchange = () => updateLoop();
  });
}

window.onload = () => {
  attachReactiveListeners();
  updateLoop(); // бесконечный старт
};


