import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import json
import os
import math
from datetime import datetime
import pandas as pd
import io
import base64
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

# --- SET PAGE CONFIG ---
page_icon_path = "logo.png" if os.path.exists("logo.png") else "🏥"
st.set_page_config(page_title="Surgicraft Industries", page_icon=page_icon_path, layout="wide")

# --- PWA / APPLE iOS LOGO FIX ---
st.markdown("""
    <link rel="apple-touch-icon" href="logo.png">
    <link rel="icon" type="image/png" href="logo.png">
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
    "hsn_codes": []
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

if 'q_no' not in st.session_state: st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_sheets():
    try:
        info = json.loads(st.secrets["google_key"])
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(info, scopes=scope)
        client = gspread.authorize(creds)
        db = client.open("Surgicraft_Database")
        
        try: sheet_main = db.worksheet("Sheet1")
        except: sheet_main = db.sheet1
        
        try: sheet_factory = db.worksheet("Factory_Data")
        except: 
            sheet_factory = db.add_worksheet(title="Factory_Data", rows="1000", cols="10")
            sheet_factory.append_row(["Date", "Raw Material", "Part Name", "Cutting Size", "Quantity"])
            
        try: sheet_stock = db.worksheet("Master_Stock")
        except:
            sheet_stock = db.add_worksheet(title="Master_Stock", rows="1000", cols="10")
            sheet_stock.append_row(["Date", "Material Name", "Total Length (Foot)", "Total Length (MM)", "Weight (KG)"])
            
        try: sheet_hexo = db.worksheet("Hexo_Cutting")
        except:
            sheet_hexo = db.add_worksheet(title="Hexo_Cutting", rows="1000", cols="10")
            sheet_hexo.append_row(["Date", "Material Name", "Cut Size", "Quantity", "Blade Margin (MM)", "Total Used (MM)"])
            
        return sheet_main, sheet_factory, sheet_stock, sheet_hexo
    except Exception as e:
        st.error(f"Google Sheet Connection Error: {e}")
        st.stop()

try:
    sheet_main, sheet_factory, sheet_stock, sheet_hexo = get_sheets()
    
    main_df = pd.DataFrame(sheet_main.get_all_records()) if sheet_main.get_all_records() else pd.DataFrame()
    unique_parties_list = sorted(main_df['Party'].astype(str).str.strip().str.title().unique().tolist()) if not main_df.empty else []
    unique_parts_list = sorted(main_df[main_df['Speed'] == 'Spare Part']['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    all_items_list = sorted(main_df['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    
    factory_df = pd.DataFrame(sheet_factory.get_all_records()) if sheet_factory.get_all_records() else pd.DataFrame()
    unique_materials = sorted(factory_df['Raw Material'].astype(str).str.strip().unique().tolist()) if not factory_df.empty else []
    unique_materials = [x for x in unique_materials if x and x != 'nan']
    unique_factory_parts = sorted(factory_df['Part Name'].astype(str).str.strip().unique().tolist()) if not factory_df.empty else []
    unique_factory_parts = [x for x in unique_factory_parts if x and x != 'nan']
    
    stock_df = pd.DataFrame(sheet_stock.get_all_records()) if sheet_stock.get_all_records() else pd.DataFrame()
    hexo_df = pd.DataFrame(sheet_hexo.get_all_records()) if sheet_hexo.get_all_records() else pd.DataFrame()
    
    stock_materials_full = sorted(stock_df['Material Name'].astype(str).str.strip().unique().tolist()) if not stock_df.empty else []
except Exception as e:
    st.error(f"Error reading data: {e}")
    st.stop()

# --- HELPER FORMAT FUNCTIONS ---
def format_size(size_str):
    if "x" in size_str:
        parts = size_str.split('x')
        if len(parts) == 2 and parts[0].strip().isdigit(): return f'{parts[0].strip()}" x {parts[1].strip()}"'
    return size_str

def format_size_for_ui(size_str):
    if size_str in ["-- All Items --", "-- New Part --"]: return size_str
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

# --- BUG FIX: Process DataFrame for OLD vs NEW Price without dropping columns ---
def prepare_display_df_with_history(df):
    df = df.copy() # Copy to prevent warnings
    df['DateObj'] = pd.to_datetime(df['Date'], format="%d-%m-%Y", errors='coerce')
    df = df.sort_values('DateObj') # Sort from oldest to newest

    basics, gsts, hsns = [], [], []
    old_dates, old_prices = [], []
    history_tracker = {}

    for idx, row in df.iterrows():
        item_name = str(row['Size']).strip().lower()
        party_name = str(row['Party']).strip().lower()
        current_price = row.get('Total_Price', 0)
        current_date = str(row['Date'])
        
        tracking_key = f"{party_name}_{item_name}"
        
        if tracking_key in history_tracker:
            old_dates.append(history_tracker[tracking_key]['date'])
            old_prices.append(history_tracker[tracking_key]['price'])
        else:
            old_dates.append("-")
            old_prices.append("-")
            
        history_tracker[tracking_key] = {'date': current_date, 'price': current_price}

        if str(row['Speed']) == 'Spare Part':
            b, g, h = get_spare_details(row.get('Options', '{}'), current_price)
            basics.append(b); gsts.append(f"{g}%" if g > 0 else "-"); hsns.append(h if h and h != "None" else "-")
        else:
            basics.append("-"); gsts.append("-"); hsns.append("-")
            
    # Add new columns to the full dataframe
    df['Old Date'] = old_dates
    df['Old Price'] = old_prices
    df['HSN Code'] = hsns
    df['Basic Price'] = basics
    df['GST'] = gsts
    
    # Sort newest to oldest for display
    df = df.sort_values('DateObj', ascending=False)
    return df

# --- SMART FRACTION PARSER & CONVERTER ---
def parse_smart_size(val_str):
    val_str = str(val_str).replace('"', '').replace('inch', '').replace('mm', '').strip()
    try:
        if " " in val_str and "/" in val_str:
            parts = val_str.split(" ")
            return float(parts[0]) + (float(parts[1].split('/')[0]) / float(parts[1].split('/')[1]))
        elif "-" in val_str and "/" in val_str:
            parts = val_str.split("-")
            return float(parts[0]) + (float(parts[1].split('/')[0]) / float(parts[1].split('/')[1]))
        elif "/" in val_str:
            return float(val_str.split('/')[0]) / float(val_str.split('/')[1])
        else:
            return float(val_str)
    except:
        return -1.0

def convert_to_mm(val, unit):
    if unit == "Foot": return val * 304.8
    elif unit == "Inch": return val * 25.4
    else: return val

def mm_to_foot_inch(mm_val):
    total_inches = mm_val / 25.4
    feet = int(total_inches // 12)
    inches = total_inches % 12
    return f"{feet} Foot {inches:.1f} Inch"

# --- PDF GENERATORS ---
def display_pdf_in_app(pdf_buffer):
    base64_pdf = base64.b64encode(pdf_buffer.getvalue()).decode('utf-8')
    pdf_display = f'''<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="450" type="application/pdf" style="border: 2px solid #ccc; border-radius: 8px;"></iframe>'''
    st.markdown("### 📄 PDF Preview")
    st.markdown(pdf_display, unsafe_allow_html=True)

def draw_grid_lines(c, y_top, y_bot, cols):
    c.setLineWidth(0.5)
    c.line(cols[0], y_top, cols[-1], y_top)
    c.line(cols[0], y_bot, cols[-1], y_bot)
    for col in cols: c.line(col, y_top, col, y_bot)

def create_history_pdf(party, records_df, period_str="Lifetime"):
    buffer = io.BytesIO()
    from reportlab.lib.pagesizes import landscape
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    c.setFont("Helvetica-Bold", 14); c.drawString(40, height - 40, f"Surgicraft Price List Record ({period_str})")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 60, f"Party Name: {party}")
    c.drawString(width - 150, height - 60, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = height - 90; c.setFont("Helvetica-Bold", 10)
    cols = [40, 105, 170, 480, 545, 600, 680, 780]
    c.drawString(cols[0]+5, y+5, "New Date"); c.drawString(cols[1]+5, y+5, "Old Date")
    c.drawString(cols[2]+5, y+5, "Item Description / Details (With Basic/GST)")
    c.drawString(cols[3]+5, y+5, "HSN"); c.drawString(cols[4]+5, y+5, "Old Price")
    c.drawString(cols[5]+5, y+5, "New Final Price")
    
    draw_grid_lines(c, y+20, y-5, [cols[0], cols[1], cols[2], cols[3], cols[5], cols[7]])
    y -= 25; c.setFont("Helvetica", 9); grand_total = 0

    for index, row in records_df.iterrows():
        total_price = int(row['Total_Price']) if pd.notna(row['Total_Price']) else 0
        y_start = y + 15
        
        c.setFont("Helvetica-Bold", 9)
        c.drawString(cols[0]+5, y, str(row['Date']))
        c.drawString(cols[1]+5, y, str(row['Old Date']))
        c.drawString(cols[3]+5, y, str(row['HSN Code'])[:8])
        
        old_price_str = f"{row['Old Price']:,.2f}" if row['Old Price'] != "-" else "-"
        c.drawString(cols[4]+5, y, old_price_str)
        c.drawString(cols[5]+5, y, f"{total_price:,.2f}")
        
        c.setFont("Helvetica", 9)
        if str(row['Speed']) == "Spare Part":
            part_display = f"Part: {format_size(str(row['Size']))} (Basic: Rs.{row['Basic Price']} | GST: {row['GST']})"
            c.drawString(cols[2]+5, y, part_display[:75])
            grand_total += total_price; y -= 20
        else:
            c.drawString(cols[2]+5, y, f"Machine: {format_size(str(row['Size']))} | Speed: {row['Speed']}")
            y -= 15; c.setFont("Helvetica-Oblique", 8)
            addons_dict = {}
            try: addons_dict = json.loads(row.get('Options', '{}'))
            except: pass
            for name, price in addons_dict.items():
                c.drawString(cols[2]+15, y, f"• Add-on: {name}"); y -= 15
            grand_total += total_price; y -= 5
            
        draw_grid_lines(c, y_start, y, [cols[0], cols[1], cols[2], cols[3], cols[5], cols[7]])
        
        if y < 80:
            c.showPage(); y = height - 50; c.setFont("Helvetica-Bold", 10)
            c.drawString(cols[0]+5, y+5, "New Date"); c.drawString(cols[1]+5, y+5, "Old Date")
            c.drawString(cols[2]+5, y+5, "Item Description / Details"); c.drawString(cols[3]+5, y+5, "HSN")
            c.drawString(cols[4]+5, y+5, "Old Price"); c.drawString(cols[5]+5, y+5, "New Final Price")
            draw_grid_lines(c, y+20, y-5, [cols[0], cols[1], cols[2], cols[3], cols[5], cols[7]]); y -= 25
        
    c.setFont("Helvetica-Bold", 12); c.drawString(40, y-25, f"{period_str.upper()} TOTAL VALUE: Rs. {grand_total:,.2f}/-")
    c.save(); buffer.seek(0)
    return buffer

def create_part_search_pdf(party_name, part_name, df):
    buffer = io.BytesIO()
    from reportlab.lib.pagesizes import landscape
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    c.setFont("Helvetica-Bold", 14); c.drawString(40, height-40, "Surgicraft Item / Part Price Report")
    c.setFont("Helvetica", 11); c.drawString(40, height-60, f"Party Filter: {party_name}")
    c.drawString(40, height-75, f"Item Filter: {part_name}"); c.drawString(width-150, height-60, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = height-110; c.setFont("Helvetica-Bold", 10)
    cols = [40, 105, 170, 320, 520, 570, 640, 780]
    c.drawString(cols[0]+5, y+5, "New Date"); c.drawString(cols[1]+5, y+5, "Old Date")
    c.drawString(cols[2]+5, y+5, "Party Name"); c.drawString(cols[3]+5, y+5, "Item Details")
    c.drawString(cols[4]+5, y+5, "HSN"); c.drawString(cols[5]+5, y+5, "Old Price"); c.drawString(cols[6]+5, y+5, "New Price")
    draw_grid_lines(c, y+20, y-5, [cols[0], cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7]]); y -= 25
    
    for index, row in df.iterrows():
        total_price = int(row['Total_Price']) if pd.notna(row['Total_Price']) else 0
        y_start = y + 15
        c.setFont("Helvetica-Bold", 9)
        c.drawString(cols[0]+5, y, str(row['Date'])); c.drawString(cols[1]+5, y, str(row['Old Date']))
        c.drawString(cols[2]+5, y, str(row['Party'])[:22])
        c.drawString(cols[4]+5, y, str(row['HSN Code'])[:8])
        
        old_price_str = f"{row['Old Price']:,.2f}" if row['Old Price'] != "-" else "-"
        c.drawString(cols[5]+5, y, old_price_str)
        c.drawString(cols[6]+5, y, f"{total_price:,.2f}")

        c.setFont("Helvetica", 9)
        if str(row['Speed']) == "Spare Part":
            c.drawString(cols[3]+5, y, f"Part: {format_size(str(row['Size']))}")[:40]
            y -= 20
        else:
            c.drawString(cols[3]+5, y, f"Machine: {format_size(str(row['Size']))}")
            y -= 15; c.setFont("Helvetica-Oblique", 8); c.drawString(cols[3]+15, y, f"• {row['Speed']}"); y -= 15
            
        draw_grid_lines(c, y_start, y, [cols[0], cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7]])
        if y < 80:
            c.showPage(); y = height-50; c.setFont("Helvetica-Bold", 10)
            c.drawString(cols[0]+5, y+5, "New Date"); c.drawString(cols[1]+5, y+5, "Old Date"); c.drawString(cols[2]+5, y+5, "Party Name")
            c.drawString(cols[3]+5, y+5, "Item Details"); c.drawString(cols[4]+5, y+5, "HSN")
            c.drawString(cols[5]+5, y+5, "Old Price"); c.drawString(cols[6]+5, y+5, "New Price")
            draw_grid_lines(c, y+20, y-5, [cols[0], cols[1], cols[2], cols[3], cols[4], cols[5], cols[6], cols[7]]); y -= 25
            
    c.save(); buffer.seek(0); return buffer

def create_factory_pdf(raw_material, search_part, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14); c.drawString(40, 800, "Surgicraft Factory Production & Cutting List")
    c.setFont("Helvetica", 10); c.drawString(40, 780, f"Material Filter: {raw_material}")
    c.drawString(220, 780, f"Part Filter: {search_part}"); c.drawString(420, 780, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = 740; c.setFont("Helvetica-Bold", 10)
    c.drawString(45, y+5, "Date"); c.drawString(105, y+5, "Raw Material"); c.drawString(235, y+5, "Part Name")
    c.drawString(405, y+5, "Cutting Size"); c.drawString(505, y+5, "Qty")
    draw_grid_lines(c, y+20, y, [40, 100, 230, 400, 500, 550])
    
    row_h = 25
    for index, row in df.iterrows():
        y -= row_h
        if y < 50:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 10)
            c.drawString(45, y+5, "Date"); c.drawString(105, y+5, "Raw Material"); c.drawString(235, y+5, "Part Name")
            c.drawString(405, y+5, "Cutting Size"); c.drawString(505, y+5, "Qty")
            draw_grid_lines(c, y+20, y, [40, 100, 230, 400, 500, 550]); y -= row_h
            
        c.setFont("Helvetica", 9)
        c.drawString(45, y+7, str(row['Date'])[:10])
        c.drawString(105, y+7, str(row['Raw Material'])[:18])
        c.drawString(235, y+7, str(row['Part Name'])[:26])
        c.setFont("Helvetica-Bold", 10); c.drawString(405, y+7, str(row['Cutting Size']))
        c.drawString(505, y+7, str(row['Quantity']))
        draw_grid_lines(c, y+row_h, y, [40, 100, 230, 400, 500, 550])
        
    c.save(); buffer.seek(0); return buffer

def create_hexo_pdf(mat_name, mat_in, mat_out, balance_mm, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Surgicraft Godown Balance & Cutting Report")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 775, f"Material: {mat_name}")
    c.drawString(400, 775, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    c.setFont("Helvetica", 10)
    c.drawString(40, 755, f"📥 Total In (Aavyo): {mm_to_foot_inch(mat_in)}")
    c.drawString(40, 740, f"✂️ Total Out (Kapayo): {mm_to_foot_inch(mat_out)}")
    c.setFillColorRGB(0, 0.5, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 720, f"✅ Balance (Padyo che): {mm_to_foot_inch(balance_mm)} ({balance_mm:.1f} MM)")
    c.setFillColorRGB(0, 0, 0)
    
    y = 690; c.setFont("Helvetica-Bold", 10)
    c.drawString(45, y+5, "Date"); c.drawString(105, y+5, "Cut Size"); c.drawString(185, y+5, "Qty")
    c.drawString(225, y+5, "Blade Margin"); c.drawString(315, y+5, "Total Used (MM)")
    draw_grid_lines(c, y+20, y, [40, 100, 180, 220, 310, 450])
    
    row_h = 25; c.setFont("Helvetica", 9)
    for index, row in df.iterrows():
        y -= row_h
        if y < 50:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 10)
            c.drawString(45, y+5, "Date"); c.drawString(105, y+5, "Cut Size"); c.drawString(185, y+5, "Qty")
            c.drawString(225, y+5, "Blade Margin"); c.drawString(315, y+5, "Total Used (MM)")
            draw_grid_lines(c, y+20, y, [40, 100, 180, 220, 310, 450]); y -= row_h
            
        c.drawString(45, y+7, str(row['Date'])[:10])
        c.drawString(105, y+7, str(row['Cut Size']))
        c.drawString(185, y+7, str(row['Quantity']))
        c.drawString(225, y+7, str(row['Blade Margin (MM)']))
        c.setFont("Helvetica-Bold", 10)
        c.drawString(315, y+7, f"{float(row['Total Used (MM)']):.1f}")
        c.setFont("Helvetica", 9)
        draw_grid_lines(c, y+row_h, y, [40, 100, 180, 220, 310, 450])
        
    c.save(); buffer.seek(0)
    return buffer

def display_header():
    col1, col2 = st.columns([1, 15])
    with col1:
        if os.path.exists("logo.png"): st.image("logo.png", width=60)
        else: st.write("🏥")
    with col2: st.markdown("<h1 style='margin-bottom: 0px; padding-bottom: 0px; color: #FF0000;'>Surgicraft Industries</h1>", unsafe_allow_html=True)
    st.markdown("<p style='color: #00b300; font-weight: bold; margin-top: 0px;'>Created by Ankit Mistry</p>", unsafe_allow_html=True)
    st.write("---")

# --- SIDEBAR MENU ---
st.sidebar.title("🏥 Surgicraft Menu")
menu = st.sidebar.radio("Go to:", [
    "🪚 Hexo Cutting (Live Stock)", 
    "✂️ Factory Parts & Cutting",
    "➕ Add New Entry", 
    "📜 Party History & Edit", 
    "🔍 Part Price Finder", 
    "⚙️ Master Settings"
])

# ==========================================
# 1. HEXO CUTTING (LIVE STOCK)
# ==========================================
if menu == "🪚 Hexo Cutting (Live Stock)":
    display_header()
    
    alert_list = []
    if not stock_df.empty:
        for mat in stock_materials_full:
            m_in = stock_df[stock_df['Material Name'] == mat]['Total Length (MM)'].sum()
            m_out = hexo_df[hexo_df['Material Name'] == mat]['Total Used (MM)'].sum() if not hexo_df.empty else 0
            if (m_in - m_out) < 1524: alert_list.append(mat)
    if alert_list: st.error(f"🚨 **ALERT!** Nichena maal no stock 5 Foot thi occho che: **{', '.join(alert_list)}**")

    st.write("### 🪚 Hexo Cutting & Live Balance Dashboard")
    htab1, htab2, htab3, htab4 = st.tabs(["✂️ Cutting Entry", "📥 Navo Maal Aavyo", "📊 Search Godown & PDF", "✏️ Edit / Delete"])
    
    with htab1:
        st.write("**Ankit bhai mate - Cutting Entry & Estimator:**")
        
        c1, c2 = st.columns(2)
        mat_sel = c1.selectbox("1. Material Select Karo:", ["-- Select --", "-- New Material --"] + stock_materials_full)
        if mat_sel == "-- New Material --":
            cut_mat = c1.text_input("📝 Navu Material Lakho (e.g. Hex 22mm 304):")
        else: cut_mat = mat_sel
        
        st.write("**2. Cut Size (e.g., 65, 4 1/8, 4.25):**")
        sc1, sc2 = st.columns(2)
        cut_size_str = sc1.text_input("Size Lakho (Fractions chale che):", value="")
        cut_unit = sc2.selectbox("Ekam (Unit) Select:", ["MM", "Inch", "Foot"])
        
        c3, c4 = st.columns(2)
        cut_qty = c3.number_input("3. Tukda ni Quantity (Nang):", min_value=1, step=1)
        blade_margin = c4.number_input("4. Blade Margin (Wastage) - Edit karo:", value=1.5, step=0.1)
        
        st.write("---")
        st.write("🧠 **Live Ganatri (Estimator):**")
        rod_foot = st.number_input("Standard Ladi (Rod) Lumbai (Foot ma) - Optional:", min_value=0.0, value=0.0, step=1.0)
        
        if cut_size_str and cut_mat and cut_mat != "-- Select --":
            size_val = parse_smart_size(cut_size_str)
            if size_val > 0 and cut_qty > 0:
                size_in_mm = convert_to_mm(size_val, cut_unit)
                total_used_mm = (size_in_mm + blade_margin) * cut_qty
                
                current_in = stock_df[stock_df['Material Name'] == cut_mat]['Total Length (MM)'].sum() if not stock_df.empty else 0
                current_out = hexo_df[hexo_df['Material Name'] == cut_mat]['Total Used (MM)'].sum() if not hexo_df.empty else 0
                current_balance = current_in - current_out
                new_balance = current_balance - total_used_mm
                
                st.info(f"👉 **Kaapva mate jarur:** ({size_in_mm:.1f}mm + {blade_margin}mm) x {cut_qty} = **{mm_to_foot_inch(total_used_mm)}** total maal joise.")
                st.info(f"👉 **Tijori Balance:** Atyare {mm_to_foot_inch(current_balance)} che. Aa kapya pachi **{mm_to_foot_inch(new_balance)}** vadhse.")
                
                if rod_foot > 0:
                    rod_mm = rod_foot * 304.8
                    rods_needed = math.ceil(total_used_mm / rod_mm)
                    wastage = (rods_needed * rod_mm) - total_used_mm
                    st.success(f"📌 **Saliya Ganatri:** Tamare **{rods_needed} aakha saliya** joise. (Chhelle {mm_to_foot_inch(wastage)} no tukdo vadhse).")
                
                if st.button("✂️ Kapi Nakho (Save & Update Stock)", type="primary"):
                    dt_str = datetime.now().strftime("%d-%m-%Y")
                    if mat_sel == "-- New Material --" and cut_mat not in stock_materials_full:
                        sheet_stock.append_row([dt_str, cut_mat.strip(), 0, 0, 0])
                    display_size = f'{cut_size_str} {cut_unit}'
                    sheet_hexo.append_row([dt_str, cut_mat.strip(), display_size, cut_qty, blade_margin, total_used_mm])
                    st.success("Cutting save thai gayu! ✅")
                    st.cache_resource.clear(); st.rerun()
            elif size_val < 0: st.error("Invalid Size! Format check karo (e.g. 65 or 4 1/8)")

    with htab2:
        st.write("**Papa mate - Navo maal aave tyare ahiya nakhvo:**")
        new_mat_name = st.text_input("1. Raw Material Naam (e.g., SS 304 28MM Round):")
        
        st.write("**2. Maap (Lumbai - Fractions chale che):**")
        col_v, col_u, col_k = st.columns(3)
        in_val_str = col_v.text_input("Lumbai Lakho (e.g. 20 ke 20 1/2):", value="")
        in_unit = col_u.selectbox("3. Ekam (Unit):", ["Foot", "Inch", "MM"])
        weight_kg = col_k.number_input("4. Total Vajan (KG) - Optional:", min_value=0.0, step=1.0)
        
        if st.button("💾 Save Navo Maal", type="primary"):
            in_val = parse_smart_size(in_val_str) if in_val_str else 0
            if not new_mat_name or in_val <= 0: st.warning("Material nu naam ane sachi lumbai nakho!")
            else:
                total_mm = convert_to_mm(in_val, in_unit)
                total_foot = total_mm / 304.8
                sheet_stock.append_row([datetime.now().strftime("%d-%m-%Y"), new_mat_name.strip(), total_foot, total_mm, weight_kg])
                st.toast(f"{new_mat_name} aavi gayo! ✅"); st.cache_resource.clear(); st.rerun()

    with htab3:
        st.write("**🔍 Smart Search & Godown PDF:**")
        search_txt = st.text_input("Material nu naam shodhva ahiya lakho (e.g., '32', 'dr', 'patti'):", value="")
        
        if not stock_df.empty:
            filtered_mats = [m for m in stock_materials_full if search_txt.lower() in m.lower()] if search_txt else stock_materials_full
            if not filtered_mats: st.warning("Aa naam no koi maal malyo nathi.")
            
            for mat in filtered_mats:
                mat_in = stock_df[stock_df['Material Name'] == mat]['Total Length (MM)'].sum()
                mat_hexo_df = hexo_df[hexo_df['Material Name'] == mat] if not hexo_df.empty else pd.DataFrame()
                mat_out = mat_hexo_df['Total Used (MM)'].sum() if not mat_hexo_df.empty else 0
                balance_mm = mat_in - mat_out
                
                with st.expander(f"📦 {mat} | Balance: {mm_to_foot_inch(balance_mm)}", expanded=(len(filtered_mats)==1)):
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("Aavyo Hato (Total In)", mm_to_foot_inch(mat_in))
                    sc2.metric("Kapayo (Total Out)", mm_to_foot_inch(mat_out))
                    sc3.metric("Live Balance", mm_to_foot_inch(balance_mm))
                    
                    if not mat_hexo_df.empty:
                        st.write(f"**✂️ {mat} ni Cutting History:**")
                        st.dataframe(mat_hexo_df[['Date', 'Cut Size', 'Quantity', 'Blade Margin (MM)', 'Total Used (MM)']], use_container_width=True, hide_index=True)
                        pdf_buf = create_hexo_pdf(mat, mat_in, mat_out, balance_mm, mat_hexo_df)
                        c_dl, c_pv = st.columns(2)
                        with c_dl: st.download_button("📥 Download PDF", data=pdf_buf, file_name=f"{mat}_Report.pdf", mime="application/pdf", use_container_width=True)
                        with c_pv: 
                            if st.button(f"👁️ View Preview", key=f"pv_{mat}", use_container_width=True): display_pdf_in_app(pdf_buf)

    with htab4:
        st.write("**✏️ Edit ke Delete Karo (Hexo & Stock):**")
        edit_type = st.radio("Shu sudharvu che?", ["✂️ Cutting Entry (Stock Out)", "📥 Stock Entry (Navo Maal)"], horizontal=True)
        
        if edit_type == "✂️ Cutting Entry (Stock Out)":
            if hexo_df.empty:
                st.info("Koi cutting entry nathi.")
            else:
                h_df = hexo_df.copy()
                h_df['Display'] = h_df['Date'].astype(str) + " | " + h_df['Material Name'].astype(str) + " | Size: " + h_df['Cut Size'].astype(str) + " | Qty: " + h_df['Quantity'].astype(str)
                sel_h_rec = st.selectbox("Select Record to Edit (Cutting):", h_df['Display'].tolist())
                
                if sel_h_rec:
                    r_d = h_df[h_df['Display'] == sel_h_rec].iloc[0]
                    e1, e2 = st.columns(2)
                    c_mat_index = stock_materials_full.index(str(r_d['Material Name'])) if str(r_d['Material Name']) in stock_materials_full else 0
                    n_mat = e1.selectbox("Edit Material Name:", stock_materials_full, index=c_mat_index)
                    
                    orig_size = str(r_d['Cut Size'])
                    o_unit = "MM"
                    if "Inch" in orig_size: o_unit = "Inch"
                    elif "Foot" in orig_size: o_unit = "Foot"
                    o_val_str = orig_size.replace('MM', '').replace('Inch', '').replace('Foot', '').strip()
                    
                    st.write("**Cut Size & Unit:**")
                    es1, es2 = st.columns(2)
                    n_cut = es1.text_input("Edit Size:", value=o_val_str)
                    n_unit = es2.selectbox("Edit Unit:", ["MM", "Inch", "Foot"], index=["MM", "Inch", "Foot"].index(o_unit))
                    
                    e3, e4 = st.columns(2)
                    n_qty = e3.number_input("Edit Qty:", value=int(r_d['Quantity']), min_value=1)
                    n_margin = e4.number_input("Edit Margin (MM):", value=float(r_d['Blade Margin (MM)']), step=0.1)
                    
                    b1, b2 = st.columns(2)
                    if b1.button("💾 Update Cutting", type="primary"):
                        n_val = parse_smart_size(n_cut)
                        if n_val > 0:
                            n_mm = convert_to_mm(n_val, n_unit)
                            n_total = (n_mm + n_margin) * n_qty
                            n_disp_size = f"{n_cut} {n_unit}"
                            
                            all_vals = sheet_hexo.get_all_values()
                            for i, r in enumerate(all_vals):
                                if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[2]) == str(r_d['Cut Size']) and str(r[3]) == str(r_d['Quantity']):
                                    sheet_hexo.update(f"B{i+1}:F{i+1}", [[n_mat, n_disp_size, n_qty, n_margin, n_total]])
                                    st.success("Updated Successfully!"); st.cache_resource.clear(); st.rerun(); break
                        else: st.error("Invalid Size format.")
                            
                    if b2.button("❌ Delete Cutting"):
                        all_vals = sheet_hexo.get_all_values()
                        for i, r in enumerate(all_vals):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[2]) == str(r_d['Cut Size']) and str(r[3]) == str(r_d['Quantity']):
                                sheet_hexo.delete_rows(i+1); st.success("Deleted Successfully!"); st.cache_resource.clear(); st.rerun(); break

        else:
            if stock_df.empty:
                st.info("Koi stock entry nathi.")
            else:
                s_df = stock_df.copy()
                s_df['Display'] = s_df['Date'].astype(str) + " | " + s_df['Material Name'].astype(str) + " | Total MM: " + s_df['Total Length (MM)'].astype(str)
                sel_s_rec = st.selectbox("Select Record to Edit (Stock):", s_df['Display'].tolist())
                
                if sel_s_rec:
                    r_d = s_df[s_df['Display'] == sel_s_rec].iloc[0]
                    st.write("---")
                    e1, e2 = st.columns(2)
                    n_mat = e1.text_input("Edit Material Name:", value=str(r_d['Material Name']))
                    n_wt = e2.number_input("Edit Weight (KG):", value=float(r_d.get('Weight (KG)', 0.0)))
                    
                    st.write("**Nevi Lumbai Nakho (Keep blank to keep old):**")
                    es1, es2 = st.columns(2)
                    n_len = es1.text_input("New Length (e.g., 20 ke 20 1/2):", value="")
                    n_unit = es2.selectbox("New Unit:", ["Foot", "Inch", "MM"])
                    
                    b1, b2 = st.columns(2)
                    if b1.button("💾 Update Stock", type="primary"):
                        if n_len:
                            n_val = parse_smart_size(n_len)
                            if n_val > 0:
                                n_total_mm = convert_to_mm(n_val, n_unit)
                                n_total_ft = n_total_mm / 304.8
                            else: st.error("Invalid Size"); st.stop()
                        else:
                            n_total_mm = float(r_d['Total Length (MM)'])
                            n_total_ft = float(r_d['Total Length (Foot)'])
                            
                        all_vals = sheet_stock.get_all_values()
                        for i, r in enumerate(all_vals):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[3]) == str(r_d['Total Length (MM)']):
                                sheet_stock.update(f"B{i+1}:E{i+1}", [[n_mat, n_total_ft, n_total_mm, n_wt]])
                                st.success("Updated Successfully!"); st.cache_resource.clear(); st.rerun(); break
                                
                    if b2.button("❌ Delete Stock"):
                        all_vals = sheet_stock.get_all_values()
                        for i, r in enumerate(all_vals):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[3]) == str(r_d['Total Length (MM)']):
                                sheet_stock.delete_rows(i+1); st.success("Deleted Successfully!"); st.cache_resource.clear(); st.rerun(); break


# ==========================================
# 2. FACTORY PARTS & CUTTING MANAGER (Junu Menu)
# ==========================================
elif menu == "✂️ Factory Parts & Cutting":
    display_header()
    st.write("### Factory Production & Cutting Manager")
    tabA, tabB, tabC = st.tabs(["➕ Add Record", "🔍 Search & Report", "✏️ Edit / Delete"])
    
    with tabA:
        c1, c2 = st.columns(2)
        raw_sel = c1.selectbox("1. Raw Material", ["-- New Material --"] + unique_materials)
        raw_val = c1.text_input("New Material Name:") if raw_sel == "-- New Material --" else raw_sel
        part_sel = c2.selectbox("2. Part Name", ["-- New Part --"] + unique_factory_parts)
        part_val = c2.text_input("New Part Name:") if part_sel == "-- New Part --" else part_sel
            
        c3, c4 = st.columns(2)
        cut_size = c3.text_input("3. Cutting Size")
        qty = c4.number_input("4. Quantity (Nang)", min_value=1)
        
        if st.button("💾 Save Cutting Record", type="primary"):
            if not raw_val or not part_val or not cut_size: st.warning("Fill all details!")
            else:
                sheet_factory.append_row([datetime.now().strftime("%d-%m-%Y"), raw_val.strip(), part_val.strip(), cut_size.strip(), int(qty)])
                st.toast("Saved! ✅"); st.cache_resource.clear(); st.rerun()
                
    with tabB:
        sc1, sc2 = st.columns(2)
        search_raw = sc1.selectbox("1. Material:", ["-- All Materials --"] + unique_materials)
        search_part = sc2.selectbox("2. Part:", ["-- All Parts --"] + unique_factory_parts)
        
        f_df = factory_df.copy()
        if not f_df.empty:
            if search_raw != "-- All Materials --": f_df = f_df[f_df['Raw Material'].astype(str).str.strip() == search_raw]
            if search_part != "-- All Parts --": f_df = f_df[f_df['Part Name'].astype(str).str.strip() == search_part]
            st.dataframe(f_df, use_container_width=True)
            st.success(f"**Total Quantity: {f_df['Quantity'].sum()}**")
            
            f_pdf = create_factory_pdf(search_raw, search_part, f_df)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Download List", data=f_pdf, file_name="Factory_List.pdf", mime="application/pdf", use_container_width=True)
            with c2:
                if st.button("👁️ View", use_container_width=True): display_pdf_in_app(f_pdf)
            
    with tabC:
        if factory_df.empty: st.info("No records.")
        else:
            edit_f_df = factory_df.copy()
            edit_f_df['Display'] = edit_f_df['Date'].astype(str) + " | " + edit_f_df['Raw Material'].astype(str) + " | " + edit_f_df['Part Name'].astype(str) + " | Qty: " + edit_f_df['Quantity'].astype(str)
            sel_rec = st.selectbox("Select Record:", edit_f_df['Display'].tolist())
            
            if sel_rec:
                r_d = edit_f_df[edit_f_df['Display'] == sel_rec].iloc[0]
                e1, e2 = st.columns(2)
                n_raw = e1.text_input("Edit Material:", value=str(r_d['Raw Material']))
                n_prt = e2.text_input("Edit Part Name:", value=str(r_d['Part Name']))
                e3, e4 = st.columns(2)
                n_cut = e3.text_input("Edit Size:", value=str(r_d['Cutting Size']))
                n_qty = e4.number_input("Edit Qty:", value=int(r_d['Quantity']), min_value=1)
                
                b1, b2 = st.columns(2)
                if b1.button("💾 Update", type="primary"):
                    for i, r in enumerate(sheet_factory.get_all_values()):
                        if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Raw Material']) and r[2] == str(r_d['Part Name']) and str(r[3]) == str(r_d['Cutting Size']):
                            sheet_factory.update(f"B{i+1}:E{i+1}", [[n_raw, n_prt, n_cut, n_qty]])
                            st.success("Updated!"); st.cache_resource.clear(); st.rerun(); break
                if b2.button("❌ Delete"):
                    for i, r in enumerate(sheet_factory.get_all_values()):
                        if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Raw Material']) and r[2] == str(r_d['Part Name']) and str(r[3]) == str(r_d['Cutting Size']):
                            sheet_factory.delete_rows(i+1); st.success("Deleted!"); st.cache_resource.clear(); st.rerun(); break

# ==========================================
# 3. ADD NEW ENTRY PAGE
# ==========================================
elif menu == "➕ Add New Entry":
    display_header()
    party_sel = st.selectbox("Select Party:", ["-- New Party --"] + unique_parties_list, index=0)
    party_name = st.text_input("Enter New Party Name:") if party_sel == "-- New Party --" else party_sel
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
        with col3: speed = st.selectbox("Speed", ["Low", "High", "Low+High"])

        size = f"{w_val}x{l_val}"
        st.write("### Add-ons")
        cols = st.columns(3)
        selected_addons, addons_prices_struct, col_idx = [], {}, 0
        
        if speed == "Low+High": addons_prices_struct["Low+High Speed Extra"] = settings['addons'].get("LowHighExtra", 0)
            
        for addon_name in settings['addons']:
            if addon_name in ["LowHighExtra"]: continue
            if cols[col_idx % 3].checkbox(addon_name):
                selected_addons.append(addon_name)
                addons_prices_struct[addon_name] = settings['addons'].get(addon_name, 0)
            col_idx += 1

        base_machine_price = int(settings['prices'].get(size, 0))
        if base_machine_price == 0: st.error(f"Base price not found for size {size}.")
        else:
            final_total_price = base_machine_price + sum(addons_prices_struct.values())
            st.success(f"**Final Machine Price: Rs. {final_total_price:,.2f}/-**")
            if st.button("➕ SAVE ENTRY", type="primary"):
                if not party_name: st.warning("Please enter Party Name!")
                else:
                    sheet_main.append_row([st.session_state.q_no, party_name, datetime.now().strftime("%d-%m-%Y"), size, speed, json.dumps(addons_prices_struct), final_total_price])
                    st.toast("Saved! ✅"); st.cache_resource.clear(); st.rerun()

    else:
        st.write("### Add Spare Part Details")
        c1, c2 = st.columns(2)
        with c1:
            part_sel = st.selectbox("Select Part:", ["-- New Part --"] + unique_parts_list, index=0)
            part_name = st.text_input("Enter New Part Name:") if part_sel == "-- New Part --" else part_sel
        with c2: basic_price = st.number_input("Basic Price (Rs)", min_value=0, step=100)
            
        c3, c4, c5 = st.columns([2, 2, 2])
        with c3: hsn_val = st.selectbox("HSN Code", ["None"] + sorted(settings.get("hsn_codes", [])))
        with c4: gst_rate = st.selectbox("GST (%)", [0] + sorted(settings.get("gst_rates", [5, 12, 18, 28])), format_func=lambda x: f"{x}%" if x > 0 else "None (0%)")
        with c5:
            final_calc_price = basic_price + (basic_price * gst_rate / 100)
            st.info(f"**Final Price: Rs. {final_calc_price:,.2f}**")
        
        if st.button("➕ SAVE PART", type="primary"):
            if not party_name or not part_name or final_calc_price <= 0: st.warning("Please enter all details!")
            else:
                sheet_main.append_row([st.session_state.q_no, party_name, datetime.now().strftime("%d-%m-%Y"), part_name, "Spare Part", json.dumps({"Basic": basic_price, "GST": gst_rate, "HSN": hsn_val}), final_calc_price])
                st.toast("Saved! ✅"); st.cache_resource.clear(); st.rerun()

# ==========================================
# 4. PARTY HISTORY & EDIT PAGE 
# ==========================================
elif menu == "📜 Party History & Edit":
    display_header()
    if main_df.empty: st.info("No records found in Google Sheet.")
    else:
        df = main_df.copy()
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        tab1, tab2, tab3 = st.tabs(["📜 View/Download PDF", "✏️ Edit Record", "❌ Delete Record"])
        
        with tab1:
            pdf_party = st.selectbox("Select Party:", ["-- Select Party --"] + unique_parties_list)
            if pdf_party != "-- Select Party --":
                party_df = df[df['Clean_Party'] == pdf_party].copy()
                
                # BUG FIX: Get FULL Processed DF with Old Dates
                processed_df = prepare_display_df_with_history(party_df)
                
                # Setup Display Dataframe (Subset of columns)
                display_df = processed_df[['Date', 'Old Date', 'Party', 'Size', 'HSN Code', 'Basic Price', 'GST', 'Old Price', 'Total_Price']].copy()
                display_df['Size'] = display_df['Size'].apply(format_size)
                display_df.rename(columns={'Total_Price': 'New Final Price(Rs)'}, inplace=True)
                
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                # PDF uses PROCESSED DF directly
                hist_pdf = create_history_pdf(pdf_party, processed_df, "Lifetime Record")
                c1, c2 = st.columns(2)
                with c1: st.download_button("📥 Download PDF", data=hist_pdf, file_name=f"{pdf_party}_Record.pdf", mime="application/pdf", use_container_width=True)
                with c2: 
                    if st.button("👁️ View Preview", use_container_width=True): display_pdf_in_app(hist_pdf)

        with tab2:
            edit_party = st.selectbox("1. Select Party (Edit):", ["-- Select Party --"] + unique_parties_list)
            if edit_party != "-- Select Party --":
                party_items = df[df['Clean_Party'] == edit_party].copy()
                party_items['Display'] = party_items['Date'].astype(str) + " | " + party_items['Size'] + " | Rs. " + party_items['Total_Price'].astype(str)
                selected_display = st.selectbox("2. Select Item:", party_items['Display'].tolist())
                
                if selected_display:
                    row_data = party_items[party_items['Display'] == selected_display].iloc[0]
                    is_spare = (str(row_data['Speed']) == 'Spare Part')
                    new_item = st.text_input("Edit Item Name:", value=row_data['Size'])
                    
                    if is_spare:
                        old_basic, old_gst, old_hsn = get_spare_details(row_data.get('Options', '{}'), row_data['Total_Price'])
                        new_basic = st.number_input("Edit Basic Price:", value=old_basic, step=100)
                        c1, c2 = st.columns(2)
                        with c1: new_hsn = st.selectbox("Edit HSN:", ["None"] + sorted(settings.get("hsn_codes", [])))
                        with c2: new_gst = st.selectbox("Edit GST:", [0] + sorted(settings.get("gst_rates", [5, 12, 18, 28])))
                        new_price = new_basic + (new_basic * new_gst / 100)
                    else: new_price = st.number_input("Edit Total Price:", value=int(float(row_data['Total_Price'])), step=100)
                    
                    if st.button("💾 Update Record", type="primary"):
                        all_values = sheet_main.get_all_values()
                        row_index_to_update = -1
                        for i, r in enumerate(all_values):
                            if i > 0 and r[1].strip().title() == edit_party and str(r[2]).strip() == str(row_data['Date']).strip() and str(r[3]).strip() == str(row_data['Size']).strip():
                                row_index_to_update = i + 1; break
                        if row_index_to_update != -1:
                            sheet_main.update_cell(row_index_to_update, 4, new_item)
                            sheet_main.update_cell(row_index_to_update, 7, new_price)
                            if is_spare: sheet_main.update_cell(row_index_to_update, 6, json.dumps({"Basic": new_basic, "GST": new_gst, "HSN": new_hsn}))
                            st.success("Updated!"); st.cache_resource.clear(); st.rerun()

        with tab3:
            del_party = st.selectbox("1. Select Party (Delete):", ["-- Select Party --"] + unique_parties_list)
            if del_party != "-- Select Party --":
                del_items = df[df['Clean_Party'] == del_party].copy()
                del_items['Display'] = del_items['Date'].astype(str) + " | " + del_items['Size'] + " | Rs. " + del_items['Total_Price'].astype(str)
                selected_del = st.selectbox("2. Select Item:", del_items['Display'].tolist())
                if selected_del and st.button("❌ Delete Permanently", type="primary"):
                    del_row_data = del_items[del_items['Display'] == selected_del].iloc[0]
                    all_values = sheet_main.get_all_values()
                    for i, r in enumerate(all_values):
                        if i > 0 and r[1].strip().title() == del_party and str(r[2]).strip() == str(del_row_data['Date']).strip() and str(r[3]).strip() == str(del_row_data['Size']).strip():
                            sheet_main.delete_rows(i + 1); st.success("Deleted!"); st.cache_resource.clear(); st.rerun(); break

# ==========================================
# 5. PART PRICE FINDER PAGE 
# ==========================================
elif menu == "🔍 Part Price Finder":
    display_header()
    if main_df.empty: st.info("No records.")
    else:
        df = main_df.copy(); df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        c1, c2 = st.columns(2)
        search_party_name = c1.selectbox("1. Party:", ["-- All Parties --"] + unique_parties_list)
        party_parts = sorted(df[df['Clean_Party'] == search_party_name]['Size'].astype(str).str.strip().unique().tolist()) if search_party_name != "-- All Parties --" else all_items_list
        search_part_name = c2.selectbox("2. Part:", ["-- All Items --"] + party_parts)
        
        filtered_df = df.copy()
        if search_party_name != "-- All Parties --": filtered_df = filtered_df[filtered_df['Clean_Party'] == search_party_name]
        if search_part_name != "-- All Items --": filtered_df = filtered_df[filtered_df['Size'].astype(str).str.strip() == search_part_name]
            
        if filtered_df.empty: st.warning("No entries found.")
        elif search_party_name == "-- All Parties --" and search_part_name == "-- All Items --": st.info("Select to search.")
        else:
            # BUG FIX: Use Processed DF for Search too
            processed_df = prepare_display_df_with_history(filtered_df)
            
            display_df = processed_df[['Date', 'Old Date', 'Party', 'Size', 'HSN Code', 'Basic Price', 'GST', 'Old Price', 'Total_Price']].copy()
            display_df['Size'] = display_df['Size'].apply(format_size)
            display_df.rename(columns={'Total_Price': 'New Final Price(Rs)'}, inplace=True)
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            pdf_buffer = create_part_search_pdf(search_party_name, search_part_name, processed_df)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Download PDF", data=pdf_buffer, file_name="Search_Result.pdf", mime="application/pdf", use_container_width=True)
            with c2: 
                if st.button("👁️ View Preview", use_container_width=True): display_pdf_in_app(pdf_buffer)

# ==========================================
# 6. MASTER SETTINGS PAGE
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
        if st.button("➕ Add New Size") and n_w and n_l and n_p > 0:
            settings['prices'][f"{n_w}x{n_l}"] = n_p; save_settings(settings); st.rerun()

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
        if st.button("➕ Add Option") and new_a and new_p > 0:
            settings['addons'][new_a] = new_p; save_settings(settings); st.rerun()
                
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

    with tab4:
        st.subheader("Manage HSN Codes")
        hsn_codes = settings.get("hsn_codes", [])
        for h in list(hsn_codes):
            cA, cB = st.columns([3, 1])
            cA.write(f"**{h}**")
            if cB.button("❌ Remove", key=f"dhsn_{h}"): hsn_codes.remove(h); settings["hsn_codes"] = hsn_codes; save_settings(settings); st.rerun()
        st.write("---")
        n_hsn = st.text_input("Add New HSN Code")
        if st.button("➕ Add New HSN") and n_hsn:
            if n_hsn not in hsn_codes: hsn_codes.append(n_hsn); hsn_codes.sort(); settings["hsn_codes"] = hsn_codes; save_settings(settings); st.rerun()
