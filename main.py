import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os
from datetime import datetime
import calendar
import pandas as pd
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# --- SET PAGE CONFIG WITH EXISTING LOGO ---
page_icon_path = "logo.png" if os.path.exists("logo.png") else "🏥"
st.set_page_config(page_title="Surgicraft Industries", page_icon=page_icon_path, layout="wide")

# --- PWA / MOBILE FULL SCREEN THEME FIX ---
st.markdown("""
    <meta name="theme-color" content="#0e1117">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
""", unsafe_allow_html=True)

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
        "LowHighExtra": 12000
    },
    "gst_rates": [5, 12, 18, 28],
    "hsn_codes": [],
    "tc": "Surgicraft Internal Price List Record."
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            if "gst_rates" not in data: data["gst_rates"] = [5, 12, 18, 28]
            if "hsn_codes" not in data: data["hsn_codes"] = []
            return data
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

@st.cache_resource
def get_factory_sheet():
    info = json.loads(st.secrets["google_key"])
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(info, scopes=scope)
    client = gspread.authorize(creds)
    db = client.open("Surgicraft_Database")
    try:
        return db.worksheet("Factory_Data")
    except:
        ws = db.add_worksheet(title="Factory_Data", rows="1000", cols="10")
        ws.append_row(["Date", "Raw Material", "Part Name", "Cutting Size", "Quantity"])
        return ws

# Fetch data early
try:
    sheet = get_sheet()
    all_sheet_data = sheet.get_all_records()
    main_df = pd.DataFrame(all_sheet_data) if all_sheet_data else pd.DataFrame()
    
    unique_parties_list = sorted(main_df['Party'].astype(str).str.strip().str.title().unique().tolist()) if not main_df.empty else []
    unique_parts_list = sorted(main_df[main_df['Speed'] == 'Spare Part']['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    all_items_list = sorted(main_df['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    
    factory_sheet = get_factory_sheet()
    all_factory_data = factory_sheet.get_all_records()
    factory_df = pd.DataFrame(all_factory_data) if all_factory_data else pd.DataFrame()
    
    unique_materials = sorted(factory_df['Raw Material'].astype(str).str.strip().unique().tolist()) if not factory_df.empty else []
    unique_materials = [x for x in unique_materials if x and x != 'nan']
    
    unique_factory_parts = sorted(factory_df['Part Name'].astype(str).str.strip().unique().tolist()) if not factory_df.empty else []
    unique_factory_parts = [x for x in unique_factory_parts if x and x != 'nan']
    
except Exception as e:
    st.error(f"Google Sheet Connection Error! Error: {e}")
    st.stop()

# --- HELPER FORMAT FUNCTIONS ---
def format_size(size_str):
    if "x" in size_str:
        parts = size_str.split('x')
        if len(parts) == 2 and parts[0].strip().isdigit():
            return f'{parts[0].strip()}" x {parts[1].strip()}"'
    return size_str

def format_size_for_ui(size_str):
    if size_str in ["-- All Items --", "-- New Part --"]:
        return size_str
    return format_size(str(size_str))

def get_spare_details(row_options, total_price):
    basic, gst, hsn = 0, 0, "None"
    try:
        opts = json.loads(str(row_options))
        if isinstance(opts, dict):
            if 'Basic' in opts: basic = int(opts['Basic'])
            if 'GST' in opts: gst = int(opts['GST'])
            if 'HSN' in opts: hsn = str(opts['HSN'])
    except: pass
    if basic == 0 and gst == 0: 
        try: basic = int(float(total_price))
        except: basic = 0
    return basic, gst, hsn

# --- DATA PROCESSOR FOR DISPLAY TABLES ---
def prepare_display_df(df):
    basics, gsts, hsns = [], [], []
    for idx, row in df.iterrows():
        if str(row['Speed']) == 'Spare Part':
            b, g, h = get_spare_details(row.get('Options', '{}'), row.get('Total_Price', 0))
            basics.append(b)
            gsts.append(f"{g}%" if g > 0 else "-")
            hsns.append(h if h and h != "None" else "-")
        else:
            basics.append("-"); gsts.append("-"); hsns.append("-")
            
    df['HSN Code'] = hsns
    df['Basic Price'] = basics
    df['GST'] = gsts
    df['Size'] = df['Size'].apply(format_size)
    return df[['Date', 'Party', 'Size', 'HSN Code', 'Basic Price', 'GST', 'Total_Price']]

# --- UNIVERSAL PDF PREVIEW ---
def display_pdf_in_app(pdf_buffer):
    base64_pdf = base64.b64encode(pdf_buffer.getvalue()).decode('utf-8')
    pdf_display = f'''
        <iframe src="data:application/pdf;base64,{base64_pdf}" 
        width="100%" height="450" type="application/pdf"
        style="border: 2px solid #ccc; border-radius: 8px; background-color: white;">
        </iframe>
    '''
    st.markdown("### 📄 PDF Preview")
    st.warning("📱 **Android Users:** Jo ahiya PDF empty (safed dabbo) dekhay, to upar thi **'Download PDF'** button dabavi ne open karo.")
    st.markdown(pdf_display, unsafe_allow_html=True)

# --- HEADER WITH LOGO & RED TEXT ---
def display_header():
    col1, col2 = st.columns([1, 15])
    with col1:
        if os.path.exists("logo.png"):
            st.image("logo.png", width=60)
    with col2:
        st.markdown("<h1 style='margin-bottom: 0px; padding-bottom: 0px; color: #FF0000;'>Surgicraft Industries</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #00b300; font-weight: bold; margin-top: 0px;'>Created by Ankit Mistry</p>", unsafe_allow_html=True)
    st.write("---")

# --- PDF GENERATOR (History) ---
def create_history_pdf(party, records_df, period_str="Lifetime"):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14); c.drawString(40, 800, f"Surgicraft Price List Record ({period_str})")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 775, f"Party Name: {party}")
    c.drawString(400, 775, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 740; c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Date"); c.drawString(110, y, "Description / Details"); c.drawString(460, y, "Final Amt(Rs)")
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
            basic, gst, hsn = get_spare_details(row.get('Options', '{}'), total_price)
            hsn_txt = f" | HSN: {hsn}" if hsn and hsn != "None" else ""
            gst_txt = f" (Basic: {basic}{hsn_txt} | GST: {gst}%)" if gst > 0 else f" (Basic: {basic}{hsn_txt})"
            part_display = f"Part: {size_str}{gst_txt}"
            if len(part_display) > 70: part_display = part_display[:67] + "..."
            
            c.drawString(110, y, part_display)
            c.drawString(460, y, f"{total_price:,.2f}")
            grand_total += total_price; y -= 20
        else:
            base_price = int(settings['prices'].get(str(row['Size']), 0))
            c.drawString(110, y, f"Machine: {size_str}")
            if base_price > 0: c.drawString(460, y, f"{base_price:,.2f}")
            else: c.drawString(460, y, f"{total_price:,.2f}")
            y -= 16
            
            c.setFont("Helvetica-Oblique", 10)
            c.drawString(120, y, f"• Speed: {speed_str}")
            y -= 16
            
            raw_addons = row.get('Options', '{}')
            addons_dict = {}
            if isinstance(raw_addons, str):
                try: addons_dict = json.loads(raw_addons)
                except: addons_dict = {raw_addons: 0}
            elif isinstance(raw_addons, dict): addons_dict = raw_addons

            for name, price in addons_dict.items():
                p_val = int(price) if price else 0
                c.drawString(120, y, f"• {name}")
                if p_val > 0: c.drawString(460, y, f"{p_val:,.2f}")
                y -= 16
                
            c.setFont("Helvetica-Bold", 10)
            c.drawString(120, y, "Total Price:")
            c.drawString(460, y, f"{total_price:,.2f}")
            grand_total += total_price; y -= 25
        
        if y < 80:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Date"); c.drawString(110, y, "Description / Details"); c.drawString(460, y, "Final Amt(Rs)")
            c.line(40, y-5, 550, y-5); y -= 25
        
    c.line(40, y-5, 550, y-5)
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y-25, f"{period_str.upper()} TOTAL VALUE: Rs. {grand_total:,.2f}/-")
    c.save(); buffer.seek(0)
    return buffer

# --- PDF GENERATOR (Search) ---
def create_part_search_pdf(party_name, part_name, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Surgicraft Item / Part Price Report")
    c.setFont("Helvetica", 11)
    c.drawString(40, 780, f"Party: {party_name if party_name and party_name != '-- All Parties --' else 'All Parties'}")
    c.drawString(40, 765, f"Item/Part: {format_size(part_name) if part_name and part_name != '-- All Items --' else 'All Items'}")
    c.drawString(400, 780, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 730; c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Date"); c.drawString(110, y, "Party Name")
    c.drawString(230, y, "Item / Machine Details"); c.drawString(470, y, "Final Amt(Rs)")
    c.line(40, y-5, 550, y-5); y -= 25; c.setFont("Helvetica", 10)
    
    for index, row in df.iterrows():
        date_str = str(row['Date'])
        party_str = str(row['Party'])[:20]
        size_str = format_size(str(row['Size']))
        speed_str = str(row.get('Speed', ''))
        total_price = int(row['Total_Price']) if pd.notna(row['Total_Price']) else 0

        c.setFont("Helvetica-Bold", 10)
        c.drawString(40, y, date_str); c.drawString(110, y, party_str)

        if speed_str == "Spare Part":
            basic, gst, hsn = get_spare_details(row.get('Options', '{}'), total_price)
            hsn_txt = f" | HSN: {hsn}" if hsn and hsn != "None" else ""
            gst_txt = f" (Basic: {basic}{hsn_txt} | GST: {gst}%)" if gst > 0 else f" (Basic: {basic}{hsn_txt})"
            part_display = f"Part: {size_str}{gst_txt}"
            if len(part_display) > 50: part_display = part_display[:47] + "..."
            c.drawString(230, y, part_display); c.drawString(470, y, f"{total_price:,.2f}")
            y -= 20
        else:
            base_price = int(settings['prices'].get(str(row['Size']), 0))
            c.drawString(230, y, f"Machine: {size_str}")
            if base_price > 0: c.drawString(470, y, f"{base_price:,.2f}")
            else: c.drawString(470, y, f"{total_price:,.2f}")
            y -= 16

            c.setFont("Helvetica-Oblique", 10)
            c.drawString(240, y, f"• Speed: {speed_str}"); y -= 16

            raw_addons = row.get('Options', '{}')
            addons_dict = {}
            if isinstance(raw_addons, str):
                try: addons_dict = json.loads(raw_addons)
                except: addons_dict = {raw_addons: 0}
            elif isinstance(raw_addons, dict): addons_dict = raw_addons

            for name, price in addons_dict.items():
                p_val = int(price) if price else 0
                c.drawString(240, y, f"• {name}")
                if p_val > 0: c.drawString(470, y, f"{p_val:,.2f}")
                y -= 16

            c.setFont("Helvetica-Bold", 10)
            c.drawString(240, y, "Total Price:"); c.drawString(470, y, f"{total_price:,.2f}")
            y -= 25
        
        if y < 80:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 11)
            c.drawString(40, y, "Date"); c.drawString(110, y, "Party Name")
            c.drawString(230, y, "Item / Machine Details"); c.drawString(470, y, "Final Amt(Rs)")
            c.line(40, y-5, 550, y-5); y -= 25; c.setFont("Helvetica", 10)
            
    c.save(); buffer.seek(0)
    return buffer

# --- FACTORY PDF GENERATOR (EXCEL GRID STYLE) ---
def create_factory_pdf(raw_material, search_part, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    
    # Header
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Surgicraft Factory Production & Cutting List")
    c.setFont("Helvetica", 10)
    if raw_material and raw_material != "-- All Materials --":
        c.drawString(40, 780, f"Material Filter: {raw_material}")
    else:
        c.drawString(40, 780, "Material Filter: All")
        
    if search_part and search_part != "-- All Parts --":
        c.drawString(220, 780, f"Part Filter: {search_part}")
    else:
        c.drawString(220, 780, f"Part Filter: All")
        
    c.drawString(420, 780, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    # Table Header (Excel style)
    y = 740
    c.setFont("Helvetica-Bold", 10)
    c.drawString(45, y+5, "Date")
    c.drawString(105, y+5, "Raw Material")
    c.drawString(235, y+5, "Part Name")
    c.drawString(405, y+5, "Cutting Size")
    c.drawString(505, y+5, "Qty")
    
    def draw_grid_lines(y_top, y_bot):
        c.line(40, y_top, 550, y_top) 
        c.line(40, y_bot, 550, y_bot) 
        c.line(40, y_top, 40, y_bot)
        c.line(100, y_top, 100, y_bot)
        c.line(230, y_top, 230, y_bot)
        c.line(400, y_top, 400, y_bot)
        c.line(500, y_top, 500, y_bot)
        c.line(550, y_top, 550, y_bot)

    draw_grid_lines(y+20, y)
    
    row_h = 25
    for index, row in df.iterrows():
        y -= row_h
        if y < 50:
            c.showPage()
            y = 800
            c.setFont("Helvetica-Bold", 10)
            c.drawString(45, y+5, "Date"); c.drawString(105, y+5, "Raw Material"); c.drawString(235, y+5, "Part Name")
            c.drawString(405, y+5, "Cutting Size"); c.drawString(505, y+5, "Qty")
            draw_grid_lines(y+20, y)
            y -= row_h
            
        c.setFont("Helvetica", 10)
        c.drawString(45, y+7, str(row['Date'])[:10])
        
        raw_mat = str(row['Raw Material'])
        if len(raw_mat) > 20: raw_mat = raw_mat[:18] + ".."
        c.drawString(105, y+7, raw_mat)
        
        part_name = str(row['Part Name'])
        if len(part_name) > 28: part_name = part_name[:26] + ".."
        c.drawString(235, y+7, part_name)
        
        # Mota Akshar for Cutting Size
        c.setFont("Helvetica-Bold", 12)
        c.drawString(405, y+7, str(row['Cutting Size']))
        
        c.setFont("Helvetica-Bold", 11)
        c.drawString(505, y+7, str(row['Quantity']))
        
        draw_grid_lines(y+row_h, y)
        
    c.save()
    buffer.seek(0)
    return buffer

# --- SIDEBAR MENU ---
st.sidebar.title("🏥 Surgicraft Menu")
menu = st.sidebar.radio("Go to:", ["➕ Add New Entry", "📜 Party History & Edit", "🔍 Part Price Finder", "✂️ Factory Parts & Cutting", "⚙️ Master Settings"])

# ==========================================
# 1. ADD NEW ENTRY PAGE
# ==========================================
if menu == "➕ Add New Entry":
    display_header()
    
    party_sel = st.selectbox("Select Party (Type to search):", ["-- New Party --"] + unique_parties_list, index=0)
    if party_sel == "-- New Party --":
        party_name = st.text_input("Enter New Party Name:")
    else:
        party_name = party_sel
        
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
            if addon_name in ["LowHighExtra"]: continue
            if cols[col_idx % 3].checkbox(addon_name):
                selected_addons.append(addon_name)
                addons_prices_struct[addon_name] = settings['addons'].get(addon_name, 0)
            col_idx += 1

        base_machine_price = int(settings['prices'].get(size, 0))
        
        if base_machine_price == 0:
            st.error(f"Base price not found for size {size}. Please add it in Master Settings.")
        else:
            final_total_price = base_machine_price + sum(addons_prices_struct.values())
            st.success(f"**Final Machine Price: Rs. {final_total_price:,.2f}/-**")

            if st.button("➕ SAVE ENTRY TO SHEET", type="primary"):
                if not party_name: st.warning("Please enter/select Party Name first!")
                else:
                    dt = datetime.now().strftime("%d-%m-%Y")
                    sheet.append_row([st.session_state.q_no, party_name, dt, size, speed, json.dumps(addons_prices_struct), final_total_price])
                    st.toast(f"{format_size(size)} Machine Saved for {party_name}! ✅")
                    st.cache_resource.clear()
                    st.rerun()

    else:
        st.write("### Add Spare Part Details")
        c1, c2 = st.columns(2)
        with c1:
            part_sel = st.selectbox("Select Part (Type to search):", ["-- New Part --"] + unique_parts_list, index=0, format_func=format_size_for_ui)
            if part_sel == "-- New Part --": part_name = st.text_input("Enter New Part Name / Description:")
            else: part_name = part_sel
                
        with c2:
            st.write(" ") 
            basic_price = st.number_input("Basic Price (Rs)", min_value=0, step=100)
            
        c3, c4, c5 = st.columns([2, 2, 2])
        with c3:
            hsn_opts = ["None"] + sorted(settings.get("hsn_codes", []))
            hsn_val = st.selectbox("HSN Code", hsn_opts)
        with c4:
            gst_options = [0] + sorted(settings.get("gst_rates", [5, 12, 18, 28]))
            gst_rate = st.selectbox("GST (%)", gst_options, format_func=lambda x: f"{x}%" if x > 0 else "None (0%)")
        with c5:
            st.write(" ") 
            final_calc_price = basic_price + (basic_price * gst_rate / 100)
            st.info(f"**Final Price: Rs. {final_calc_price:,.2f}**")
        
        if st.button("➕ SAVE PART TO SHEET", type="primary"):
            if not party_name: st.warning("Please enter Party Name first!")
            elif not part_name or final_calc_price <= 0: st.warning("Please enter Part Name and Price!")
            else:
                dt = datetime.now().strftime("%d-%m-%Y")
                options_json = json.dumps({"Basic": basic_price, "GST": gst_rate, "HSN": hsn_val})
                sheet.append_row([st.session_state.q_no, party_name, dt, part_name, "Spare Part", options_json, final_calc_price])
                st.toast(f"{format_size(part_name)} Saved for {party_name}! ✅")
                st.cache_resource.clear()
                st.rerun()

# ==========================================
# 2. PARTY HISTORY & EDIT PAGE 
# ==========================================
elif menu == "📜 Party History & Edit":
    display_header()
    if main_df.empty: st.info("No records found in Google Sheet.")
    else:
        df = main_df.copy()
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        tab1, tab2, tab3 = st.tabs(["📜 View/Download PDF", "✏️ Edit Record", "❌ Delete Record"])
        
        with tab1:
            st.write("### Party Wise Record")
            pdf_party = st.selectbox("Select Party (Type to search):", ["-- Select Party --"] + unique_parties_list, key="pdf_party")
            if pdf_party != "-- Select Party --":
                party_df = df[df['Clean_Party'] == pdf_party].copy()
                display_party_df = prepare_display_df(party_df)
                st.dataframe(display_party_df.rename(columns={'Item/Machine':'Item/Part Name', 'Total_Price':'Final Price (Rs)'}), use_container_width=True)
                st.write("---")
                hist_pdf = create_history_pdf(pdf_party, party_df, "Lifetime Record")
                c1, c2 = st.columns(2)
                with c1: st.download_button("📥 Download PDF", data=hist_pdf, file_name=f"{pdf_party}_Record.pdf", mime="application/pdf", use_container_width=True)
                with c2: 
                    if st.button("👁️ View Preview", use_container_width=True): display_pdf_in_app(hist_pdf)

        with tab2:
            st.write("### Edit Existing Record (By Party)")
            edit_party = st.selectbox("1. Select Party:", ["-- Select Party --"] + unique_parties_list, key="edit_party")
            if edit_party != "-- Select Party --":
                party_items = df[df['Clean_Party'] == edit_party].copy()
                party_items['Display'] = party_items['Date'].astype(str) + " | " + party_items['Size'].apply(format_size) + " | Rs. " + party_items['Total_Price'].astype(str)
                selected_display = st.selectbox("2. Select Specific Item to Edit:", party_items['Display'].tolist())
                
                if selected_display:
                    row_data = party_items[party_items['Display'] == selected_display].iloc[0]
                    is_spare = (str(row_data['Speed']) == 'Spare Part')
                    st.write("---")
                    new_item = st.text_input("Edit Item/Machine Name:", value=row_data['Size'])
                    
                    if is_spare:
                        old_basic, old_gst, old_hsn = get_spare_details(row_data.get('Options', '{}'), row_data['Total_Price'])
                        new_basic = st.number_input("Edit Basic Price (Rs):", value=old_basic, step=100)
                        c1, c2 = st.columns(2)
                        with c1:
                            hsn_opts = ["None"] + sorted(settings.get("hsn_codes", []))
                            if old_hsn and old_hsn not in hsn_opts: hsn_opts.append(old_hsn); hsn_opts.sort()
                            new_hsn = st.selectbox("Edit HSN Code:", hsn_opts, index=hsn_opts.index(old_hsn) if old_hsn in hsn_opts else 0)
                        with c2:
                            gst_opts = [0] + sorted(settings.get("gst_rates", [5, 12, 18, 28]))
                            if old_gst not in gst_opts: gst_opts.append(old_gst); gst_opts.sort()
                            new_gst = st.selectbox("Edit GST (%):", gst_opts, index=gst_opts.index(old_gst), format_func=lambda x: f"{x}%" if x > 0 else "None (0%)")
                        new_price = new_basic + (new_basic * new_gst / 100)
                        st.info(f"**New Final Price: Rs. {new_price:,.2f}**")
                    else:
                        new_price = st.number_input("Edit Total Price (Rs):", value=int(float(row_data['Total_Price'])), step=100)
                    
                    if st.button("💾 Update Record in Sheet", type="primary"):
                        all_values = sheet.get_all_values()
                        row_index_to_update = -1
                        for i, row_vals in enumerate(all_values):
                            if i == 0: continue
                            # SMART MATCHING
                            if (row_vals[1].strip().title() == edit_party and 
                                str(row_vals[2]).strip() == str(row_data['Date']).strip() and 
                                str(row_vals[3]).strip() == str(row_data['Size']).strip()):
                                row_index_to_update = i + 1 
                                break
                                
                        if row_index_to_update != -1:
                            sheet.update_cell(row_index_to_update, 4, new_item)
                            sheet.update_cell(row_index_to_update, 7, new_price)
                            if is_spare: sheet.update_cell(row_index_to_update, 6, json.dumps({"Basic": new_basic, "GST": new_gst, "HSN": new_hsn}))
                            st.success("Record Updated Successfully!")
                            st.cache_resource.clear()
                            st.rerun()
                        else: st.error("Row not found in Database.")

        with tab3:
            st.write("### Delete Record (By Party)")
            del_party = st.selectbox("1. Select Party:", ["-- Select Party --"] + unique_parties_list, key="del_party")
            if del_party != "-- Select Party --":
                del_items = df[df['Clean_Party'] == del_party].copy()
                del_items['Display'] = del_items['Date'].astype(str) + " | " + del_items['Size'].apply(format_size) + " | Rs. " + del_items['Total_Price'].astype(str)
                selected_del = st.selectbox("2. Select Item to Delete:", del_items['Display'].tolist())
                
                if selected_del:
                    del_row_data = del_items[del_items['Display'] == selected_del].iloc[0]
                    if st.button("❌ Delete Permanently", type="primary"):
                        all_values = sheet.get_all_values()
                        row_index_to_del = -1
                        for i, row_vals in enumerate(all_values):
                            if i == 0: continue
                            if (row_vals[1].strip().title() == del_party and 
                                str(row_vals[2]).strip() == str(del_row_data['Date']).strip() and 
                                str(row_vals[3]).strip() == str(del_row_data['Size']).strip()):
                                row_index_to_del = i + 1 
                                break
                                
                        if row_index_to_del != -1:
                            sheet.delete_rows(row_index_to_del)
                            st.success("Record Deleted Successfully!")
                            st.cache_resource.clear()
                            st.rerun()
                        else: st.error("Row not found in Database.")

# ==========================================
# 3. PART PRICE FINDER PAGE 
# ==========================================
elif menu == "🔍 Part Price Finder":
    display_header()
    st.write("Party select karo etle automatic ena j parts nu list aavse!")
    if main_df.empty: st.info("No records found in Google Sheet.")
    else:
        df = main_df.copy()
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        c1, c2 = st.columns(2)
        search_party_name = c1.selectbox("1. Select Party:", ["-- All Parties --"] + unique_parties_list, index=0)
        
        if search_party_name != "-- All Parties --":
            party_specific_parts = sorted(df[df['Clean_Party'] == search_party_name]['Size'].astype(str).str.strip().unique().tolist())
            search_part_name = c2.selectbox("2. Select Part / Item:", ["-- All Items --"] + party_specific_parts, index=0, format_func=format_size_for_ui)
        else:
            search_part_name = c2.selectbox("2. Select Part / Item:", ["-- All Items --"] + all_items_list, index=0, format_func=format_size_for_ui)
        
        filtered_df = df.copy()
        if search_party_name != "-- All Parties --": filtered_df = filtered_df[filtered_df['Clean_Party'] == search_party_name]
        if search_part_name != "-- All Items --": filtered_df = filtered_df[filtered_df['Size'].astype(str).str.strip() == search_part_name]
            
        st.write("### Search Results")
        if search_party_name == "-- All Parties --" and search_part_name == "-- All Items --": st.info("Please select a Party or Part Name above to see results.")
        elif filtered_df.empty: st.warning("Aa naam thi koi entry mali nathi.")
        else:
            display_df = prepare_display_df(filtered_df)
            display_df.rename(columns={'Size': 'Item / Part Name', 'Total_Price': 'Final Price (Rs)'}, inplace=True)
            st.dataframe(display_df, use_container_width=True)
            st.write("---")
            pdf_buffer = create_part_search_pdf(search_party_name, search_part_name, filtered_df)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Download PDF", data=pdf_buffer, file_name="PriceSearch_Result.pdf", mime="application/pdf", use_container_width=True)
            with c2: 
                if st.button("👁️ View Preview", use_container_width=True): display_pdf_in_app(pdf_buffer)

# ==========================================
# 5. FACTORY PARTS & CUTTING MANAGER 
# ==========================================
elif menu == "✂️ Factory Parts & Cutting":
    display_header()
    st.write("### Factory Production & Cutting Manager")
    
    tabA, tabB, tabC = st.tabs(["➕ Add Record", "🔍 Search & Report", "✏️ Edit / Delete"])
    
    with tabA:
        st.write("**Record New Cutting Details:**")
        col1, col2 = st.columns(2)
        
        raw_sel = col1.selectbox("1. Raw Material", ["-- New Material --"] + unique_materials)
        if raw_sel == "-- New Material --": raw_val = col1.text_input("Enter New Raw Material (e.g. 32mm 304 Round)")
        else: raw_val = raw_sel
            
        part_sel = col2.selectbox("2. Part Name", ["-- New Part --"] + unique_factory_parts)
        if part_sel == "-- New Part --": part_val = col2.text_input("Enter New Part Name (e.g. Dryer valve Lambi degree)")
        else: part_val = part_sel
            
        col3, col4 = st.columns(2)
        cut_size = col3.text_input("3. Cutting Size (e.g. 130mm or 5\")")
        qty = col4.number_input("4. Quantity (Nang)", min_value=1, step=1)
        
        if st.button("💾 Save Cutting Record", type="primary"):
            if not raw_val or not part_val or not cut_size: st.warning("Please fill Raw Material, Part Name and Cutting Size!")
            else:
                dt_str = datetime.now().strftime("%d-%m-%Y")
                factory_sheet.append_row([dt_str, str(raw_val).strip(), str(part_val).strip(), str(cut_size).strip(), int(qty)])
                st.toast("Cutting Record Saved! ✅")
                st.cache_resource.clear()
                st.rerun()
                
    with tabB:
        st.write("**Search Parts Cut from Raw Material:**")
        
        sc1, sc2 = st.columns(2)
        search_raw = sc1.selectbox("1. Select Raw Material:", ["-- All Materials --"] + unique_materials)
        
        # CHANGED TO SELECTBOX FOR AUTO-COMPLETE AS REQUESTED
        search_part = sc2.selectbox("2. Select Part Name:", ["-- All Parts --"] + unique_factory_parts)
        
        f_df = factory_df.copy()
        if not f_df.empty:
            if search_raw != "-- All Materials --":
                f_df = f_df[f_df['Raw Material'].astype(str).str.strip() == search_raw]
                
            if search_part != "-- All Parts --":
                f_df = f_df[f_df['Part Name'].astype(str).str.strip() == search_part]
                
            st.dataframe(f_df, use_container_width=True)
            total_qty = f_df['Quantity'].sum() if 'Quantity' in f_df.columns else 0
            st.success(f"**Total Quantity (Nang) Found: {total_qty}**")
            
            st.write("---")
            f_pdf_buffer = create_factory_pdf(search_raw, search_part, f_df)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Download PDF (Cutting List)", data=f_pdf_buffer, file_name="Factory_Cutting_List.pdf", mime="application/pdf", use_container_width=True)
            with c2:
                if st.button("👁️ View Preview", use_container_width=True): display_pdf_in_app(f_pdf_buffer)
                
        else: st.info("No cutting records found yet.")
            
    with tabC:
        st.write("**Edit or Delete Factory Records:**")
        if factory_df.empty: st.info("No records to edit.")
        else:
            edit_f_df = factory_df.copy()
            edit_f_df['Display'] = edit_f_df['Date'].astype(str) + " | " + edit_f_df['Raw Material'].astype(str) + " | " + edit_f_df['Part Name'].astype(str) + " | Qty: " + edit_f_df['Quantity'].astype(str)
            sel_rec = st.selectbox("Select Record:", edit_f_df['Display'].tolist())
            
            if sel_rec:
                row_f_data = edit_f_df[edit_f_df['Display'] == sel_rec].iloc[0]
                st.write("---")
                e_col1, e_col2 = st.columns(2)
                new_f_raw = e_col1.text_input("Edit Raw Material:", value=str(row_f_data['Raw Material']))
                new_f_part = e_col2.text_input("Edit Part Name:", value=str(row_f_data['Part Name']))
                e_col3, e_col4 = st.columns(2)
                new_f_cut = e_col3.text_input("Edit Cutting Size:", value=str(row_f_data['Cutting Size']))
                new_f_qty = e_col4.number_input("Edit Quantity:", value=int(row_f_data['Quantity']), min_value=1)
                
                c_btn1, c_btn2 = st.columns(2)
                if c_btn1.button("💾 Update Record", type="primary"):
                    all_f_vals = factory_sheet.get_all_values()
                    row_idx_f = -1
                    for i, r_vals in enumerate(all_f_vals):
                        if i == 0: continue
                        if (r_vals[0] == str(row_f_data['Date']) and r_vals[1] == str(row_f_data['Raw Material']) and 
                            r_vals[2] == str(row_f_data['Part Name']) and str(r_vals[3]) == str(row_f_data['Cutting Size'])):
                            row_idx_f = i + 1; break
                            
                    if row_idx_f != -1:
                        factory_sheet.update(f"B{row_idx_f}:E{row_idx_f}", [[new_f_raw, new_f_part, new_f_cut, new_f_qty]])
                        st.success("Record Updated!")
                        st.cache_resource.clear()
                        st.rerun()
                    else: st.error("Row not found for update.")
                        
                if c_btn2.button("❌ Delete Record"):
                    all_f_vals = factory_sheet.get_all_values()
                    row_idx_f = -1
                    for i, r_vals in enumerate(all_f_vals):
                        if i == 0: continue
                        if (r_vals[0] == str(row_f_data['Date']) and r_vals[1] == str(row_f_data['Raw Material']) and 
                            r_vals[2] == str(row_f_data['Part Name']) and str(r_vals[3]) == str(row_f_data['Cutting Size'])):
                            row_idx_f = i + 1; break
                            
                    if row_idx_f != -1:
                        factory_sheet.delete_rows(row_idx_f)
                        st.success("Record Deleted!")
                        st.cache_resource.clear()
                        st.rerun()
                    else: st.error("Row not found for deletion.")

# ==========================================
# 4. MASTER SETTINGS PAGE
# ==========================================
elif menu == "⚙️ Master Settings":
    display_header()
    st.title("Master Settings 🔒")
    pwd_input = st.text_input("Enter Master Password:", type="password")
    
    if pwd_input != settings.get('password', '1234'):
        if pwd_input: st.error("❌ Incorrect Password!")
        st.stop()
        
    st.success("Access Granted!")
    tab1, tab2, tab3, tab4 = st.tabs(["Machine Prices", "Add-ons", "GST % Options", "HSN Codes"])
    
    with tab1:
        st.subheader("Edit/Remove Sizes")
        prices = settings['prices']
        for size, price in list(prices.items()):
            cA, cB, cC = st.columns([2, 2, 1])
            cA.write(f"**{format_size(size)}**")
            prices[size] = cB.number_input("Price", value=price, step=1000, key=f"p_{size}", label_visibility="collapsed")
            if cC.button("❌ Remove", key=f"d_{size}"): del prices[size]; save_settings(settings); st.rerun()
                    
        st.write("---")
        c1, c2, c3 = st.columns(3)
        n_w = c1.text_input("Width (e.g. 24)")
        n_l = c2.text_input("Length (e.g. 48)")
        n_p = c3.number_input("Base Price", value=0, step=1000)
        if st.button("➕ Add New Size"):
            if n_w and n_l and n_p > 0: settings['prices'][f"{n_w}x{n_l}"] = n_p; save_settings(settings); st.rerun()

    with tab2:
        st.subheader("Edit/Remove Add-ons")
        addons = settings['addons']
        for name, price in list(addons.items()):
            if name in ["LowHighExtra"]:
                cA, cB = st.columns([2, 3])
                cA.write(f"**{name}**")
                addons[name] = cB.number_input("Price", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
            else:
                cA, cB, cC = st.columns([2, 2, 1])
                cA.write(f"**{name}**")
                addons[name] = cB.number_input("Price", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
                if cC.button("❌ Remove", key=f"da_{name}"): del addons[name]; save_settings(settings); st.rerun()
                        
        if st.button("💾 Save Add-on Changes", type="primary"): save_settings(settings); st.success("Updated!")
        st.write("---")
        c1, c2 = st.columns(2)
        new_a = c1.text_input("New Add-on Name")
        new_p = c2.number_input("Add-on Price", value=0, step=500)
        if st.button("➕ Add New Option"):
            if new_a and new_p > 0: settings['addons'][new_a] = new_p; save_settings(settings); st.rerun()
                
    with tab3:
        st.subheader("Manage GST Percentages (%)")
        gst_rates = settings.get("gst_rates", [5, 12, 18, 28])
        for g in list(gst_rates):
            cA, cB = st.columns([3, 1])
            cA.write(f"**{g}%** GST")
            if cB.button("❌ Remove", key=f"dgst_{g}"): gst_rates.remove(g); settings["gst_rates"] = gst_rates; save_settings(settings); st.rerun()
        st.write("---")
        n_gst = st.number_input("Add New GST Rate (%)", min_value=1, max_value=100, step=1)
        if st.button("➕ Add New GST %"):
            if n_gst not in gst_rates: gst_rates.append(n_gst); gst_rates.sort(); settings["gst_rates"] = gst_rates; save_settings(settings); st.rerun()
            else: st.warning("Aa percentage pahelathi j che.")

    with tab4:
        st.subheader("Manage HSN Codes")
        hsn_codes = settings.get("hsn_codes", [])
        for h in list(hsn_codes):
            cA, cB = st.columns([3, 1])
            cA.write(f"**{h}**")
            if cB.button("❌ Remove", key=f"dhsn_{h}"): hsn_codes.remove(h); settings["hsn_codes"] = hsn_codes; save_settings(settings); st.rerun()
        st.write("---")
        n_hsn = st.text_input("Add New HSN Code")
        if st.button("➕ Add New HSN"):
            if n_hsn and n_hsn not in hsn_codes: hsn_codes.append(n_hsn); hsn_codes.sort(); settings["hsn_codes"] = hsn_codes; save_settings(settings); st.rerun()
            elif n_hsn in hsn_codes: st.warning("Aa HSN Code pahelathi j che.")
