const statusIDs = {
  "NEW": "NEW",
  "База ВВ": "11",
  "OLD": "UC_VTOOIM",
  "НДЗ": "5",
  "НДЗ 2": "9",
  "Перезвонить": "IN_PROCESS",
  "На согласовании": "UC_A2DF81"
};

async function loadDailyStatusSummary() {
  const list = document.getElementById("status_list");
  if (!list) {
    console.warn("❗ Элемент #status_list не найден");
    return;
  }

  list.innerHTML = ""; // очищаем старый список

  for (const [name, id] of Object.entries(statusIDs)) {
    const item = document.createElement("li");
    item.innerText = `${name} — 🔄 загрузка...`;
    list.appendChild(item); // добавляем сразу, чтобы пользователь видел прогресс

    try {
      const res = await fetch(`/daily_status?status_id=${encodeURIComponent(id)}`);
      const data = await res.json();

      if (res.ok && typeof data.count === "number") {
        item.innerText = `${name} — ${data.count} лидов`;
        item.style.color = "#000";
      } else {
        item.innerText = `${name} — ❌ ошибка в данных`;
        item.style.color = "red";
      }
    } catch (error) {
      item.innerText = `${name} — ⚠️ ошибка запроса`;
      item.style.color = "red";
      console.error(`Ошибка при загрузке ${name}:`, error);
    }
  }
}

// 🚀 Вызов при загрузке страницы
window.onload = () => {
  loadDailyStatusSummary();
};



