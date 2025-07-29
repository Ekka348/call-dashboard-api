const STAGES = {
  "НДЗ": "5",
  "НДЗ 2": "9",
  "Перезвонить": "IN_PROCESS",
  "Приглашен к рекрутеру": "CONVERTED",
  "NEW": "NEW",
  "OLD": "11",
  "База ВВ": "UC_VTOOIM"
};

const WORK_STAGES = ["НДЗ", "НДЗ 2", "Перезвонить", "Приглашен к рекрутеру"];
const INFO_STAGES = ["NEW", "OLD", "База ВВ"];

async function updateDashboard() {
  try {
    const res = await fetch("/api/leads/by-stage?_=" + Date.now()); // ⚠ анти-кэш
    const data = await res.json();

    // 🔹 Инфо-стадии
    const statsContainer = document.getElementById("stats");
    statsContainer.innerHTML = "";
    INFO_STAGES.forEach(stage => {
      const info = data.data[stage];
      const value = info?.count ?? 0;
      const statLine = document.createElement("p");
      statLine.innerHTML = `<strong>${stage}:</strong> ${value}`;
      statsContainer.appendChild(statLine);
    });

    // 🔹 Рабочие стадии
    const content = document.getElementById("content");
    content.innerHTML = "";
    WORK_STAGES.forEach(stage => {
      const info = data.data[stage];
      const block = document.createElement("div");
      block.className = "stage-table";

      const heading = document.createElement("h2");
      heading.textContent = `Стадия: ${stage}`;
      block.appendChild(heading);

      if (!info?.details || info.details.length === 0) {
        const empty = document.createElement("p");
        empty.className = "empty-message";
        empty.textContent = "Нет лидов.";
        block.appendChild(empty);
      } else {
        const table = document.createElement("table");
        const header = document.createElement("thead");
        header.innerHTML = `<tr><th>Оператор</th><th>Количество</th></tr>`;
        table.appendChild(header);

        const body = document.createElement("tbody");
        info.details.forEach(row => {
          const tr = document.createElement("tr");
          tr.innerHTML = `<td>${row.operator}</td><td>${row.count}</td>`;
          body.appendChild(tr);
        });

        table.appendChild(body);
        block.appendChild(table);
      }

      content.appendChild(block);
    });

    // 🔸 Лог времени
    const now = new Date().toLocaleTimeString();
    document.getElementById("last-update").textContent = now;
  } catch (err) {
    document.getElementById("last-update").textContent = "⚠ Ошибка загрузки";
    console.error("Ошибка автообновления:", err);
  }
}

// ⏱ автообновление каждые 30 сек
window.onload = () => {
  updateDashboard();
  setInterval(updateDashboard, 30000);
};
