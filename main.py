import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime
import calendar
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
LOGO_PATH = "logo.png"

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

# --- HELPER FORMAT FUNCTION (Inch formatting) ---
def format_size(size_str):
    if "x" in size_str:
        parts = size_str.split('x')
        if len(parts) == 2:
            return f'{parts[0].strip()}" x {parts[1].strip()}"'
    return size_str

# --- PDF GENERATORS ---
def create_bill_pdf(party, q_no, items_data, date_str):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    text_start_x = 50
    if os.path.exists(LOGO_PATH):
        try:
            c.drawImage(LOGO_PATH, 50, 740, width=80, height=50, mask='auto')
            text_start_x = 150
        except: pass
        
    c.setFont("Helvetica-Bold", 20); c.drawString(text_start_x, 780, "SURGICRAFT INDUSTRIES")
    c.setFont("Helvetica", 10); c.drawString(text_start_x, 765, "Manufacturers of Hospital Equipment | Since 1985")
    c.line(50, 730, 550, 730)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, 700, f"Quotation No: {q_no}"); c.drawString(400, 700, f"Date: {date_str}")
    c.drawString(50, 680, f"Party Name: {party}")
    
    y = 650; c.setFont("Helvetica-Bold", 11)
    c.drawString(50, y, "Sr."); c.drawString(90, y, "Description"); c.drawString(460, y, "Amount (Rs)")
    c.line(50, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 11); grand_total = 0
    
    for i, item in enumerate(items_data, 1):
        base_size = format_size(item.get('size', 'Unknown Size'))
        base_price = int(item.get('base_price', 0))
        
        c.drawString(50, y, str(i)); c.setFont("Helvetica-Bold", 11); c.drawString(90, y, f"Machine Size: {base_size}"); c.setFont("Helvetica", 11);
        if base_price > 0: c.drawString(460, y, f"{base_price:,.2f}")
        grand_total += base_price; y -= 18
        
        speed = item.get('speed', 'Low')
        c.setFont("Helvetica-Oblique", 11); c.drawString(100, y, f"  • Speed: {speed}"); c.setFont("Helvetica", 11);
        y -= 18
        
        raw_addons = item.get('addons_breakdown', {})
        addons_dict = {}
        
        if isinstance(raw_addons, str):
            try:
                parsed = json.loads(raw_addons)
                if isinstance(parsed, dict): addons_dict = parsed
                elif isinstance(parsed, list): addons_dict = {addon: 0 for addon in parsed}
            except:
                addons_dict = {raw_addons: 0}
        elif isinstance(raw_addons, list):
            addons_dict = {addon: 0 for addon in raw_addons}
        elif isinstance(raw_addons, dict):
            addons_dict = raw_addons
            
        for name, price in addons_dict.items():
            price_val = int(price) if price else 0
            c.drawString(100, y, f"  • Addon: {name}")
            if price_val > 0: 
                c.drawString(460, y, f"{price_val:,.2f}")
                grand_total += price_val
            y -= 18
            
        y -= 10
        if y < 150:
            c.showPage(); y = 750; c.setFont("Helvetica", 11)
            c.drawString(50, y, "Sr."); c.drawString(90, y, "Description"); c.drawString(460, y, "Amount (Rs)")
            c.line(50, y-5, 550, y-5); y -= 25

    if grand_total == 0 and item.get('total'):
        grand_total = int(item.get('total'))

    c.line(50, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(50, y-25, f"GRAND TOTAL VALUE: Rs. {grand_total:,.2f}/-")
    c.setFont("Helvetica-Oblique", 9); c.drawString(50, 50, settings['tc'])
    
    c.save(); buffer.seek(0)
    return buffer

def create_history_pdf(party, records_df, period_str="Lifetime"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    text_start_x = 40
    if os.path.exists(LOGO_PATH):
        try:
            c.drawImage(LOGO_PATH, 40, 750, width=60, height=40, mask='auto')
            text_start_x = 120
        except: pass
    
    c.setFont("Helvetica-Bold", 20); c.drawString(text_start_x, 780, "SURGICRAFT INDUSTRIES")
    c.setFont("Helvetica", 12); c.drawString(text_start_x, 765, f"{period_str} Account Statement (Detailed)")
    c.line(40, 740, 550, 740)
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 710, f"Party Name: {party}"); c.drawString(400, 710, f"Date generated: {datetime.now().strftime('%d-%m-%Y')}")
    
    # Removed Q.No, given more space to Description
    y = 670; c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Date"); c.drawString(100, y, "Description / Details"); c.drawString(460, y, "Amount (Rs)")
    c.line(40, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 11); grand_total = 0
    
    try:
        records_df['DateObj'] = pd.to_datetime(records_df['Date'], format="%d-%m-%Y", errors='coerce')
        records_df = records_df.sort_values('DateObj')
    except:
        pass

    for index, row in records_df.iterrows():
        date_str = str(row['Date'])
        size_str = format_size(str(row['Size']))
        speed_str = str(row['Speed'])
        total_price = int(row['Total_Price']) if pd.notna(row['Total_Price']) else 0
        
        # Base Price
        base_price = int(settings['prices'].get(str(row['Size']), 0))
        
        # Addons Dictionary
        raw_addons = row.get('Options', '{}')
        addons_dict = {}
        if isinstance(raw_addons, str):
            try:
                parsed = json.loads(raw_addons)
                if isinstance(parsed, dict): addons_dict = parsed
                elif isinstance(parsed, list): addons_dict = {addon: 0 for addon in parsed}
            except:
                addons_dict = {raw_addons: 0}
        elif isinstance(raw_addons, list):
            addons_dict = {addon: 0 for addon in raw_addons}
        elif isinstance(raw_addons, dict):
            addons_dict = raw_addons

        # Print 1: Date & Machine Size
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, date_str); c.drawString(100, y, f"Machine Size: {size_str}")
        if base_price > 0:
            c.drawString(460, y, f"{base_price:,.2f}")
        else:
            c.drawString(460, y, f"{total_price:,.2f}") # Fallback for very old records
        y -= 16
        
        # Print 2: Speed
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(110, y, f"• Speed: {speed_str}")
        y -= 16
        
        # Print 3: Addons Loop
        for name, price in addons_dict.items():
            p_val = int(price) if price else 0
            c.drawString(110, y, f"• {name}")
            if p_val > 0:
                c.drawString(460, y, f"{p_val:,.2f}")
            y -= 16
            
        # Print 4: Subtotal for this specific bill
        c.setFont("Helvetica-Bold", 10)
        c.drawString(110, y, "Bill Total:")
        c.drawString(460, y, f"{total_price:,.2f}")
        
        grand_total += total_price
        y -= 25 # Space between different bills
        
        if y < 100:
            c.showPage(); y = 750; c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Date"); c.drawString(100, y, "Description / Details"); c.drawString(460, y, "Amount (Rs)")
            c.line(40, y-5, 550, y-5); y -= 25
        
    c.line(40, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y-25, f"{period_str.upper()} TOTAL VALUE: Rs. {grand_total:,.2f}/-")
    
    c.save(); buffer.seek(0)
    return buffer


# --- SIDEBAR MENU ---
st.sidebar.title("🏥 Surgicraft Menu")
menu = st.sidebar.radio("Go to:", ["➕ New Quotation Session", "📜 Party History & Search", "⚙️ Master Settings"])

try:
    sheet = get_sheet()
except Exception as e:
    st.error(f"Google Sheet Connection Error! Error: {e}")
    st.stop()


# ==========================================
# 1. CREATE QUOTATION PAGE
# ==========================================
if menu == "➕ New Quotation Session":
    st.title("Surgicraft Industries") 
    st.caption("Created by Ankit Mistry") 
    
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=150)
    st.write("---")
    
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
    addons_prices_struct = {} 
    col_idx = 0
    
    if speed == "Low+High":
        lh_price = settings['addons'].get("LowHighExtra", 0)
        addons_prices_struct["Low+High Speed Extra"] = lh_price
        st.warning(f"Note: Low+High speed adds extra Rs. {lh_price:,}/-")
        
    for addon_name in settings['addons']:
        if addon_name in ["LowHighExtra", "PressureSwitch"]: continue
        if cols[col_idx % 3].checkbox(addon_name):
            selected_addons.append(addon_name)
            addons_prices_struct[addon_name] = settings['addons'].get(addon_name, 0)
        col_idx += 1
        
    ps_qty = st.selectbox("Pressure Switch Qty:", [0, 1, 2])
    if ps_qty > 0:
        ps_unit_price = settings['addons'].get("PressureSwitch", 0)
        ps_total_price = ps_qty * ps_unit_price
        addons_prices_struct[f"Pressure Switch ({ps_qty} Qty)"] = ps_total_price
        selected_addons.append(f"{ps_qty} Pressure Switch")

    base_machine_price = int(settings['prices'].get(size, 0))
    
    if base_machine_price == 0:
        st.error(f"Base price not found for size {size}. Please add it in Master Settings.")
    else:
        addons_total_price = sum(addons_prices_struct.values())
        final_total_price = base_machine_price + addons_total_price
            
        st.success(f"**Calculated Item Price: Rs. {final_total_price:,.2f}/-**")

        if st.button("➕ ADD TO PRICE LIST", type="primary"):
            if not party_name: st.warning("Please enter Party Name first!")
            else:
                st.session_state.cart.append({
                    "party": party_name, 
                    "size": size, 
                    "base_price": base_machine_price,
                    "speed": speed,
                    "addons_breakdown": addons_prices_struct,
                    "total": final_total_price
                })
                
                dt = datetime.now().strftime("%d-%m-%Y")
                sheet.append_row([st.session_state.q_no, party_name, dt, size, speed, json.dumps(addons_prices_struct), final_total_price])
                st.toast("Item Added to Google Sheet! ✅")

    if st.session_state.cart:
        st.write("---")
        st.subheader("Current Session Items")
        
        cart_display_list = []
        for c_item in st.session_state.cart:
            addons_list_str = ", ".join(c_item['addons_breakdown'].keys())
            cart_display_list.append({
                "Party Name": c_item['party'],
                "Size": format_size(c_item['size']),
                "Speed": c_item['speed'],
                "Addons": addons_list_str,
                "Price": f"{int(c_item['total']):,.2f}"
            })
            
        st.dataframe(pd.DataFrame(cart_display_list), use_container_width=True)
        
        pdf_buffer = create_bill_pdf(party_name, st.session_state.q_no, st.session_state.cart, datetime.now().strftime("%d-%m-%Y"))
        
        colA, colB = st.columns(2)
        with colA:
            st.download_button("📄 DOWNLOAD QUOTATION PDF (Detailed)", data=pdf_buffer, file_name=f"Quotation_{party_name.replace(' ','_')}_{datetime.now().strftime('%d-%m-%Y')}.pdf", mime="application/pdf")
        with colB:
            if st.button("Clear List (Start New Session)"):
                st.session_state.cart = []; st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"; st.rerun()


# ==========================================
# 2. PARTY HISTORY PAGE 
# ==========================================
elif menu == "📜 Party History & Search":
    st.title("Party Search History")
    
    data = sheet.get_all_records()
    if not data:
        st.info("No records found in Google Sheet. Please add some items first.")
    else:
        df = pd.DataFrame(data)
        
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        df['DateObj'] = pd.to_datetime(df['Date'], format="%d-%m-%Y", errors='coerce')
        df['Year'] = df['DateObj'].dt.year
        df['MonthNum'] = df['DateObj'].dt.month
        df = df.sort_values(by='DateObj')
        
        search_party = st.text_input("🔍 Type here to search Table (Party Name or Q_No):", placeholder="Live filter...")
        
        if search_party:
            mask = df['Party'].astype(str).str.contains(search_party, case=False, na=False) | \
                   df['Q_No'].astype(str).str.contains(search_party, case=False, na=False)
            filtered_df = df[mask]
        else:
            filtered_df = df.tail(100)
            
        st.dataframe(filtered_df.drop(columns=['Clean_Party', 'DateObj', 'Year', 'MonthNum'], errors='ignore'), use_container_width=True)
        st.write("---")
        
        col1, col2, col3 = st.columns(3)
        
        unique_parties = sorted(df['Clean_Party'].unique().tolist())
        unique_qnos = sorted(df['Q_No'].astype(str).unique().tolist(), reverse=True)
        
        with col1:
            st.write("### 📜 Party Statement PDF")
            pdf_party = st.selectbox("Select Party:", ["-- Select Party --"] + unique_parties)
            
            if pdf_party != "-- Select Party --":
                party_df = df[df['Clean_Party'] == pdf_party].copy()
                
                years = sorted(party_df['Year'].dropna().unique().astype(int).tolist(), reverse=True)
                selected_year = st.selectbox("Select Year:", ["All Time"] + years)
                
                period_str = "Lifetime"
                
                if selected_year != "All Time":
                    party_df = party_df[party_df['Year'] == selected_year]
                    period_str = f"Year {selected_year}"
                    
                    months_present = sorted(party_df['MonthNum'].dropna().unique().astype(int).tolist())
                    month_names_dict = {m: calendar.month_name[m] for m in months_present}
                    
                    selected_month = st.selectbox("Select Month:", ["All Months"] + list(month_names_dict.values()))
                    
                    if selected_month != "All Months":
                        month_num = [k for k, v in month_names_dict.items() if v == selected_month][0]
                        party_df = party_df[party_df['MonthNum'] == month_num]
                        period_str = f"{selected_month} {selected_year}"

                if st.button(f"Generate Detailed {period_str} PDF"):
                    if not party_df.empty:
                        hist_pdf = create_history_pdf(pdf_party, party_df, period_str)
                        st.download_button("📥 Download Statement", data=hist_pdf, file_name=f"Statement_{pdf_party.replace(' ','_')}_{period_str.replace(' ','_')}.pdf", mime="application/pdf")
                    else:
                        st.warning("No records found for this period.")

        with col2:
            st.write("### 📄 Reprint Old Bill")
            reprint_qno = st.selectbox("Select Q_No to Reprint:", ["-- Select Q_No --"] + unique_qnos)
            
            if st.button("Generate Detailed Bill PDF"):
                if reprint_qno != "-- Select Q_No --":
                    bill_df = df[df['Q_No'].astype(str) == reprint_qno]
                    if not bill_df.empty:
                        party_n = bill_df.iloc[0]['Party']
                        date_n = bill_df.iloc[0]['Date']
                        
                        reprint_items_struct = []
                        for _, r in bill_df.iterrows():
                            size_n = str(r['Size'])
                            base_p_calc = int(settings['prices'].get(size_n, 0))
                            
                            reprint_items_struct.append({
                                "size": size_n, 
                                "base_price": base_p_calc,
                                "speed": r['Speed'],
                                "addons_breakdown": r['Options'], 
                                "total": r['Total_Price']
                            })
                        
                        detailed_bill_pdf = create_bill_pdf(party_n, reprint_qno, reprint_items_struct, str(date_n))
                        st.download_button("📥 Download Bill PDF", data=detailed_bill_pdf, file_name=f"Reprint_{reprint_qno.replace('/','_')}.pdf", mime="application/pdf")
                else:
                    st.warning("Please select a Q_No from the list.")

        with col3:
            st.write("### ❌ Delete Record")
            del_qno = st.selectbox("Select Q_No to Delete:", ["-- Select Q_No --"] + unique_qnos)
            if st.button("Delete from Sheet", type="primary"):
                if del_qno != "-- Select Q_No --":
                    try:
                        cell = sheet.find(del_qno)
                        sheet.delete_rows(cell.row)
                        st.success(f"Record {del_qno} deleted successfully!")
                        st.rerun()
                    except:
                        st.error("Q_No not found in Sheet.")
                else:
                    st.warning("Please select a Q_No to delete.")


# ==========================================
# 3. MASTER SETTINGS PAGE
# ==========================================
elif menu == "⚙️ Master Settings":
    st.title("Master Settings 🔒")
    
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
                st.write(f"**{format_size(size)}**")
            with colB:
                new_val = st.number_input(f"Price for {size}", value=price, step=1000, key=f"p_{size}", label_visibility="collapsed")
                prices[size] = new_val
            with colC:
                if st.button("❌ Remove", key=f"del_size_{size}"):
                    del prices[size]
                    save_settings(settings)
                    st.rerun()
                    
        st.write("---")
        st.subheader("Add New Machine Size")
        colA, colB, colC = st.columns(3)
        n_w = colA.text_input("Width (e.g. 24)")
        n_l = colB.text_input("Length (e.g. 48)")
        n_p = colC.number_input("Base Price", value=0, step=1000)
        
        if st.button("➕ Add New Size"):
            if n_w and n_l and n_p > 0:
                settings['prices'][f"{n_w}x{n_l}"] = n_p
                save_settings(settings)
                st.success("New Size Added permanently!")
                st.rerun()
            else:
                st.error("Please fill all fields with valid data.")

    with tab2:
        st.subheader("Edit or Remove Current Add-ons")
        addons = settings['addons']
        
        for name, price in list(addons.items()):
            if name in ["LowHighExtra", "PressureSwitch"]:
                colA, colB = st.columns([2, 3])
                disp_n = "Speed (Low+High Extra)" if name == "LowHighExtra" else "Pressure Switch (Unit Price)"
                colA.write(f"**{disp_n}**")
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
                        
        if st.button("💾 Save Add-on Price Changes", type="primary"):
            save_settings(settings)
            st.success("Add-on Prices Updated permanently!")
            
        st.write("---")
        st.subheader("Add New Add-on Option")
        c1, c2 = st.columns(2)
        new_addon_name = c1.text_input("New Add-on Name")
        new_addon_price = c2.number_input("Add-on Price", value=0, step=500)
        if st.button("➕ Add New Option permanently"):
            if new_addon_name and new_addon_price > 0:
                settings['addons'][new_addon_name] = new_addon_price
                save_settings(settings)
                st.success(f"{new_addon_name} added permanently!")
                st.rerun()

    with tab3:
        st.subheader("Change Master Password")
        new_pwd = st.text_input("New Master Password:", type="password")
        if st.button("Update Password permanently"):
            if new_pwd:
                settings['password'] = new_pwd
                save_settings(settings)
                st.success("Master Password Updated permanently!")
                
        st.write("---")
        st.subheader("Edit Terms & Conditions for PDF")
        new_tc = st.text_area("T&C text appearing in footer", value=settings.get('tc', ''), height=100)
        if st.button("Update T&C permanently"):
            settings['tc'] = new_tc
            save_settings(settings)
            st.success("T&C text Updated permanently!")
