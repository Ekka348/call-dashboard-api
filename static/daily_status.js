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
  if (!list) return;

  list.innerHTML = "";

  for (const [name, id] of Object.entries(statusIDs)) {
    try {
      const res = await fetch(`/daily_status?status_id=${encodeURIComponent(id)}`);
      const data = await res.json();

      const item = document.createElement("li");
      item.innerText = `${name} — ${data.count} лидов`;
      list.appendChild(item);
    } catch (error) {
      const item = document.createElement("li");
      item.innerText = `${name} — ❌ ошибка`;
      item.style.color = "red";
      list.appendChild(item);
    }
  }
}
