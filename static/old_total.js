async function loadOldTotal() {
  const res = await fetch("/old_total");
  const data = await res.json();
  const container = document.getElementById("report_old_total");

  container.innerHTML = `
    <h4>📦 Всего лидов OLD за сегодня</h4>
    <p style="font-size: 22px; margin-top: 10px;">${data.total}</p>
    <p style="font-size: 13px; color: gray;">Обновлено: ${new Date().toLocaleTimeString()}</p>
  `;
}

async function fetchExtendedStatus() {
  try {
    const response = await fetch('/api/lead_extended_summary');
    const data = await response.json();

    document.getElementById("count-old").textContent = data.OLD;
    document.getElementById("count-new-today").textContent = data.NEW_TODAY;
    document.getElementById("count-vv-today").textContent = data.VV_TODAY;
  } catch (err) {
    console.error("Ошибка загрузки расширенной сводки:", err);
  }
}

document.addEventListener("DOMContentLoaded", fetchExtendedStatus);

loadOldTotal();
setInterval(loadOldTotal, 600000);
