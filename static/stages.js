<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8" />
  <title>CRM Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <style>
    body {
      font-family: Arial, sans-serif;
      margin: 20px;
      background: #f4f4f4;
      color: #333;
    }

    select, input[type="date"] {
      font-size: 16px;
      padding: 6px 10px;
      margin: 5px;
    }

    #statusbar {
      margin-top: 10px;
      font-size: 14px;
    }

    #spinner, #lastupdate {
      margin: 5px 0;
    }

    #spinner { color: gray; }
    #lastupdate { color: #28a745; }

    .stage-block {
      flex: 1;
      min-width: 300px;
      border: 2px solid #ccc;
      border-radius: 8px;
      padding: 10px;
      background: #fff;
    }

    .stage-block.blue     { border-color: #007bff; }
    .stage-block.purple   { border-color: #6f42c1; }
    .stage-block.orange   { border-color: #fd7e14; }
    .stage-block.green    { border-color: #28a745; }

    .stage-block h4 { margin-top: 0; }

    table {
      border-collapse: collapse;
      width: 100%;
      background: #fff;
    }

    th, td {
      border: 1px solid #ccc;
      padding: 6px;
      text-align: left;
    }

    #status_summary {
      margin-top: 30px;
      background: #fff;
      border: 2px solid #444;
      padding: 10px;
      border-radius: 8px;
    }

    #status_list {
      list-style: none;
      padding-left: 0;
      font-size: 15px;
    }

    #status_list li {
      margin: 4px 0;
    }

    @media screen and (max-width: 768px) {
      .stage-block {
        flex: 1 1 100%;
      }

      body {
        margin: 10px;
      }

      h2, h3 {
        font-size: 20px;
      }

      select, input[type="date"] {
        font-size: 15px;
        width: 100%;
        margin: 5px 0;
      }

      #statusbar {
        font-size: 13px;
      }

      #status_summary {
        padding: 10px;
        font-size: 14px;
      }

      #status_list li {
        font-size: 14px;
      }
    }
  </style>
</head>
<body>
  <h2>📊 CRM Dashboard</h2>

  <label>Период:</label>
  <select id="range">
    <option value="today">Сегодня</option>
    <option value="week">Текущая неделя</option>
    <option value="month">Месяц</option>
    <option value="custom">Выбрать вручную</option>
  </select>

  <label>С:</label>
  <input type="date" id="startdate">

  <label>По:</label>
  <input type="date" id="enddate">

  <div id="statusbar">
    <div id="spinner">🌀 Загрузка не начата</div>
    <div id="lastupdate">✅ Последнее обновление: нет данных</div>
  </div>

  <div style="display:flex; flex-wrap:wrap; gap:20px; margin-top:20px;">
    <div class="stage-block blue" id="report_ndz"></div>
    <div class="stage-block purple" id="report_ndz2"></div>
    <div class="stage-block orange" id="report_call"></div>
    <div class="stage-block green" id="report_recruiter"></div>
  </div>

  <div id="status_summary">
    <h3>📦 Лиды в стадиях за сегодня</h3>
    <ul id="status_list"></ul>
  </div>

  <script src="/static/stages.js"></script>
  <script src="/static/daily_status.js"></script>
</body>
</html>
