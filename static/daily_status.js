async function loadDailyStatusSummary() {
  const list = document.getElementById("status_list");
  if (!list) return;
  if (!list) {
    console.warn("❗ Элемент #status_list не найден");
    return;
  }

  list.innerHTML = "";
  list.innerHTML = ""; // очищаем старый список

  for (const [name, id] of Object.entries(statusIDs)) {
    const item = document.createElement("li");
    item.innerText = `${name} — 🔄 загрузка...`;
    list.appendChild(item); // добавляем сразу, чтобы пользователь видел прогресс

    try {
      const res = await fetch(`/daily_status?status_id=${encodeURIComponent(id)}`);
      const data = await res.json();
      const item = document.createElement("li");
      item.innerText = `${name} — ${data.count} лидов`;
      list.appendChild(item);

      if (res.ok && typeof data.count === "number") {
        item.innerText = `${name} — ${data.count} лидов`;
        item.style.color = "#000";
      } else {
        item.innerText = `${name} — ❌ ошибка в данных`;
        item.style.color = "red";
      }
    } catch (error) {
      const item = document.createElement("li");
      item.innerText = `${name} — ❌ ошибка`;
      item.innerText = `${name} — ⚠️ ошибка запроса`;
      item.style.color = "red";
      list.appendChild(item);
      console.error(`Ошибка при загрузке ${name}:`, error);
    }
  }
}

// 🚀 Вызов при загрузке страницы
window.onload = () => {
  loadDailyStatusSummary();
};

