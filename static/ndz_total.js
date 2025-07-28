async function loadNdzTotal() {
  const res = await fetch("/ndz_total");
  const data = await res.json();
  const container = document.getElementById("report_ndz_total");

  container.innerHTML = `
    <h4>📦 Всего лидов НДЗ за сегодня</h4>
    <p style="font-size: 22px; margin-top: 10px;">${data.total}</p>
    <p style="font-size: 13px; color: gray;">Обновлено: ${new Date().toLocaleTimeString()}</p>
  `;
}

// первичная загрузка
loadNdzTotal();
// автообновление каждые 10 мин
setInterval(loadNdzTotal, 600000);

