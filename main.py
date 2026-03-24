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
    "password": "1234",
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
        # Handle options format for both new cart items and old db records
        opts = item['options']
        if isinstance(opts, str):
            try: opts = json.loads(opts)
            except: opts = [opts]
        opts_str = f"Speed: {item['speed']} | " + ", ".join(opts)
        c.drawString(180, y, opts_str[:55]); c.drawString(450, y, str(item['total']))
        grand_total += int(item['total']); y -= 20
            
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
        widths = sorted(list(set([k.split('x')[0] for k in settings['prices'].keys() if 'x' in k])))
        w_val = st.selectbox("Width", widths if widths else ["0"])
    with col2:
        lengths = sorted(list(set([k.split('x')[1] for k in settings['prices'].keys() if 'x' in k])))
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
                # Appending party_name so it shows in the cart
                st.session_state.cart.append({"party": party_name, "size": size, "speed": speed, "options": selected_addons, "total": total_price})
                dt = datetime.now().strftime("%d-%m-%Y")
                
                if not sheet.get_all_values():
                    sheet.append_row(["Q_No", "Party", "Date", "Size", "Speed", "Options", "Total_Price"])
                    
                sheet.append_row([st.session_state.q_no, party_name, dt, size, speed, json.dumps(selected_addons), total_price])
                st.toast("Item Added to Google Sheet! ✅")

    if st.session_state.cart:
        st.write("---")
        st.subheader("Current Cart")
        df = pd.DataFrame(st.session_state.cart)
        # Rename columns for better display
        df.rename(columns={'party': 'Party Name', 'size': 'Size', 'speed': 'Speed', 'options': 'Addons', 'total': 'Price'}, inplace=True)
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
        
        # Advance Search Box
        search_party = st.text_input("🔍 Search Party Name or Q_No:", placeholder="Type name or Q_No to search...")
        
        if search_party:
            # Filter by Party Name OR Q_No
            mask = df['Party'].astype(str).str.contains(search_party, case=False, na=False) | \
                   df['Q_No'].astype(str).str.contains(search_party, case=False, na=False)
            filtered_df = df[mask]
        else:
            filtered_df = df.tail(50)
            
        st.dataframe(filtered_df, use_container_width=True)
        
        st.write("---")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.write("### 📜 Party History PDF")
            pdf_party = st.text_input("Enter Party Name for History PDF:")
            if st.button("Generate History PDF"):
                if pdf_party:
                    party_df = df[df['Party'].astype(str).str.lower() == pdf_party.lower()]
                    if not party_df.empty:
                        hist_pdf = create_history_pdf(pdf_party, party_df)
                        st.download_button("📥 Download History PDF", data=hist_pdf, file_name=f"History_{pdf_party}.pdf", mime="application/pdf")
                    else:
                        st.warning("No records found for this party.")
                else:
                    st.warning("Please enter a party name.")

        with col2:
            st.write("### 📄 Reprint Old Bill")
            reprint_qno = st.text_input("Enter Q_No to Reprint Bill:")
            if st.button("Generate Bill PDF"):
                if reprint_qno:
                    bill_df = df[df['Q_No'].astype(str) == reprint_qno]
                    if not bill_df.empty:
                        party_n = bill_df.iloc[0]['Party']
                        date_n = bill_df.iloc[0]['Date']
                        # Convert dataframe rows to items list for the PDF function
                        items_list = []
                        for _, r in bill_df.iterrows():
                            items_list.append({"size": r['Size'], "speed": r['Speed'], "options": r['Options'], "total": r['Total_Price']})
                        
                        bill_pdf = create_bill_pdf(party_n, reprint_qno, items_list, str(date_n))
                        st.download_button("📥 Download Bill PDF", data=bill_pdf, file_name=f"Reprint_{reprint_qno.replace('/','_')}.pdf", mime="application/pdf")
                    else:
                        st.warning("Q_No not found.")

        with col3:
            st.write("### ❌ Delete Record")
            del_qno = st.text_input("Enter exact Q_No to Delete:")
            if st.button("Delete from Sheet", type="primary"):
                if del_qno:
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
    st.title("Master Settings 🔒")
    
    # Password Protection
    pwd_input = st.text_input("Enter Master Password to Access Settings:", type="password")
    
    if pwd_input != settings.get('password', '1234'):
        if pwd_input:
            st.error("❌ Incorrect Password!")
        st.stop()
        
    st.success("Access Granted!")
    st.info("Changes made here will be saved permanently.")
    
    tab1, tab2, tab3 = st.tabs(["Machine Prices", "Add-ons", "Security & T&C"])
    
    with tab1:
        st.subheader("Edit or Remove Current Sizes")
        prices = settings['prices']
        
        for size, price in list(prices.items()):
            colA, colB, colC = st.columns([2, 2, 1])
            with colA:
                st.write(f"**{size}**")
            with colB:
                new_val = st.number_input(f"Price for {size}", value=price, step=1000, key=f"p_{size}", label_visibility="collapsed")
                prices[size] = new_val
            with colC:
                if st.button("❌ Remove", key=f"del_size_{size}"):
                    del prices[size]
                    save_settings(settings)
                    st.rerun()
                    
        st.write("---")
        st.subheader("Add New Size")
        colA, colB, colC = st.columns(3)
        n_w = colA.text_input("Width (e.g. 24)")
        n_l = colB.text_input("Length (e.g. 48)")
        n_p = colC.number_input("Price", value=0, step=1000)
        
        if st.button("➕ Add New Size"):
            if n_w and n_l and n_p > 0:
                settings['prices'][f"{n_w}x{n_l}"] = n_p
                save_settings(settings)
                st.success("New Size Added!")
                st.rerun()
            else:
                st.error("Please fill all fields.")

    with tab2:
        st.subheader("Edit or Remove Current Add-ons")
        addons = settings['addons']
        
        for name, price in list(addons.items()):
            if name in ["LowHighExtra", "PressureSwitch"]:
                colA, colB = st.columns([2, 3])
                colA.write(f"**{name}** (System Addon)")
                addons[name] = colB.number_input(f"Price for {name}", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
            else:
                colA, colB, colC = st.columns([2, 2, 1])
                with colA:
                    st.write(f"**{name}**")
                with colB:
                    addons[name] = st.number_input(f"Price for {name}", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
                with colC:
                    if st.button("❌ Remove", key=f"del_addon_{name}"):
                        del addons[name]
                        save_settings(settings)
                        st.rerun()
                        
        if st.button("💾 Save Add-on Prices"):
            save_settings(settings)
            st.success("Add-on Prices Updated!")
            
        st.write("---")
        st.subheader("Add New Add-on Option")
        c1, c2 = st.columns(2)
        new_addon_name = c1.text_input("Add-on Name")
        new_addon_price = c2.number_input("Add-on Price", value=0, step=500)
        if st.button("➕ Add New Option"):
            if new_addon_name and new_addon_price > 0:
                settings['addons'][new_addon_name] = new_addon_price
                save_settings(settings)
                st.success(f"{new_addon_name} added!")
                st.rerun()
            else:
                st.error("Please enter valid name and price.")

    with tab3:
        st.subheader("Change Master Password")
        new_pwd = st.text_input("New Password:", type="password")
        if st.button("Update Password"):
            if new_pwd:
                settings['password'] = new_pwd
                save_settings(settings)
                st.success("Password Updated!")
            else:
                st.warning("Password cannot be empty.")
                
        st.write("---")
        st.subheader("Terms & Conditions")
        new_tc = st.text_area("T&C for PDF", value=settings.get('tc', ''))
        if st.button("Update T&C"):
            settings['tc'] = new_tc
            save_settings(settings)
            st.success("T&C Updated!")
