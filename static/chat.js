let chatHistory = [];

function logChat(message) {
  chatHistory.push(message);
  const log = document.getElementById("chatlog");
  log.innerHTML += `<div>${message}</div>`;
  log.scrollTop = log.scrollHeight;
}

function handleChat(e) {
  if (e.key !== "Enter") return;
  const input = document.getElementById("chatinput").value.trim();
  if (!input) return;
  logChat("👤 " + input);
  processChat(input);
  document.getElementById("chatinput").value = "";
}

async function processChat(message) {
  let label = "НДЗ", range = "week";
  const stages = ["НДЗ", "НДЗ 2", "Перезвонить", "Приглашен к рекрутеру"];

  for (let s of stages) {
    if (message.toLowerCase().includes(s.toLowerCase())) label = s;
  }
  if (message.includes("сегодня")) range = "today";
  if (message.includes("неделя")) range = "week";
  if (message.includes("месяц")) range = "month";

  // 🔍 Тренд по дням
  if (message.includes("по дням") || message.includes("тренд")) {
    const res = await fetch(`/trend?label=${encodeURIComponent(label)}&range=${range}`);
    const data = await res.json();
    logChat(`📈 Активность по дням: стадия "${data.stage}", период "${data.range}"`);
    renderLineChart(data);
    return;
  }

  // 🏁 Сравнение двух стадий
  if (message.includes("сравни")) {
    const parts = stages.filter(s => message.includes(s));
    if (parts.length === 2) {
      const res = await fetch(`/compare_stages?stage1=${encodeURIComponent(parts[0])}&stage2=${encodeURIComponent(parts[1])}&range=${range}`);
      const data = await res.json();
      const diff = data.count1 - data.count2;
      const emoji = diff > 0 ? "📈" : (diff < 0 ? "📉" : "➖");
      logChat(`🔁 Сравнение: ${data.stage1} (${data.count1}) vs ${data.stage2} (${data.count2}) → разница: ${diff} ${emoji}`);
      return;
    }
  }

  // 📥 Экспорт CSV
  if (message.includes("скачай") || message.includes("экспорт")) {
    const link = `/export_csv?label=${encodeURIComponent(label)}&range=${range}`;
    logChat(`📁 Готово! Скачать отчёт: <a href="${link}" target="_blank">CSV-файл</a>`);
    return;
  }

  // 📊 Стандартный запрос — график + таблица
  const res = await fetch(`/stats_data?label=${encodeURIComponent(label)}&range=${range}`);
  const data = await res.json();
  logChat(`🤖 Стадия "${data.stage}", период "${data.range}": всего ${data.total} лидов`);
  renderTable(data);
  renderChart(data);

  // 🏆 Самый активный
  const max = Math.max(...data.values);
  const idx = data.values.indexOf(max);
  const top = data.labels[idx];
  logChat(`🏆 Самый активный сотрудник: ${top} (${max} лидов)`);
}

function presetChat(text) {
  document.getElementById("chatinput").value = text;
  handleChat({ key: "Enter" });
}

// 📊 Отдельный тренд-график
function renderLineChart(data) {
  const trace = {
    x: data.labels,
    y: data.values,
    type: "scatter",
    mode: "lines+markers",
    marker: { color: "#28a745" }
  };
  const layout = {
    title: `📈 Тренд по дням — "${data.stage}" (${data.range})`,
    margin: { t: 40, l: 60, r: 30, b: 100 }
  };
  Plotly.newPlot("chart", [trace], layout);
}
