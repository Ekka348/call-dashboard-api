<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8">
  <title>Кандидаты по стадиям</title>
  <link rel="stylesheet" href="/static/styles.css">
  <script>
    const STAGES = ["На согласовании", "Перезвонить", "Приглашен к рекрутеру"];

    async function updateStage(stage) {
      try {
        const response = await fetch(`/update_stage/${stage}`);
        if (response.ok) {
          location.reload();
        } else {
          alert("Ошибка при обновлении стадии: " + stage);
        }
      } catch (error) {
        console.error("Ошибка запроса:", error);
      }
    }
  </script>
</head>
<body>
  <h1>📋 Панель кандидатов</h1>
  <div class="stage-columns" id="content">
    <div class="stage-table" data-stage="На согласовании">
      <h2>Стадия: На согласовании</h2>
      <button class="refresh-btn" onclick="updateStage('На согласовании')">🔄 Обновить</button>
      <div id="table-На согласовании"></div>
    </div>
    <div class="stage-table" data-stage="Перезвонить">
      <h2>Стадия: Перезвонить</h2>
      <button class="refresh-btn" onclick="updateStage('Перезвонить')">🔄 Обновить</button>
      <div id="table-Перезвонить"></div>
    </div>
    <div class="stage-table" data-stage="Приглашен к рекрутеру">
      <h2>Стадия: Приглашен к рекрутеру</h2>
      <button class="refresh-btn" onclick="updateStage('Приглашен к рекрутеру')">🔄 Обновить</button>
      <div id="table-Приглашен к рекрутеру"></div>
    </div>
  </div>
</body>
</html>
