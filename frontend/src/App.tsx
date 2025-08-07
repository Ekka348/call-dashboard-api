import React, { useState, useEffect } from "react";
import { Bar } from "react-chartjs-2";
import { getDeals } from "./auth";
import Login from "./Login";

const STAGE_LABELS = {
  "UC_A2DF81": "На согласовании",
  "IN_PROCESS": "Перезвонить",
  "CONVERTED": "Приглашен к рекрутеру",
};

const Dashboard = () => {
  const [deals, setDeals] = useState([]);
  const [token, setToken] = useState("");

  useEffect(() => {
    if (token) {
      getDeals(token).then((data) => setDeals(data.deals));
    }
  }, [token]);

  const stagesCount = {
    "На согласовании": deals.filter((d) => d[1] === "UC_A2DF81").length,
    "Перезвонить": deals.filter((d) => d[1] === "IN_PROCESS").length,
    "Приглашен к рекрутеру": deals.filter((d) => d[1] === "CONVERTED").length,
  };

  if (!token) return <Login onLogin={setToken} />;

  return (
    <div>
      <h2>Воронка продаж</h2>
      <Bar
        data={{
          labels: Object.keys(stagesCount),
          datasets: [{
            label: "Количество сделок",
            data: Object.values(stagesCount),
            backgroundColor: ["#FF6384", "#36A2EB", "#FFCE56"],
          }],
        }}
      />
    </div>
  );
};

export default Dashboard;
