import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import io

# --- Google Sheets Connection ---
def connect_to_sheet():
    info = json.loads(st.secrets["google_key"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Surgicraft_Database").sheet1 
    return sheet

# --- PDF Banavva nu Function ---
def create_pdf(df, party_name):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(200, 750, f"Surgicraft Party History")
    
    c.setFont("Helvetica", 12)
    c.drawString(50, 720, f"Party Name: {party_name}")
    c.line(50, 715, 550, 715)
    
    y = 680
    c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Date")
    c.drawString(150, y, "Machine Name")
    c.drawString(350, y, "Details")
    
    c.setFont("Helvetica", 10)
    for index, row in df.iterrows():
        y -= 20
        c.drawString(50, y, str(row['Date']))
        c.drawString(150, y, str(row['Machine Name']))
        c.drawString(350, y, str(row['Details']))
        if y < 50: # Navi page mate
            c.showPage()
            y = 750
            
    c.save()
    buf.seek(0)
    return buf

# --- UI ---
st.title("🏥 Surgicraft Management")

try:
    sheet = connect_to_sheet()
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    menu = ["Add New Entry", "Party History"]
    choice = st.sidebar.selectbox("Select Action", menu)

    if choice == "Add New Entry":
        with st.form("entry_form"):
            st.subheader("Add Machine Sale Detail")
            date = st.text_input("Date (DD-MM-YYYY)")
            party = st.text_input("Party Name")
            machine = st.text_input("Machine Name")
            detail = st.text_area("Full Details / Serial No.")
            submit = st.form_submit_button("Save to Sheet")
            
            if submit:
                sheet.append_row([date, party, machine, detail])
                st.success("Data Saved! ✅")

    elif choice == "Party History":
        st.subheader("Search Party History")
        search_name = st.text_input("Enter Party Name to Search")
        
        if search_name:
            # Filter data based on name
            result_df = df[df['Party Name'].str.contains(search_name, case=False, na=False)]
            
            if not result_df.empty:
                st.write(f"Found {len(result_df)} records for '{search_name}'")
                st.table(result_df)
                
                # PDF Download Button
                pdf_file = create_pdf(result_df, search_name)
                st.download_button(
                    label="📥 Download History as PDF",
                    data=pdf_file,
                    file_name=f"{search_name}_History.pdf",
                    mime="application/pdf"
                )
            else:
                st.warning("Aa naam ni koi party mali nathi.")

except Exception as e:
    st.error(f"Error: {e}")
