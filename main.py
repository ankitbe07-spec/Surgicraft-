import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json

# --- Google Sheets Connection ---
def connect_to_sheet():
    # Streamlit Secrets mathi key levi
    info = json.loads(st.secrets["google_key"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    client = gspread.authorize(creds)
    
    # Ahiya tamari Sheet nu naam dhyan thi lakhjo
    sheet = client.open("Surgicraft_Database").sheet1 
    return sheet

# --- Main App ---
st.title("🏥 Surgicraft Price List")

try:
    sheet = connect_to_sheet()
    st.success("Connected to Google Sheets! ✅")
    
    # Data read karva
    data = sheet.get_all_records()
    
    if data:
        st.write("Current Price List:")
        st.table(data)
    else:
        st.info("Sheet khali che. Excel mathi data copy-paste kari do!")

    # Nvo data nakhva mate form
    with st.form("add_item"):
        item = st.text_input("Item Name")
        price = st.number_input("Price", min_value=0)
        submit = st.form_submit_button("Add to Sheet")
        
        if submit:
            sheet.append_row([item, price])
            st.success(f"{item} add thai gayo! Google Sheet check karo.")
            st.rerun()

except Exception as e:
    st.error(f"Connection Error: {e}")
