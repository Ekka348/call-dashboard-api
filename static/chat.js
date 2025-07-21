let chatHistory = [];
let dynamicUsers = {};

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

async function loadUsers() {
  try {
    const res = await fetch("/users");
    const data = await res.json();
    for (let uid in data) {
      const name = data[uid].toLowerCase();
      dynamicUsers[name] = parseInt(uid);
    }
  } catch (e) {
    console.warn("Не удалось загрузить список сотрудников");
  }
}

// 🔍 Распознавание UID по тексту
function detectUserId(message) {
  const msg = message.toLowerCase();
  for (let fullName in dynamicUsers) {
    if (msg.includes(fullName)) {
      logChat(`🕵️‍♂️ Найден сотрудник: ${fullName}`);
      return dynamicUsers[fullName];
    }
  }
  return "";
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

  const uid = detectUserId(message);

  const res = await fetch(`/stats_data?label=${encodeURIComponent(label)}&range=${range}&uid=${uid}`);
  const data = await res.json();

  if (!data.values || !data.values.length || data.total === 0) {
    logChat(`📭 Нет лидов по стадии "${label}" за период "${range}"${uid ? ` для выбранного сотрудника` : ""}.`);
    document.getElementById("report").innerHTML = `<p>📭 Пусто: нет лидов по фильтру.</p>`;
    document.getElementById("chart").innerHTML = "";
    return;
  }

  logChat(`🤖 ${label}, ${range}${uid ? ` (фильтр по сотруднику)` : ""}: всего ${data.total} лидов`);
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

function renderTable(data) {
  let html = `<h3>📋 Стадия: "${data.stage}", период: "${data.range}"</h3>`;
  html += `<p>Всего лидов: ${data.total}</p><table><tr><th>Сотрудник</th><th>Лидов</th></tr>`;
  for (let i = 0; i < data.labels.length; i++) {
    html += `<tr><td>${data.labels[i]}</td><td>${data.values[i]}</td></tr>`;
  }
  html += `</table>`;
  document.getElementById("report").innerHTML = html;
}

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

function showSuggestions() {
  const box = document.getElementById("chatbox");
  if (document.getElementById("suggestions")) return;
  const sug = document.createElement("div");
  sug.id = "suggestions";
  sug.innerHTML = `
    <strong>💡 Примеры команд:</strong>
    <ul>
      <li>НДЗ неделя по Алия Ахматшина</li>
      <li>Сравни НДЗ и НДЗ 2 за неделю</li>
      <li>НДЗ по часам сегодня</li>
      <li>Активность НДЗ по дням</li>
      <li>НДЗ по неделям</li>
      <li>Скачай отчёт по НДЗ</li>
    </ul>`;
  box.appendChild(sug);
}

// 🚀 Запустить авто-загрузку пользователей
loadUsers();

