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
      return null; // период не выбран
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

async function loadTotals() {
  try {
    const res = await fetch("/totals");
    const html = await res.text();
    document.getElementById("totals_table").innerHTML = html;
  } catch (e) {
    document.getElementById("totals_table").innerHTML = "⚠️ Ошибка загрузки данных";
    console.error("Ошибка /totals:", e);
  }
}

async function updateLoop() {
  const params = getDateParams();
  if (!params) {
    showWarning();
    return setTimeout(update
