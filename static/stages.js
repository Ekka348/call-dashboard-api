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

async function loadStatsFor(stage, targetId, color) {
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
  html += `</table><div class="chart-container" id="${targetId}_chart"></div>`;
  document.getElementById(targetId).innerHTML = html;
}

function renderMiniChart(data, chartId, color) {
  const trace = {
    x: data.labels,
    y: data.values,
    type: "bar",
    marker: { color }
  };
  const layout = {
    margin: { t: 20, l: 30, r: 20, b: 80 },
    height: 180,
    xaxis: { tickangle: -45 },
    yaxis: { title: "Лидов", automargin: true },
  };
  Plotly.newPlot(chartId, [trace], layout);
}

function updateAllStages() {
  showLoading("🔄 Обновляем все стадии...");
  loadStatsFor("НДЗ", "report_ndz", "#007bff");
  loadStatsFor("НДЗ 2", "report_ndz2", "#6f42c1");
  loadStatsFor("Перезвонить", "report_call", "#fd7e14");
  loadStatsFor("Приглашен к рекрутеру", "report_recruiter", "#28a745");
  hideLoading(true);
}

window.onload = () => {
  document.getElementById("range").onchange = updateAllStages;
  updateAllStages();
  refreshInterval = setInterval(updateAllStages, 120000);
};

