import streamlit as st
import pandas as pd
from datetime import datetime
import json
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
import io

# --- APP CONFIG ---
st.set_page_config(page_title="Surgicraft Cloud", layout="centered")

# --- INITIAL DATA (Aa bhav tamara Cloud Database mathi aavse) ---
if 'base_prices' not in st.session_state:
    st.session_state.base_prices = {
        "16x24": 160000, "16x36": 175000, "16x48": 190000,
        "20x24": 195000, "20x36": 210000, "20x48": 225000,
        "24x24": 240000, "24x36": 260000, "24x48": 280000
    }
if 'addons' not in st.session_state:
    st.session_state.addons = {
        "Vacuum Pump": 35000, "Double Door": 30000, "Alarm": 4000, "Gauge": 5000
    }
if 'cart' not in st.session_state:
    st.session_state.cart = []

# --- PDF GENERATION LOGIC ---
def generate_pdf(party, items):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 20); c.drawString(150, 790, "SURGICRAFT INDUSTRIES")
    c.setFont("Helvetica", 10); c.drawString(150, 775, "Manufacturers of Hospital Equipment | Since 1985")
    c.line(50, 750, 550, 750)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 720, f"Party: {party}")
    c.drawString(400, 720, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 680
    c.drawString(50, y, "Sr."); c.drawString(100, y, "Machine Size"); c.drawString(450, y, "Price")
    c.line(50, y-5, 550, y-5)
    
    y -= 30
    total_val = 0
    for i, item in enumerate(items, 1):
        c.drawString(50, y, str(i))
        c.drawString(100, y, item['size'])
        c.drawString(450, y, f"Rs. {item['total']}")
        total_val += item['total']
        y -= 25
    
    c.line(50, y, 550, y)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y-30, f"GRAND TOTAL: Rs. {total_val}/-")
    c.save()
    return buffer.getvalue()

# --- SIDEBAR (Settings & Login) ---
with st.sidebar:
    st.title("Surgicraft Menu")
    menu = st.radio("Go to:", ["Create Quotation", "Master Settings", "History"])
    st.divider()
    st.write("Logged in as: **Ankit**")

# --- MAIN INTERFACE ---
if menu == "Create Quotation":
    st.header("New Quotation")
    party = st.text_input("Enter Party Name")
    
    col1, col2 = st.columns(2)
    with col1:
        size = st.selectbox("Machine Size", list(st.session_state.base_prices.keys()))
    with col2:
        speed = st.radio("Speed", ["Low", "High", "Low+High"])
        
    st.subheader("Add-ons")
    selected_addons = []
    for addon, price in st.session_state.addons.items():
        if st.checkbox(f"{addon} (Rs. {price})"):
            selected_addons.append(addon)
            
    if st.button("➕ ADD TO LIST", use_container_width=True):
        total = st.session_state.base_prices[size]
        # Logic for speed/addons calc can go here
        st.session_state.cart.append({"size": size, "total": total, "addons": selected_addons})
        st.success("Added to list!")

    if st.session_state.cart:
        st.divider()
        st.write("### Current List")
        df = pd.DataFrame(st.session_state.cart)
        st.table(df[['size', 'total']])
        
        pdf_data = generate_pdf(party, st.session_state.cart)
        st.download_button("📄 DOWNLOAD FINAL PDF", pdf_data, file_name=f"{party}_quote.pdf", mime="application/pdf", use_container_width=True)
        
        if st.button("🗑️ CLEAR LIST", type="secondary"):
            st.session_state.cart = []
            st.rerun()

elif menu == "Master Settings":
    st.header("Price Settings")
    pwd = st.text_input("Enter Master Password", type="password")
    if pwd == "1234":
        st.write("Edit Prices below:")
        # Ahiya tame bhav badli shaksho (Demo mate khali batavyu che)
        for sz, pr in st.session_state.base_prices.items():
            st.number_input(f"Price for {sz}", value=pr)
        st.button("Update Prices Online")

elif menu == "History":
    st.header("Recent Quotations")
    st.info("Searching across all devices (Ankit, Vijay, Ketan)...")
    # Aa real database mathi aavse
    st.write("No online records yet. Connect to Cloud for real-time history.")
