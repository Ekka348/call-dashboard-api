import requests
from fastapi import FastAPI
import streamlit as st
import pandas as pd

app = FastAPI()

# Вебхук Bitrix24
BITRIX_WEBHOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"

def get_deals():
    """Получаем сделки из Bitrix24"""
    method = "crm.deal.list"
    params = {
        "select": ["ID", "TITLE", "STAGE_ID"],
        "filter": {"CATEGORY_ID": 0}  # Можно убрать или изменить фильтр
    }
    response = requests.post(f"{BITRIX_WEBHOOK}{method}", json=params).json()
    return response.get("result", [])

# Streamlit-дашборд
def show_dashboard():
    st.title("Bitrix24 Deal Dashboard")
    deals = get_deals()
    
    if not deals:
        st.error("Не удалось загрузить сделки!")
        return
    
    # Преобразуем в таблицу
    df = pd.DataFrame(deals)
    st.write("### Все сделки:")
    st.dataframe(df)
    
    # Группируем по стадиям
    stage_counts = df["STAGE_ID"].value_counts().reset_index()
    stage_counts.columns = ["STAGE_ID", "COUNT"]
    st.write("### Количество сделок по стадиям:")
    st.bar_chart(stage_counts.set_index("STAGE_ID"))

# Запуск Streamlit
if __name__ == "__main__":
    show_dashboard()
