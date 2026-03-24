import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime
import pandas as pd
import io
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

st.set_page_config(page_title="Surgicraft App", layout="wide")

# --- SETTINGS MANAGER ---
SETTINGS_FILE = "surgicraft_settings.json"
DEF_SETTINGS = {
    "prices": {
        "16x24": 160000, "16x36": 175000, "16x39": 180000, "16x48": 190000,
        "20x24": 195000, "20x36": 210000, "20x39": 215000, "20x48": 225000,
        "24x24": 240000, "24x36": 260000, "24x39": 270000, "24x48": 280000
    },
    "addons": {
        "VacuumPump": 35000, "Only Provision V.Pump Bush": 18000,
        "DoubleDoor": 30000, "Alarm": 4000, "Gauge": 5000,
        "PressureSwitch": 6000, "LowHighExtra": 12000
    },
    "tc": "Terms: GST Extra, Transport Extra, Subject to Ahmedabad Jurisdiction."
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    return DEF_SETTINGS

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f)

settings = load_settings()

# --- SESSION STATE ---
if 'cart' not in st.session_state: st.session_state.cart = []
if 'q_no' not in st.session_state: st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_sheet():
    info = json.loads(st.secrets["google_key"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    client = gspread.authorize(creds)
    return client.open("Surgicraft_Database").sheet1

# --- PDF GENERATORS ---
def create_bill_pdf(party, q_no, items, date_str):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 20); c.drawString(150, 790, "SURGICRAFT INDUSTRIES")
    c.setFont("Helvetica", 10); c.drawString(150, 775, "Manufacturers of Hospital Equipment | Since 1985")
    c.line(50, 700, 550, 700)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 670, f"Quotation No: {q_no}"); c.drawString(400, 670, f"Date: {date_str}")
    c.drawString(50, 650, f"Party Name: {party}")
    
    y = 610; c.setFont("Helvetica-Bold", 10)
    c.drawString(50, y, "Sr."); c.drawString(80, y, "Machine Size")
    c.drawString(180, y, "Specifications"); c.drawString(450, y, "Net Price (Rs)")
    c.line(50, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 10); grand_total = 0
    for i, item in enumerate(items, 1):
        c.drawString(50, y, str(i)); c.drawString(80, y, item['size'])
        opts_str = f"Speed: {item['speed']} | " + ", ".join(item['options'])
        c.drawString(180, y, opts_str[:55]); c.drawString(450, y, str(item['total']))
        grand_total += item['total']; y -= 20
            
    c.line(50, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(50, y-25, f"GRAND TOTAL VALUE: Rs. {grand_total}/-")
    c.setFont("Helvetica-Oblique", 9); c.drawString(50, 50, settings['tc'])
    c.save(); buffer.seek(0)
    return buffer

def create_history_pdf(party, records_df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 20); c.drawString(150, 790, "SURGICRAFT INDUSTRIES")
    c.setFont("Helvetica", 12); c.drawString(150, 770, "Customer Account History Statement")
    c.line(40, 750, 550, 750)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 720, f"Party Name: {party}"); c.drawString(400, 720, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 680; c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "Date"); c.drawString(110, y, "Q.No"); c.drawString(200, y, "Size"); c.drawString(450, y, "Amount (Rs)")
    c.line(40, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 10); grand_total = 0
    for index, row in records_df.iterrows():
        c.drawString(40, y, str(row['Date'])); c.drawString(110, y, str(row['Q_No'])); c.drawString(200, y, str(row['Size']))
        c.drawString(450, y, str(row['Total_Price']))
        try: grand_total += int(row['Total_Price'])
        except: pass
        y -= 20
        if y < 100: c.showPage(); y = 750
        
    c.line(40, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y-25, f"TOTAL HISTORICAL VALUE: Rs. {grand_total}/-")
    c.save(); buffer.seek(0)
    return buffer


# --- SIDEBAR MENU ---
st.sidebar.title("🏥 Surgicraft Menu")
menu = st.sidebar.radio("Go to:", ["📝 Create Quotation", "📜 Party History & Search", "⚙️ Master Settings"])

try:
    sheet = get_sheet()
except Exception as e:
    st.error(f"Google Sheet Connection Error! Code: {e}")
    st.stop()


# ==========================================
# 1. CREATE QUOTATION PAGE
# ==========================================
if menu == "📝 Create Quotation":
    st.title("Create New Quotation")
    party_name = st.text_input("Party Name:", placeholder="Enter customer name...")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        widths = sorted(list(set([k.split('x')[0] for k in settings['prices'].keys()])))
        w_val = st.selectbox("Width", widths if widths else ["0"])
    with col2:
        lengths = sorted(list(set([k.split('x')[1] for k in settings['prices'].keys()])))
        l_val = st.selectbox("Length", lengths if lengths else ["0"])
    with col3:
        speed = st.selectbox("Speed", ["Low", "High", "Low+High"])

    size = f"{w_val}x{l_val}"
    
    st.write("### Add-ons")
    cols = st.columns(3)
    selected_addons = []
    col_idx = 0
    for addon_name in settings['addons']:
        if addon_name in ["LowHighExtra", "PressureSwitch"]: continue
        if cols[col_idx % 3].checkbox(addon_name): selected_addons.append(addon_name)
        col_idx += 1
    ps_qty = st.selectbox("Pressure Switch Qty:", [0, 1, 2])

    # Price Calc
    total_price = settings['prices'].get(size, 0)
    if total_price == 0:
        st.error(f"Price not found for size {size}. Please add it in Master Settings.")
    else:
        if speed == "Low+High": total_price += settings['addons'].get("LowHighExtra", 0)
        for addon in selected_addons: total_price += settings['addons'].get(addon, 0)
        if ps_qty > 0: 
            total_price += (ps_qty * settings['addons'].get("PressureSwitch", 0))
            selected_addons.append(f"{ps_qty} Pressure Switch")
            
        st.success(f"**Calculated Item Price: Rs. {total_price}/-**")

        if st.button("➕ ADD TO PRICE LIST", type="primary"):
            if not party_name: st.warning("Please enter Party Name first!")
            else:
                st.session_state.cart.append({"size": size, "speed": speed, "options": selected_addons, "total": total_price})
                dt = datetime.now().strftime("%d-%m-%Y")
                
                # Check if Headers exist, if not add them
                if not sheet.get_all_values():
                    sheet.append_row(["Q_No", "Party", "Date", "Size", "Speed", "Options", "Total_Price"])
                    
                sheet.append_row([st.session_state.q_no, party_name, dt, size, speed, json.dumps(selected_addons), total_price])
                st.toast("Item Added to Google Sheet! ✅")

    if st.session_state.cart:
        st.write("---")
        st.subheader("Current Cart")
        df = pd.DataFrame(st.session_state.cart)
        st.dataframe(df, use_container_width=True)
        
        pdf_buffer = create_bill_pdf(party_name, st.session_state.q_no, st.session_state.cart, datetime.now().strftime("%d-%m-%Y"))
        colA, colB = st.columns(2)
        with colA:
            st.download_button("📄 DOWNLOAD QUOTATION PDF", data=pdf_buffer, file_name=f"Quotation_{party_name}.pdf", mime="application/pdf")
        with colB:
            if st.button("Clear List (New Session)"):
                st.session_state.cart = []; st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"; st.rerun()


# ==========================================
# 2. PARTY HISTORY PAGE
# ==========================================
elif menu == "📜 Party History & Search":
    st.title("Party Search History")
    
    data = sheet.get_all_records()
    if not data:
        st.info("No records found in Google Sheet.")
    else:
        df = pd.DataFrame(data)
        
        # Search Box
        search_party = st.text_input("🔍 Search Party Name:", placeholder="Type name to filter...")
        
        if search_party:
            filtered_df = df[df['Party'].str.contains(search_party, case=False, na=False)]
        else:
            filtered_df = df.tail(50) # Show last 50 by default
            
        st.dataframe(filtered_df, use_container_width=True)
        
        st.write("---")
        col1, col2 = st.columns(2)
        
        with col1:
            st.write("### 📄 Generate History PDF")
            pdf_party = st.text_input("Enter exact Party Name for PDF:")
            if st.button("Generate Party History PDF"):
                if pdf_party:
                    party_df = df[df['Party'].str.lower() == pdf_party.lower()]
                    if not party_df.empty:
                        hist_pdf = create_history_pdf(pdf_party, party_df)
                        st.download_button("📥 Download History PDF", data=hist_pdf, file_name=f"History_{pdf_party}.pdf", mime="application/pdf")
                    else:
                        st.warning("No records found for this party.")
                else:
                    st.warning("Please enter a party name.")

        with col2:
            st.write("### ❌ Delete Record")
            st.caption("Delete a record using its Q_No")
            del_qno = st.text_input("Enter Q_No to delete:")
            if st.button("Delete from Sheet", type="primary"):
                if del_qno:
                    # Find row in sheet
                    try:
                        cell = sheet.find(del_qno)
                        sheet.delete_rows(cell.row)
                        st.success(f"Record {del_qno} deleted successfully!")
                        st.rerun()
                    except:
                        st.error("Q_No not found in Sheet.")


# ==========================================
# 3. MASTER SETTINGS PAGE
# ==========================================
elif menu == "⚙️ Master Settings":
    st.title("Master Settings")
    st.info("Changes made here will be saved permanently.")
    
    tab1, tab2 = st.tabs(["Machine Prices", "Add-ons & T&C"])
    
    with tab1:
        st.subheader("Edit Current Prices")
        prices = settings['prices']
        new_prices = {}
        
        cols = st.columns(4)
        for i, (size, price) in enumerate(prices.items()):
            new_prices[size] = cols[i % 4].number_input(f"Size {size}", value=price, step=1000)
            
        st.write("---")
        st.subheader("Add New Size")
        colA, colB, colC = st.columns(3)
        n_w = colA.text_input("Width (e.g. 24)")
        n_l = colB.text_input("Length (e.g. 48)")
        n_p = colC.number_input("Price", value=0, step=1000)
        
        if st.button("Save Prices"):
            if n_w and n_l and n_p > 0:
                new_prices[f"{n_w}x{n_l}"] = n_p
            settings['prices'] = new_prices
            save_settings(settings)
            st.success("Prices Updated!")
            st.rerun()

    with tab2:
        st.subheader("Edit Add-on Prices")
        addons = settings['addons']
        new_addons = {}
        
        cols = st.columns(3)
        for i, (name, price) in enumerate(addons.items()):
            new_addons[name] = cols[i % 3].number_input(f"{name}", value=price, step=500)
            
        st.write("---")
        new_tc = st.text_area("Terms & Conditions", value=settings.get('tc', ''))
        
        if st.button("Save Add-ons & T&C"):
            settings['addons'] = new_addons
            settings['tc'] = new_tc
            save_settings(settings)
            st.success("Add-ons and T&C Updated!")
            st.rerun()
