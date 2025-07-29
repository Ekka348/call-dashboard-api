async function loadTotalLeads() {
  const spinner = document.getElementById("total_spinner");
  const resultBox = document.getElementById("total_result");

  spinner.textContent = "🔄 Загрузка...";
  resultBox.textContent = "—";

  try {
    const res = await fetch("/daily?label=total&range=today");
    const data = await res.json();
    const total = data?.total ?? 0;

    spinner.textContent = "✅ Обновлено";
    resultBox.textContent = `Всего лидов: ${total}`;
  } catch (err) {
    spinner.textContent = "❌ Ошибка загрузки";
    resultBox.textContent = "—";
    console.error("Ошибка при загрузке total leads:", err);
  }
}

// Можно запускать при загрузке или на изменение диапазона
window.addEventListener("DOMContentLoaded", loadTotalLeads);
