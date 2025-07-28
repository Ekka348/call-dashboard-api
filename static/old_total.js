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

loadOldTotal();
setInterval(loadOldTotal, 600000);
