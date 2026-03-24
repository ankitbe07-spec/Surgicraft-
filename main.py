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

# --- HELPER FORMAT FUNCTION ---
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
    
    c.setFont("Helvetica-Bold", 12)
    c.drawString(40, 800, f"Quotation No: {q_no}")
    c.drawString(400, 800, f"Date: {date_str}")
    c.drawString(40, 780, f"Party Name: {party}")
    
    y = 750; c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Sr."); c.drawString(90, y, "Description / Particulars"); c.drawString(460, y, "Amount (Rs)")
    c.line(40, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 11); grand_total = 0
    
    for i, item in enumerate(items_data, 1):
        speed = item.get('speed', 'Low')
        base_size = format_size(item.get('size', 'Unknown Size'))
        total_item_price = int(item.get('total', 0))
        
        c.drawString(40, y, str(i))
        
        if speed == "Spare Part":
            c.setFont("Helvetica-Bold", 11)
            c.drawString(90, y, f"Part / Item: {base_size}")
            c.drawString(460, y, f"{total_item_price:,.2f}")
            c.setFont("Helvetica", 11)
            grand_total += total_item_price; y -= 25
        else:
            base_price = int(item.get('base_price', 0))
            c.setFont("Helvetica-Bold", 11); c.drawString(90, y, f"Machine Size: {base_size}"); c.setFont("Helvetica", 11)
            if base_price > 0: c.drawString(460, y, f"{base_price:,.2f}")
            grand_total += base_price; y -= 18
            
            c.setFont("Helvetica-Oblique", 11); c.drawString(100, y, f"  • Speed: {speed}"); c.setFont("Helvetica", 11);
            y -= 18
            
            raw_addons = item.get('addons_breakdown', {})
            addons_dict = {}
            if isinstance(raw_addons, str):
                try:
                    parsed = json.loads(raw_addons)
                    addons_dict = parsed if isinstance(parsed, dict) else {addon: 0 for addon in parsed}
                except: addons_dict = {raw_addons: 0}
            elif isinstance(raw_addons, list): addons_dict = {addon: 0 for addon in raw_addons}
            elif isinstance(raw_addons, dict): addons_dict = raw_addons
                
            for name, price in addons_dict.items():
                price_val = int(price) if price else 0
                c.drawString(100, y, f"  • Addon: {name}")
                if price_val > 0: 
                    c.drawString(460, y, f"{price_val:,.2f}")
                    grand_total += price_val
                y -= 18
            y -= 10
            
        if y < 100:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Sr."); c.drawString(90, y, "Description / Particulars"); c.drawString(460, y, "Amount (Rs)")
            c.line(40, y-5, 550, y-5); y -= 25; c.setFont("Helvetica", 11)

    c.line(40, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y-25, f"GRAND TOTAL VALUE: Rs. {grand_total:,.2f}/-")
    c.setFont("Helvetica-Oblique", 9); c.drawString(40, 40, settings['tc'])
    
    c.save(); buffer.seek(0)
    return buffer

def create_history_pdf(party, records_df, period_str="Lifetime"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    c.setFont("Helvetica-Bold", 14); c.drawString(40, 800, f"Account History Statement ({period_str})")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 775, f"Party Name: {party}")
    c.drawString(400, 775, f"Date generated: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 740; c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Date"); c.drawString(110, y, "Description / Details"); c.drawString(460, y, "Amount (Rs)")
    c.line(40, y-5, 550, y-5)
    
    y -= 25; c.setFont("Helvetica", 11); grand_total = 0
    
    try:
        records_df['DateObj'] = pd.to_datetime(records_df['Date'], format="%d-%m-%Y", errors='coerce')
        records_df = records_df.sort_values('DateObj')
    except: pass

    for index, row in records_df.iterrows():
        date_str = str(row['Date'])
        size_str = format_size(str(row['Size']))
        speed_str = str(row['Speed'])
        total_price = int(row['Total_Price']) if pd.notna(row['Total_Price']) else 0
        
        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, date_str)
        
        if speed_str == "Spare Part":
            c.drawString(110, y, f"Part: {size_str}")
            c.drawString(460, y, f"{total_price:,.2f}")
            grand_total += total_price; y -= 20
        else:
            base_price = int(settings['prices'].get(str(row['Size']), 0))
            c.drawString(110, y, f"Machine Size: {size_str}")
            if base_price > 0: c.drawString(460, y, f"{base_price:,.2f}")
            else: c.drawString(460, y, f"{total_price:,.2f}")
            y -= 16
            
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(120, y, f"• Speed: {speed_str}")
            y -= 16
            
            raw_addons = row.get('Options', '{}')
            addons_dict = {}
            if isinstance(raw_addons, str):
                try:
                    parsed = json.loads(raw_addons)
                    addons_dict = parsed if isinstance(parsed, dict) else {addon: 0 for addon in parsed}
                except: addons_dict = {raw_addons: 0}
            elif isinstance(raw_addons, list): addons_dict = {addon: 0 for addon in raw_addons}
            elif isinstance(raw_addons, dict): addons_dict = raw_addons

            for name, price in addons_dict.items():
                p_val = int(price) if price else 0
                c.drawString(120, y, f"• {name}")
                if p_val > 0: c.drawString(460, y, f"{p_val:,.2f}")
                y -= 16
                
            c.setFont("Helvetica-Bold", 10)
            c.drawString(120, y, "Bill Total:")
            c.drawString(460, y, f"{total_price:,.2f}")
            grand_total += total_price; y -= 25
        
        if y < 80:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Date"); c.drawString(110, y, "Description / Details"); c.drawString(460, y, "Amount (Rs)")
            c.line(40, y-5, 550, y-5); y -= 25
        
    c.line(40, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y-25, f"{period_str.upper()} TOTAL VALUE: Rs. {grand_total:,.2f}/-")
    
    c.save(); buffer.seek(0)
    return buffer

def create_part_search_pdf(party_name, part_name, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Item / Part Price Search Report")
    
    c.setFont("Helvetica", 11)
    c.drawString(40, 780, f"Party: {party_name if party_name else 'All Parties'}")
    c.drawString(40, 765, f"Item/Part: {part_name if part_name else 'All Items'}")
    c.drawString(400, 780, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 730
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Date")
    c.drawString(120, y, "Party Name")
    c.drawString(280, y, "Item / Part Name")
    c.drawString(460, y, "Price (Rs)")
    c.line(40, y-5, 550, y-5)
    
    y -= 25
    c.setFont("Helvetica", 10)
    
    for index, row in df.iterrows():
        c.drawString(40, y, str(row['Date']))
        c.drawString(120, y, str(row['Party'])[:22])
        c.drawString(280, y, str(row['Size'])[:30])
        c.drawString(460, y, f"{int(row['Total_Price']):,.2f}")
        y -= 20
        
        if y < 80:
            c.showPage()
            y = 800
            c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Date")
            c.drawString(120, y, "Party Name")
            c.drawString(280, y, "Item / Part Name")
            c.drawString(460, y, "Price (Rs)")
            c.line(40, y-5, 550, y-5)
            y -= 25
            c.setFont("Helvetica", 10)
            
    c.save()
    buffer.seek(0)
    return buffer

# --- SIDEBAR MENU ---
st.sidebar.title("🏥 Surgicraft Menu")
# NAVU MENU OPTION ADD KARYU CHE:
menu = st.sidebar.radio("Go to:", ["➕ New Quotation / Bill", "📜 Party History & Search", "🔍 Part Price Finder", "⚙️ Master Settings"])

try: sheet = get_sheet()
except Exception as e:
    st.error(f"Google Sheet Connection Error! Error: {e}")
    st.stop()

# ==========================================
# 1. CREATE QUOTATION PAGE
# ==========================================
if menu == "➕ New Quotation / Bill":
    st.title("Surgicraft Billing & Quotation") 
    party_name = st.text_input("Party Name:", placeholder="Enter customer name...")
    st.write("---")
    
    entry_type = st.radio("What do you want to add?", ["Machine", "Spare Part / Custom Item"], horizontal=True)
    
    if entry_type == "Machine":
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
            final_total_price = base_machine_price + sum(addons_prices_struct.values())
            st.success(f"**Calculated Machine Price: Rs. {final_total_price:,.2f}/-**")

            if st.button("➕ ADD MACHINE TO BILL", type="primary"):
                if not party_name: st.warning("Please enter Party Name first!")
                else:
                    st.session_state.cart.append({
                        "party": party_name, "size": size, "base_price": base_machine_price,
                        "speed": speed, "addons_breakdown": addons_prices_struct, "total": final_total_price
                    })
                    dt = datetime.now().strftime("%d-%m-%Y")
                    sheet.append_row([st.session_state.q_no, party_name, dt, size, speed, json.dumps(addons_prices_struct), final_total_price])
                    st.toast("Machine Added! ✅")

    else:
        st.write("### Add Spare Part Details")
        c1, c2 = st.columns(2)
        part_name = c1.text_input("Part Name / Description (e.g., Heater Coil, Motor Repair)")
        part_price = c2.number_input("Final Price (Rs)", min_value=0, step=100)
        
        if st.button("➕ ADD PART TO BILL", type="primary"):
            if not party_name: st.warning("Please enter Party Name first!")
            elif not part_name or part_price <= 0: st.warning("Please enter Part Name and Price!")
            else:
                st.session_state.cart.append({
                    "party": party_name, "size": part_name, "base_price": 0,
                    "speed": "Spare Part", "addons_breakdown": {}, "total": part_price
                })
                dt = datetime.now().strftime("%d-%m-%Y")
                sheet.append_row([st.session_state.q_no, party_name, dt, part_name, "Spare Part", "{}", part_price])
                st.toast(f"{part_name} Added! ✅")

    if st.session_state.cart:
        st.write("---")
        st.subheader("Current Session Items")
        
        cart_display_list = []
        for c_item in st.session_state.cart:
            addons_list_str = ", ".join(c_item['addons_breakdown'].keys()) if c_item['addons_breakdown'] else "-"
            cart_display_list.append({
                "Party Name": c_item['party'],
                "Item / Size": format_size(c_item['size']),
                "Type/Speed": c_item['speed'],
                "Addons": addons_list_str,
                "Price": f"{int(c_item['total']):,.2f}"
            })
            
        st.dataframe(pd.DataFrame(cart_display_list), use_container_width=True)
        
        pdf_buffer = create_bill_pdf(party_name, st.session_state.q_no, st.session_state.cart, datetime.now().strftime("%d-%m-%Y"))
        
        colA, colB = st.columns(2)
        with colA:
            st.download_button("📄 DOWNLOAD BILL PDF", data=pdf_buffer, file_name=f"Bill_{party_name.replace(' ','_')}_{datetime.now().strftime('%d-%m-%Y')}.pdf", mime="application/pdf")
        with colB:
            if st.button("Clear List (Start New Session)"):
                st.session_state.cart = []; st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"; st.rerun()

# ==========================================
# 2. PARTY HISTORY PAGE 
# ==========================================
elif menu == "📜 Party History & Search":
    st.title("Party Search History")
    
    data = sheet.get_all_records()
    if not data: st.info("No records found in Google Sheet.")
    else:
        df = pd.DataFrame(data)
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        df['DateObj'] = pd.to_datetime(df['Date'], format="%d-%m-%Y", errors='coerce')
        df['Year'] = df['DateObj'].dt.year
        df['MonthNum'] = df['DateObj'].dt.month
        df = df.sort_values(by='DateObj')
        
        search_party = st.text_input("🔍 Search by Party Name or Q_No:", placeholder="Live filter...")
        
        if search_party:
            mask = df['Party'].astype(str).str.contains(search_party, case=False, na=False) | \
                   df['Q_No'].astype(str).str.contains(search_party, case=False, na=False)
            filtered_df = df[mask]
        else: filtered_df = df.tail(100)
            
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

                if st.button(f"Generate PDF History"):
                    if not party_df.empty:
                        hist_pdf = create_history_pdf(pdf_party, party_df, period_str)
                        st.download_button("📥 Download Statement", data=hist_pdf, file_name=f"Statement_{pdf_party.replace(' ','_')}.pdf", mime="application/pdf")
                    else: st.warning("No records found.")

        with col2:
            st.write("### 📄 Reprint Old Bill")
            reprint_qno = st.selectbox("Select Q_No to Reprint:", ["-- Select Q_No --"] + unique_qnos)
            if st.button("Generate Bill PDF"):
                if reprint_qno != "-- Select Q_No --":
                    bill_df = df[df['Q_No'].astype(str) == reprint_qno]
                    if not bill_df.empty:
                        party_n = bill_df.iloc[0]['Party']
                        date_n = bill_df.iloc[0]['Date']
                        
                        reprint_items_struct = []
                        for _, r in bill_df.iterrows():
                            size_n = str(r['Size'])
                            speed_n = str(r['Speed'])
                            base_p_calc = 0 if speed_n == "Spare Part" else int(settings['prices'].get(size_n, 0))
                            
                            reprint_items_struct.append({
                                "size": size_n, "base_price": base_p_calc,
                                "speed": speed_n, "addons_breakdown": r['Options'], "total": r['Total_Price']
                            })
                        
                        detailed_bill_pdf = create_bill_pdf(party_n, reprint_qno, reprint_items_struct, str(date_n))
                        st.download_button("📥 Download Old Bill", data=detailed_bill_pdf, file_name=f"Reprint_{reprint_qno.replace('/','_')}.pdf", mime="application/pdf")
                else: st.warning("Please select a Q_No.")

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
                    except: st.error("Q_No not found in Sheet.")
                else: st.warning("Please select a Q_No.")

# ==========================================
# 3. PART PRICE FINDER PAGE (NEW FEATURE)
# ==========================================
elif menu == "🔍 Part Price Finder":
    st.title("Item & Part Price Finder 🔍")
    st.write("Koi pan party ne past ma kyo part ketla ma apyo hato e ahiya thi check karo.")
    
    data = sheet.get_all_records()
    if not data:
        st.info("No records found in Google Sheet.")
    else:
        df = pd.DataFrame(data)
        
        c1, c2 = st.columns(2)
        search_party_name = c1.text_input("1. Party Name (e.g., Hiral):", placeholder="Enter Party Name...")
        search_part_name = c2.text_input("2. Part / Item Name (e.g., Motor):", placeholder="Enter Part Name...")
        
        filtered_df = df.copy()
        
        if search_party_name:
            filtered_df = filtered_df[filtered_df['Party'].astype(str).str.contains(search_party_name, case=False, na=False)]
        if search_part_name:
            filtered_df = filtered_df[filtered_df['Size'].astype(str).str.contains(search_part_name, case=False, na=False)]
            
        st.write("### Search Results")
        
        if not search_party_name and not search_part_name:
            st.info("Upar Party nu naam athva Part nu naam lakho etle ahiya details aavse.")
        elif filtered_df.empty:
            st.warning("Aa naam thi koi entry mali nathi.")
        else:
            display_df = filtered_df[['Date', 'Party', 'Size', 'Speed', 'Total_Price']].copy()
            display_df.rename(columns={'Size': 'Item / Part Name'}, inplace=True)
            st.dataframe(display_df, use_container_width=True)
            
            # PDF Download option for this specific search
            if st.button("📄 Download Search Result PDF"):
                pdf_buffer = create_part_search_pdf(search_party_name, search_part_name, filtered_df)
                file_name = f"PriceSearch_{search_party_name}_{search_part_name}.pdf".replace(" ", "_")
                st.download_button("📥 Click Here to Download PDF", data=pdf_buffer, file_name=file_name, mime="application/pdf")

# ==========================================
# 4. MASTER SETTINGS PAGE
# ==========================================
elif menu == "⚙️ Master Settings":
    st.title("Master Settings 🔒")
    pwd_input = st.text_input("Enter Master Password:", type="password")
    
    if pwd_input != settings.get('password', '1234'):
        if pwd_input: st.error("❌ Incorrect Password!")
        st.stop()
        
    st.success("Access Granted!")
    tab1, tab2, tab3 = st.tabs(["Machine Prices", "Add-ons", "Security & T&C"])
    
    with tab1:
        st.subheader("Edit/Remove Sizes")
        prices = settings['prices']
        for size, price in list(prices.items()):
            cA, cB, cC = st.columns([2, 2, 1])
            cA.write(f"**{format_size(size)}**")
            prices[size] = cB.number_input("Price", value=price, step=1000, key=f"p_{size}", label_visibility="collapsed")
            if cC.button("❌ Remove", key=f"d_{size}"):
                del prices[size]; save_settings(settings); st.rerun()
                    
        st.write("---")
        c1, c2, c3 = st.columns(3)
        n_w = c1.text_input("Width (e.g. 24)")
        n_l = c2.text_input("Length (e.g. 48)")
        n_p = c3.number_input("Base Price", value=0, step=1000)
        if st.button("➕ Add New Size"):
            if n_w and n_l and n_p > 0:
                settings['prices'][f"{n_w}x{n_l}"] = n_p
                save_settings(settings); st.rerun()

    with tab2:
        st.subheader("Edit/Remove Add-ons")
        addons = settings['addons']
        for name, price in list(addons.items()):
            if name in ["LowHighExtra", "PressureSwitch"]:
                cA, cB = st.columns([2, 3])
                cA.write(f"**{name}**")
                addons[name] = cB.number_input("Price", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
            else:
                cA, cB, cC = st.columns([2, 2, 1])
                cA.write(f"**{name}**")
                addons[name] = cB.number_input("Price", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
                if cC.button("❌ Remove", key=f"da_{name}"):
                    del addons[name]; save_settings(settings); st.rerun()
                        
        if st.button("💾 Save Add-on Changes", type="primary"): save_settings(settings); st.success("Updated!")
        st.write("---")
        c1, c2 = st.columns(2)
        new_a = c1.text_input("New Add-on Name")
        new_p = c2.number_input("Add-on Price", value=0, step=500)
        if st.button("➕ Add New Option"):
            if new_a and new_p > 0:
                settings['addons'][new_a] = new_p
                save_settings(settings); st.rerun()

    with tab3:
        new_pwd = st.text_input("New Password:", type="password")
        if st.button("Update Password"):
            if new_pwd: settings['password'] = new_pwd; save_settings(settings); st.success("Updated!")
        st.write("---")
        new_tc = st.text_area("T&C text", value=settings.get('tc', ''), height=100)
        if st.button("Update T&C"):
            settings['tc'] = new_tc; save_settings(settings); st.success("Updated!")
