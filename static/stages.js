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
@@ -20,7 +26,11 @@
  if (range === "custom") {
    const start = document.getElementById("startdate").value;
    const end = document.getElementById("enddate").value;
    if (start && end) params += `&start=${start}&end=${end}`;
    if (start && end) {
      params += `&start=${start}&end=${end}`;
    } else {
      return null; // период не выбран
    }
  }
  return params;
}
@@ -29,6 +39,10 @@
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
@@ -52,12 +66,18 @@
}

async function updateLoop() {
  const params = getDateParams();
  if (!params) {
    showWarning();
    return setTimeout(updateLoop, 1000); // ждём и пробуем снова
  }

  await loadStatsFor("НДЗ", "report_ndz");
  await loadStatsFor("НДЗ 2", "report_ndz2");
  await loadStatsFor("Перезвонить", "report_call");
  await loadStatsFor("Приглашен к рекрутеру", "report_recruiter");
  hideLoading(true);
  requestAnimationFrame(() => setTimeout(updateLoop, 100));
  requestAnimationFrame(() => setTimeout(updateLoop, 100)); // непрерывный цикл
}

function attachReactiveListeners() {
@@ -70,6 +90,3 @@
  attachReactiveListeners();
  updateLoop();

  window.onload = () => {
  attachReactiveListeners();
  updateLoop();
  loadDailyStatusSummary(); // 👈 добавляем вызов загрузки сводки по стадиям
};
};
