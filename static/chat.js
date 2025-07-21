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
  if (!input) {
    showSuggestions();
    return;
  }
  document.getElementById("suggestions")?.remove();
  logChat("👤 " + input);
  processChat(input);
  document.getElementById("chatinput").value = "";
}

async function processChat(message) {
  let label = "НДЗ", range = "week", uid = "";
  const stages = ["НДЗ", "НДЗ 2", "Перезвонить", "Приглашен к рекрутеру"];
  const users = { "алия": 1, "наталья": 2, "сергей": 3 };

  for (let s of stages) {
    if (message.toLowerCase().includes(s.toLowerCase())) label = s;
  }

  if (message.includes("сегодня")) range = "today";
  if (message.includes("неделя")) range = "week";
  if (message.includes("месяц")) range = "month";

  for (let name in users) {
    if (message.toLowerCase().includes(name)) uid = users[name];
  }

  // ⏱ По часам
  if (message.includes("по часам")) {
    const res = await fetch(`/hourly?label=${label}&range=${range}`);
    const data = await res.json();
    renderLineChart(data);
    logChat(`🕒 Активность по часам: ${label}, ${range}`);
    return;
  }

  // 📈 По дням
  if (message.includes("по дням") || message.includes("тренд")) {
    const res = await fetch(`/trend?label=${label}&range=${range}`);
    const data = await res.json();
    renderLineChart(data);
    logChat(`📈 Активность по дням: ${label}, ${range}`);
    return;
  }

  // 🔁 Сравнение двух стадий
  if (message.includes("сравни")) {
    const found = stages.filter(s => message.includes(s));
    if (found.length === 2) {
      const res = await fetch(`/compare_stages?stage1=${found[0]}&stage2=${found[1]}&range=${range}`);
      const data = await res.json();
      const diff = data.count1 - data.count2;
      const emoji = diff > 0 ? "📈" : diff < 0 ? "📉" : "➖";
      logChat(`🔁 Сравнение: ${data.stage1} (${data.count1}) vs ${data.stage2} (${data.count2}) → разница: ${diff} ${emoji}`);
      return;
    }
  }

  // 📥 Скачивание отчёта
  if (message.includes("скачай") || message.includes("экспорт")) {
    const link = `/export_csv?label=${label}&range=${range}`;
    logChat(`📁 Скачать отчёт: <a href="${link}" target="_blank">${label} ${range}</a>`);
    return;
  }

  // 📅 Понедельная аналитика
  if (message.includes("неделям") || message.includes("по неделям")) {
    const res = await fetch(`/weekly_breakdown?label=${label}`);
    const data = await res.json();
    let html = `<table border="1" cellpadding="6"><tr><th>Неделя</th><th>Лидов</th></tr>`;
    for (let w of data) {
      html += `<tr><td>${w.week}</td><td>${w.count}</td></tr>`;
    }
    html += `</table>`;
    logChat(`📅 Понедельная аналитика по "${label}":`);
    document.getElementById("chart").innerHTML = html;
    return;
  }

  // 📊 Стандартный отчёт
  const res = await fetch(`/stats_data?label=${label}&range=${range}&uid=${uid}`);
  const data = await res.json();
  logChat(`🤖 ${label}, ${range}: всего ${data.total} лидов`);
  renderTable(data);
  renderChart(data);
  const max = Math.max(...data.values);
  const idx = data.values.indexOf(max);
  const top = data.labels[idx];
  logChat(`🏆 Самый активный: ${top} (${max} лидов)`);
}

function presetChat(text) {
  document.getElementById("chatinput").value = text;
  handleChat({ key: "Enter" });
}

function showSuggestions() {
  const box = document.getElementById("chatbox");
  const sug = document.createElement("div");
  sug.id = "suggestions";
  sug.innerHTML = `
    <strong>💡 Примеры команд:</strong>
    <ul>
      <li>НДЗ неделя по Алие</li>
      <li>Сравни НДЗ и НДЗ 2 за неделю</li>
      <li>Активность НДЗ по дням</li>
      <li>НДЗ по часам сегодня</li>
      <li>НДЗ по неделям</li>
      <li>Скачай отчёт по НДЗ</li>
    </ul>`;
  box.appendChild(sug);
}

// 📊 Стандартный бар-график
function renderChart(data) {
  const trace = {
    x: data.labels,
    y: data.values,
    type: "bar",
    marker: { color: "#007bff" }
  };
  const layout = {
    title: `📊 Активность — "${data.stage}" (${data.range})`,
    margin: { t: 40, l: 60, r: 30, b: 100 }
  };
  Plotly.newPlot("chart", [trace], layout);
}

// 📈 Линейный график по дням/часам
function renderLineChart(data) {
  const trace = {
    x: data.labels,
    y: data.values,
    type: "scatter",
    mode: "lines+markers",
    marker: { color: "#28a745" }
  };
  const layout = {
    title: `📈 Тренд — "${data.stage}" (${data.range})`,
    margin: { t: 40, l: 60, r: 30, b: 100 }
  };
  Plotly.newPlot("chart", [trace], layout);
}

// 📋 Отображение таблицы
function renderTable(data) {
  let html = `<h3>📋 Стадия: "${data.stage}", период: "${data.range}"</h3>`;
  html += `<p>Всего лидов: ${data.total}</p><table><tr><th>Сотрудник</th><th>Лидов</th></tr>`;
  for (let i = 0; i < data.labels.length; i++) {
    html += `<tr><td>${data.labels[i]}</td><td>${data.values[i]}</td></tr>`;
  }
  html += `</table>`;
  document.getElementById("report").innerHTML = html;
}
