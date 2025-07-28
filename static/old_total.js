document.addEventListener("DOMContentLoaded", () => {
  // Вставляем HTML внутрь контейнера
  const container = document.getElementById("report_old_total");

  container.innerHTML = `
    <div class="status-container old-extended">
      <h3>🟡 OLD лиды</h3>
      <p>Всего: <span id="count-old">—</span></p>

      <div class="related-status">
        <div>
          <strong>🟢 NEW (сегодня):</strong>
          <span id="count-new-today">—</span>
        </div>
        <div>
          <strong>🔵 База ВВ (сегодня):</strong>
          <span id="count-vv-today">—</span>
        </div>
      </div>
    </div>
  `;

  // Загружаем данные с Flask-сервера
  fetch('/api/lead_extended_summary')
    .then(response => response.json())
    .then(data => {
      document.getElementById("count-old").textContent = data.OLD;
      document.getElementById("count-new-today").textContent = data.NEW_TODAY;
      document.getElementById("count-vv-today").textContent = data.VV_TODAY;
    })
    .catch(error => {
      console.error("Ошибка загрузки расширенной статистики:", error);
      container.innerHTML += `<p style="color:red;">❌ Не удалось загрузить данные</p>`;
    });
});
