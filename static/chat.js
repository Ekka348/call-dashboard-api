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

// 🚀 Загружаем сотрудников из /users
async function loadUsers() {
  try {
    const res = await fetch("/users");
    const data = await res.json();
    const select = document.getElementById("userselect");
    const datalist = document.getElementById("userlist");

    for (let uid in data) {
      const name = data[uid];
      const norm = name.toLowerCase();
      const reversed = norm.split(" ").reverse().join(" ");
      dynamicUsers[norm] = parseInt(uid);
      dynamicUsers[reversed] = parseInt(uid);

      const opt = document.createElement("option");
      opt.value = uid;
      opt.textContent = name;
      select.appendChild(opt);

      const dl = document.createElement("option");
      dl.value = name;
      datalist.appendChild(dl);
    }
  } catch {
    logChat("⚠️ Не удалось загрузить список сотрудников.");
  }
}

// 🔍 Распознаем UID по тексту
function detectUserId(message) {
  const msg = message.toLowerCase();
  for (let name in dynamicUsers) {
    if (msg.includes(name)) {
      logChat(`🕵️‍♀️ Найден сотрудник: ${name}`);
      return dynamicUsers[name];
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

  const uidText = detectUserId(message);
  const selectedUid = document.getElementById("userselect").value;
  const uid = selectedUid || uidText;

  const res = await fetch(`/stats_data?label=${label}&range=${range}&uid=${uid}`);
  const data = await res.json();

  if (!data.values || !data.values.length || data.total === 0) {
    logChat(`📭 Нет лидов по "${label}" (${range})${uid ? " для выбранного сотрудника" : ""}.`);
    document.getElementById("report").innerHTML = `<p>📭 Пусто: нет лидов по фильтру.</p>`;
    document.getElementById("chart").innerHTML = "";
    return;
  }

  logChat(`🤖 ${label}, ${range}${uid ? " (фильтр по сотруднику)" : ""}: всего ${data.total} лидов`);
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

// 🚀 При старте — загружаем сотрудников
loadUsers();


