const STAGES = [
  { label: "НДЗ", container: "report_ndz" },
  { label: "НДЗ 2", container: "report_ndz2" },
  { label: "Перезвонить", container: "report_call" },
  { label: "Приглашен к рекрутеру", container: "report_recruiter" }
];

function renderTable(title, labels, values, total) {
  let rows = labels.map((label, i) => `<tr><td>${label}</td><td>${values[i]}</td></tr>`).join("");
  return `<table><caption>${title}</caption><tr><th>Сотрудник</th><th>Лидов</th></tr>${rows}<tr><td><strong>Итого</strong></td><td><strong>${total}</strong></td></tr></table>`;
}

function loadStats(stageLabel, containerId) {
  fetch(`/stats_data?label=${encodeURIComponent(stageLabel)}`)
    .then(r => r.json())
    .then(data => {
      const html = renderTable(`📋 ${data.stage}`, data.labels, data.values, data.total);
      document.getElementById(containerId).innerHTML = html;
    });
}

function loadTotals() {
  fetch("/totals")
    .then(r => r.json())
    .then(data => {
      let rows = data.data.map(item =>
        `<tr><td>${item.label}</td><td>${item.count}</td></tr>`
      ).join("");
      const html = `<table><tr><th>Стадия</th><th>Лидов</th></tr>${rows}</table>`;
      document.getElementById("totals_table").innerHTML = html;
    });
}

function refreshAll() {
  STAGES.forEach(stage => loadStats(stage.label, stage.container));
  loadTotals();
}

// 🔄 Обновление каждые 30 секунд
refreshAll();
setInterval(refreshAll, 30000);
