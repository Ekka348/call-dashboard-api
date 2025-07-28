async function fetchTotals() {
  const spinner = document.getElementById("spinner");
  spinner.textContent = "⏳ Загружаю данные по стадиям...";

  const res = await fetch("/totals");
  const data = await res.json();
  const list = document.getElementById("status_list");
  list.innerHTML = "";

  data.data.forEach(entry => {
    const li = document.createElement("li");
    li.textContent = `${entry.label}: ${entry.count}`;
    list.appendChild(li);
  });

  document.getElementById("lastupdate").textContent =
    `✅ Последнее обновление: ${new Date().toLocaleTimeString()}`;
  spinner.textContent = "🎯 Готово!";
}

fetchTotals();                 // первичная загрузка
setInterval(fetchTotals, 60); // автообновление каждые 10 минут

