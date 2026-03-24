import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
import pandas as pd
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# --- DEFAULT SETTINGS ---
DEF_PRICES = {
    "16x24": 160000, "16x36": 175000, "16x39": 180000, "16x48": 190000,
    "20x24": 195000, "20x36": 210000, "20x39": 215000, "20x48": 225000,
    "24x24": 240000, "24x36": 260000, "24x39": 270000, "24x48": 280000
}
DEF_ADDONS = {
    "VacuumPump": 35000, "Only Provision V.Pump Bush": 18000,
    "DoubleDoor": 30000, "Alarm": 4000, "Gauge": 5000,
    "PressureSwitch": 6000, "LowHighExtra": 12000
}
TC_TEXT = "Terms: GST Extra, Transport Extra, Subject to Ahmedabad Jurisdiction."

# --- SESSION STATE INITIALIZATION ---
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'q_no' not in st.session_state:
    st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"

# --- GOOGLE SHEETS CONNECTION ---
def connect_to_sheet():
    info = json.loads(st.secrets["google_key"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    client = gspread.authorize(creds)
    return client.open("Surgicraft_Database").sheet1

# --- PDF GENERATOR ---
def create_pdf(party, q_no, items, date_str):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    c.setFont("Helvetica-Bold", 20); c.drawString(150, 790, "SURGICRAFT INDUSTRIES")
    c.setFont("Helvetica-Bold", 10); c.drawString(150, 775, "Manufacturers of Hospital Equipment | Since 1985")
    c.setFont("Helvetica", 9)
    c.drawString(150, 760, "Partners: Vijay Mistry, Ketan Mistry")
    c.drawString(150, 745, "Ram krishna compound, Opp. Muncipal labour quator, Behind Bharat petrol pump,")
    c.drawString(150, 730, "Near naroda fruit market, Naroda Road. Ahmedabad - 380025")
    c.setFont("Helvetica-Bold", 10); c.drawString(150, 715, "GSTIN: [Tamaro GST Number]")
    c.line(50, 700, 550, 700)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 670, f"Quotation No: {q_no}")
    c.drawString(400, 670, f"Date: {date_str}")
    c.drawString(50, 650, f"Party Name: {party}")
    
    y = 610; c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Sr."); c.drawString(80, y, "Machine Size")
    c.drawString(180, y, "Speed & Specifications"); c.drawString(450, y, "Net Price (Rs)")
    c.line(50, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 10); grand_total = 0
    for i, item in enumerate(items, 1):
        c.drawString(50, y, str(i)); c.drawString(80, y, item['size'])
        opts_str = f"Speed: {item['speed']} | " + ", ".join(item['options'])
        if len(opts_str) > 55: opts_str = opts_str[:52] + "..."
        c.drawString(180, y, opts_str); c.drawString(450, y, str(item['total']))
        grand_total += item['total']; y -= 20
        if y < 150: c.showPage(); y = 750
            
    c.line(50, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(50, y-25, f"GRAND TOTAL VALUE: Rs. {grand_total}/-")
    c.setFont("Helvetica-Oblique", 9); c.drawString(50, 50, TC_TEXT)
    
    c.save()
    buffer.seek(0)
    return buffer

# --- MAIN UI ---
st.title("🏥 Surgicraft Multi-Quotation (Web)")
st.caption("Created by Ankit Mistry")

# Party Name
party_name = st.text_input("Party Name:", placeholder="Enter customer name...")

# Machine Details
st.subheader("Machine Details")
col1, col2, col3 = st.columns(3)
with col1:
    widths = sorted(list(set([k.split('x')[0] for k in DEF_PRICES.keys()])))
    w_val = st.selectbox("Width", widths)
with col2:
    lengths = sorted(list(set([k.split('x')[1] for k in DEF_PRICES.keys()])))
    l_val = st.selectbox("Length", lengths)
with col3:
    speed = st.selectbox("Speed", ["Low", "High", "Low+High"])

size = f"{w_val}x{l_val}"

# Addons
st.write("### Add-ons")
cols = st.columns(3)
selected_addons = []
col_idx = 0

for addon_name in DEF_ADDONS:
    if addon_name in ["LowHighExtra", "PressureSwitch"]: continue
    if cols[col_idx % 3].checkbox(addon_name):
        selected_addons.append(addon_name)
    col_idx += 1

ps_qty = st.selectbox("Pressure Switch Qty:", [0, 1, 2])

# Calculate Price
total_price = DEF_PRICES.get(size, 0)
if total_price == 0:
    st.error(f"Price not found for size {size}")
else:
    if speed == "Low+High": total_price += DEF_ADDONS["LowHighExtra"]
    for addon in selected_addons: total_price += DEF_ADDONS[addon]
    if ps_qty > 0: 
        total_price += (ps_qty * DEF_ADDONS["PressureSwitch"])
        selected_addons.append(f"{ps_qty} Pressure Switch")
        
    st.write(f"**Calculated Item Price: Rs. {total_price}/-**")

    # Add to Cart Button
    if st.button("➕ ADD TO PRICE LIST", type="primary"):
        if not party_name:
            st.warning("Please enter Party Name first!")
        else:
            item_data = {"size": size, "speed": speed, "options": selected_addons, "total": total_price}
            st.session_state.cart.append(item_data)
            
            # Save to Google Sheet
            try:
                sheet = connect_to_sheet()
                dt = datetime.now().strftime("%d-%m-%Y")
                sheet.append_row([st.session_state.q_no, party_name, dt, size, speed, json.dumps(selected_addons), total_price])
                st.success(f"{size} added to list and saved to Google Sheets! ✅")
            except Exception as e:
                st.error(f"Saved to cart, but Google Sheets error: {e}")

# Display Cart
if st.session_state.cart:
    st.write("---")
    st.subheader("Current Cart")
    
    # Convert cart to dataframe for nice display
    df = pd.DataFrame(st.session_state.cart)
    df['options'] = df['options'].apply(lambda x: ", ".join(x))
    st.dataframe(df, use_container_width=True)
    
    # Generate PDF
    dt_str = datetime.now().strftime("%d-%m-%Y")
    pdf_buffer = create_pdf(party_name, st.session_state.q_no, st.session_state.cart, dt_str)
    
    colA, colB = st.columns(2)
    with colA:
        st.download_button(
            label="📄 DOWNLOAD PDF",
            data=pdf_buffer,
            file_name=f"Quotation_{party_name}_{st.session_state.q_no.replace('/','_')}.pdf",
            mime="application/pdf"
        )
    with colB:
        if st.button("Clear List (New Quotation)"):
            st.session_state.cart = []
            st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"
            st.rerun()
