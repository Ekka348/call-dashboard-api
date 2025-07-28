async function fetchTotals() {
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
}
fetchTotals();
