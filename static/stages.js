let autoRefresh = true;
let refreshInterval;

function showLoading(message = "Загрузка...") {
  document.getElementById("spinner").style.display = "inline";
  document.getElementById("status").style.color = "gray";
  document.getElementById("status").innerText = `🌀 ${message}`;
}

function hideLoading(success = true) {
  const now = new Date().toLocaleTimeString();
  document.getElementById("spinner").style.display = "none";
  document.getElementById("status").style.color = success ? "#28a745" : "red";
  document.getElementById("status").innerText = success
    ? `✅ Обновлено: ${now} — успешно`
    : `❌ Обновление не удалось`;
}

async function loadStatsFor(stage, targetId) {
  try {
    const range = document.getElementById("range").value;
    const res = await fetch(`/stats_data?label=${encodeURIComponent(stage)}&range=${range}`);
    const data = await res.json();
    renderMiniTable(data, targetId);
  } catch {
    document.getElementById(targetId).innerHTML = `<p>❌ Ошибка загрузки для стадии "${stage}"</p>`;
  }
}

function renderMiniTable(data, targetId) {
  const sorted = [];
  for (let i = 0; i < data.labels.length; i++) {
    sorted.push({ name: data.labels[i], count: data.values[i] });
  }
  sorted.sort((a, b) => b.count - a.count);

  let html = `<h4>📋 ${data.stage}</h4>`;
  html += `<p>Всего лидов: ${data.total}</p><table><tr><th>Сотрудник</th><th>Лидов</th></tr>`;
  for (const row of sorted) {
    html += `<tr><td>${row.name}</td><td>${row.count}</td></tr>`;
  }
  html += `</table>`;
  document.getElementById(targetId).innerHTML = html;
}

function updateAllStages() {
  showLoading("🔄 Обновляем все стадии...");
  loadStatsFor("НДЗ", "report_ndz");
  loadStatsFor("НДЗ 2", "report_ndz2");
  loadStatsFor("Перезвонить", "report_call");
  loadStatsFor("Приглашен к рекрутеру", "report_recruiter");
  hideLoading(true);
}

function toggleAutoRefresh() {
  autoRefresh = !autoRefresh;
  document.getElementById("autostatus").innerText = autoRefresh ? "ВКЛ" : "ВЫКЛ";
  if (!autoRefresh) clearInterval(refreshInterval);
  else startAutoRefresh();
}

function startAutoRefresh() {
  refreshInterval = setInterval(updateAllStages, 120000);
}

window.onload = () => {
  updateAllStages();
  startAutoRefresh();
};
