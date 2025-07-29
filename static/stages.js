function getDateParams() {
  const now = new Date().toISOString().slice(0, 19).replace("T", " ");
  return "start=2020-01-01 00:00:00&end=" + encodeURIComponent(now);
}

async function loadSummaryOLD() {
  try {
    const res = await fetch("/summary_old?" + getDateParams());
    const data = await res.json();
    document.getElementById("old_count").innerText = data.count ?? "Нет данных";
  } catch {
    document.getElementById("old_count").innerText = "❌ Ошибка";
  }
}

async function loadStageSummary() {
  try {
    const res = await fetch("/stage_summary");
    const data = await res.json();
    const listHTML = Object.entries(data).map(([name, count]) =>
      `<li><strong>${name}</strong>: ${count}</li>`
    ).join("");
    document.getElementById("stage_list").innerHTML = listHTML;
  } catch {
    document.getElementById("stage_list").innerText = "❌ Ошибка загрузки";
  }
}

window.onload = () => {
  loadSummaryOLD();
  loadStageSummary();
};
