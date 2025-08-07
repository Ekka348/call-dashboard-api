import requests
import streamlit as st
import pandas as pd
import warnings

# Игнорируем предупреждения Streamlit
warnings.filterwarnings("ignore", category=UserWarning, message=".*ScriptRunContext.*")

# Вебхук Bitrix24
BITRIX_WEBHOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"

@st.cache_data(ttl=300)  # Кэшируем на 5 минут
def get_deals():
    """Получаем сделки из Bitrix24"""
    method = "crm.deal.list"
    params = {
        "select": ["ID", "TITLE", "STAGE_ID"],
        "filter": {"CATEGORY_ID": 0}
    }
    response = requests.post(f"{BITRIX_WEBHOOK}{method}", json=params).json()
    return response.get("result", [])

# Заголовок дашборда
st.title("Bitrix24 Deal Dashboard")

# Получаем данные
deals = get_deals()

if not deals:
    st.error("Не удалось загрузить сделки!")
else:
    # Таблица сделок
    st.write("### Все сделки:")
    df = pd.DataFrame(deals)
    st.dataframe(df)

    # Статистика по стадиям
    st.write("### Количество сделок по стадиям:")
    stage_counts = df["STAGE_ID"].value_counts().reset_index()
    stage_counts.columns = ["STAGE_ID", "COUNT"]
    st.bar_chart(stage_counts.set_index("STAGE_ID"))
