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
from reportlab.lib.pagesizes import A4, landscape
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# --- SET PAGE CONFIG ---
page_icon_path = "logo.png" if os.path.exists("logo.png") else "🏥"
st.set_page_config(page_title="Surgicraft Industries", page_icon=page_icon_path, layout="wide")

st.markdown("""
    <link rel="apple-touch-icon" href="logo.png">
    <link rel="icon" type="image/png" href="logo.png">
    <meta name="theme-color" content="#0e1117">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
""", unsafe_allow_html=True)

DEF_SETTINGS = {
    "password": "1234",
    "prices": {
        "16x24": 160000, "16x36": 175000, "16x39": 180000, "16x48": 190000,
        "20x24": 195000, "20x36": 210000, "20x39": 215000, "20x48": 225000,
        "24x24": 240000, "24x36": 260000, "24x39": 270000, "24x48": 280000
    },
    "addons": {
        "VacuumPump": 35000, "Only Provision V.Pump Bush": 18000,
        "DoubleDoor": 30000, "Alarm": 4000, "Gauge": 5000
    },
    "lh_label": "Low+High Speed Extra",
    "gst_rates": [5, 12, 18, 28],
    "hsn_codes": [],
    "vis_mach": ['Date', 'Old Date', 'Item Details', 'Old Price', 'Total_Price'],
    "vis_part": ['Date', 'Old Date', 'Item Details', 'HSN Code', 'Old Price', 'Total_Price']
}

if 'q_no' not in st.session_state: st.session_state.q_no = f"SUR/{datetime.now().year}/{datetime.now().strftime('%m%d%H%M')}"

# --- GOOGLE SHEETS CONNECTION ---
@st.cache_resource
def get_sheets():
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
        sheet_factory.append_row(["Date", "Raw Material", "Part Name", "Cutting Size", "Final Size", "Quantity"])
        
    try: sheet_stock = db.worksheet("Master_Stock")
    except:
        sheet_stock = db.add_worksheet(title="Master_Stock", rows="1000", cols="10")
        sheet_stock.append_row(["Date", "Material Name", "Total Length (Foot)", "Total Length (MM)", "Weight (KG)"])
        
    try: sheet_hexo = db.worksheet("Hexo_Cutting")
    except:
        sheet_hexo = db.add_worksheet(title="Hexo_Cutting", rows="1000", cols="10")
        sheet_hexo.append_row(["Date", "Material Name", "Cut Size", "Quantity", "Blade Margin (MM)", "Total Used (MM)"])
        
    try: sheet_settings = db.worksheet("App_Settings")
    except:
        sheet_settings = db.add_worksheet(title="App_Settings", rows="10", cols="2")
        sheet_settings.update_acell("B1", json.dumps(DEF_SETTINGS))
        
    return sheet_main, sheet_factory, sheet_stock, sheet_hexo, sheet_settings

# --- SMART CACHE ---
@st.cache_data(ttl=120)
def fetch_all_data():
    sheet_m, sheet_f, sheet_s, sheet_h, sheet_set = get_sheets()
    return (
        pd.DataFrame(sheet_m.get_all_records()) if sheet_m.get_all_records() else pd.DataFrame(),
        pd.DataFrame(sheet_f.get_all_records()) if sheet_f.get_all_records() else pd.DataFrame(),
        pd.DataFrame(sheet_s.get_all_records()) if sheet_s.get_all_records() else pd.DataFrame(),
        pd.DataFrame(sheet_h.get_all_records()) if sheet_h.get_all_records() else pd.DataFrame()
    )

def load_settings_from_sheet():
    try:
        _, _, _, _, sheet_set = get_sheets()
        val = sheet_set.acell("B1").value
        if val:
            data = json.loads(val)
            if "gst_rates" not in data: data["gst_rates"] = [5, 12, 18, 28]
            if "hsn_codes" not in data: data["hsn_codes"] = []
            if "lh_label" not in data: data["lh_label"] = "Low+High Speed Extra"
            if "vis_mach" not in data: data["vis_mach"] = ['Date', 'Old Date', 'Item Details', 'Old Price', 'Total_Price']
            if "vis_part" not in data: data["vis_part"] = ['Date', 'Old Date', 'Item Details', 'HSN Code', 'Old Price', 'Total_Price']
            return data
    except: pass
    return DEF_SETTINGS

def save_settings_to_sheet(data):
    try:
        _, _, _, _, sheet_set = get_sheets()
        sheet_set.update_acell("B1", json.dumps(data))
    except Exception as e: st.error(f"Error saving settings: {e}")

def clear_all_caches():
    st.cache_data.clear()
    st.cache_resource.clear()

settings = load_settings_from_sheet()

try:
    sheet_main, sheet_factory, sheet_stock, sheet_hexo, sheet_set = get_sheets()
    main_df, factory_df, stock_df, hexo_df = fetch_all_data()
    
    unique_parties_list = sorted(main_df['Party'].astype(str).str.strip().str.title().unique().tolist()) if not main_df.empty else []
    unique_parts_list = sorted(main_df[main_df['Speed'] == 'Spare Part']['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    all_items_list = sorted(main_df['Size'].astype(str).str.strip().unique().tolist()) if not main_df.empty else []
    unique_materials = sorted(factory_df['Raw Material'].astype(str).str.strip().unique().tolist()) if not factory_df.empty else []
    unique_materials = [x for x in unique_materials if x and x != 'nan']
    unique_factory_parts = sorted(factory_df['Part Name'].astype(str).str.strip().unique().tolist()) if not factory_df.empty else []
    unique_factory_parts = [x for x in unique_factory_parts if x and x != 'nan']
    stock_materials_full = sorted(stock_df['Material Name'].astype(str).str.strip().unique().tolist()) if not stock_df.empty else []
except Exception as e:
    st.error(f"Google Sheet Connection Error: {e}")
    st.stop()

def safe_date(val_str):
    parsed = pd.to_datetime(val_str, format="%d-%m-%Y", errors='coerce')
    if pd.isna(parsed): return datetime.today()
    return parsed

def safe_int(val, fallback=1):
    try:
        if pd.isna(val) or val == '' or val == '-': return fallback
        return int(float(val))
    except: return fallback

def safe_float(val, fallback=0.0):
    try:
        if pd.isna(val) or val == '' or val == '-': return fallback
        return float(val)
    except: return fallback

def format_size(size_str):
    if "x" in size_str:
        parts = size_str.split('x')
        if len(parts) == 2 and parts[0].strip().isdigit(): return f'{parts[0].strip()}" x {parts[1].strip()}"'
    return size_str

def get_spare_details(row_options, total_price):
    basic, gst, hsn = 0, 0, "-"
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

def get_raw_full_name(row, settings_dict):
    opts = {}
    try: opts = json.loads(str(row.get('Options', '{}')))
    except: pass
    
    if opts.get('Is_Custom_Name', False):
        return str(row['Size'])
        
    base = str(row['Size'])
    speed = str(row.get('Speed', ''))
    if speed == 'Spare Part': return base
    
    if speed not in ["-", "", "nan", "-- None --", "None"]:
        base += f" {speed} Speed"
        
    custom_dtl = opts.get('Custom_Details', '')
    if custom_dtl:
        base += f" + {custom_dtl}"
        
    lh_label = settings_dict.get('lh_label', 'Low+High Speed Extra')
    addons = [k for k,v in opts.items() if k not in ['Basic', 'GST', 'HSN', 'ManualOldDate', 'ManualOldPrice', lh_label, 'Custom_Details', 'Is_Custom_Name'] and isinstance(v, (int, float))]
    if addons:
        base += " + " + " + ".join(addons)
    return base

# --- REMOVED "Machine: " and "Part: " FROM DETAILS ---
def get_item_details_str(row):
    opts = {}
    try: opts = json.loads(str(row.get('Options', '{}')))
    except: pass
    
    if opts.get('Is_Custom_Name', False):
        return str(row['Size'])
        
    size_formatted = format_size(str(row['Size']))
    speed_str = str(row.get('Speed', ''))
    
    if speed_str == 'Spare Part':
        return f"{size_formatted}"
        
    res = size_formatted
    if speed_str not in ["-", "", "nan", "-- None --", "None"]:
        res += f" {speed_str} Speed"
        
    custom_dtl = opts.get('Custom_Details', '')
    if custom_dtl:
        res += f" + {custom_dtl}"
        
    lh_label = settings.get('lh_label', 'Low+High Speed Extra')
    addons = [k for k,v in opts.items() if k not in ['Basic', 'GST', 'HSN', 'ManualOldDate', 'ManualOldPrice', lh_label, 'Custom_Details', 'Is_Custom_Name'] and isinstance(v, (int, float))]
    if addons:
        res += " + " + " + ".join(addons)
    return res

def prepare_display_df_with_history(df):
    df = df.copy()
    df['DateObj'] = pd.to_datetime(df['Date'], format="%d-%m-%Y", errors='coerce')
    df = df.sort_values('DateObj', ascending=False)

    basics, gsts, hsns = [], [], []
    old_dates, old_prices = [], []
    full_details = []

    for idx, row in df.iterrows():
        opts = {}
        try: opts = json.loads(str(row.get('Options', '{}')))
        except: pass
        
        m_old_date = opts.get('ManualOldDate', '-') if isinstance(opts, dict) else '-'
        m_old_price = opts.get('ManualOldPrice', '-') if isinstance(opts, dict) else '-'
        
        old_dates.append(m_old_date if m_old_date.strip() else "-")
        old_prices.append(m_old_price if str(m_old_price).strip() else "-")
        
        full_details.append(get_item_details_str(row))

        if str(row['Speed']) == 'Spare Part':
            b, g, h = get_spare_details(row.get('Options', '{}'), row.get('Total_Price', 0))
            basics.append(b); gsts.append(f"{g}%" if g > 0 else "-"); hsns.append(h if h and h != "None" else "-")
        else:
            basics.append("-"); gsts.append("-"); hsns.append("-")
            
    df['Old Date'] = old_dates
    df['Old Price'] = old_prices
    df['HSN Code'] = hsns
    df['Basic Price'] = basics
    df['GST'] = gsts
    df['Item Details'] = full_details
    
    return df

def make_full_display_name(r):
    base = f"{r['Date']} | "
    base += get_item_details_str(r)
    return f"{base} | Rs. {r['Total_Price']}"

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
    except: return -1.0

def convert_to_mm(val, unit):
    if unit == "Foot": return val * 304.8
    elif unit == "Inch": return val * 25.4
    else: return val

def mm_to_foot_inch(mm_val):
    total_inches = mm_val / 25.4
    feet = int(total_inches // 12)
    inches = total_inches % 12
    return f"{feet} Foot {inches:.1f} Inch"

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

# --- NEW DYNAMIC PDF FUNCTION ---
def create_dynamic_pdf(party, records_df, title_str, visible_cols, is_machine=True):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    width, height = landscape(A4)
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, height - 40, title_str)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 60, f"Party Name: {party}")
    c.drawString(width - 150, height - 60, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    if not visible_cols: 
        c.drawString(40, height - 100, "No columns selected for PDF.")
        c.save(); buffer.seek(0); return buffer

    y = height - 90
    c.setFont("Helvetica-Bold", 10)
    
    start_x = 40
    end_x = width - 40
    avail_width = end_x - start_x
    
    col_widths = {'Date': 70, 'Old Date': 70, 'HSN Code': 60, 'Old Price': 80, 'Total_Price': 100, 'Party': 120}
    fixed_w = sum([col_widths[col] for col in visible_cols if col in col_widths])
    
    if 'Item Details' in visible_cols:
        col_widths['Item Details'] = max(100, avail_width - fixed_w)
        
    cols = [start_x]
    for col in visible_cols:
        cols.append(cols[-1] + col_widths.get(col, 80))
        
    row_y_top = y + 20; row_y_bot = y - 5
    for i, col in enumerate(visible_cols):
        if col == 'Item Details': c.drawString(cols[i]+5, y+2, "Item Description / Details")
        elif col == 'Total_Price': c.drawCentredString((cols[i]+cols[i+1])/2.0, y+2, "New Final Price (Rs)")
        elif col == 'Party': c.drawString(cols[i]+5, y+2, "Party Name")
        else: c.drawCentredString((cols[i]+cols[i+1])/2.0, y+2, col)
            
    draw_grid_lines(c, row_y_top, row_y_bot, cols); y = row_y_bot

    for index, row in records_df.iterrows():
        total_val = row.get('Total_Price', 0)
        total_price = int(total_val) if pd.notna(total_val) else 0
        
        speed_str = str(row['Speed'])
        opts = {}
        try: opts = json.loads(str(row.get('Options', '{}')))
        except: pass
        
        addons = []
        if is_machine and not opts.get('Is_Custom_Name', False):
            addons = [k for k,v in opts.items() if k not in ['Basic', 'GST', 'HSN', 'ManualOldDate', 'ManualOldPrice', settings.get('lh_label', 'Low+High Speed Extra'), 'Custom_Details', 'Is_Custom_Name'] and isinstance(v, (int, float))]
            
        needed_height = 25
        if 'Item Details' in visible_cols and is_machine:
            needed_height += len(addons) * 15
            
        if y - needed_height < 50:
            c.showPage(); y = height - 50; c.setFont("Helvetica-Bold", 10)
            row_y_top = y + 20; row_y_bot = y - 5
            for i, col in enumerate(visible_cols):
                if col == 'Item Details': c.drawString(cols[i]+5, y+2, "Item Description / Details")
                elif col == 'Total_Price': c.drawCentredString((cols[i]+cols[i+1])/2.0, y+2, "New Final Price (Rs)")
                elif col == 'Party': c.drawString(cols[i]+5, y+2, "Party Name")
                else: c.drawCentredString((cols[i]+cols[i+1])/2.0, y+2, col)
            draw_grid_lines(c, row_y_top, row_y_bot, cols); y = row_y_bot

        row_y_top = y; text_y = y - 15 
        c.setFont("Helvetica-Bold", 9)
        
        dt_val = str(row['Date']) if str(row['Date']) not in ["-", "nan", ""] else ""
        odt_val = str(row['Old Date']) if str(row['Old Date']) not in ["-", "nan", ""] else ""
        old_price_str = f"{row['Old Price']:,.2f}" if str(row['Old Price']).replace('.','').isdigit() else str(row['Old Price'])
        if old_price_str == "-" or old_price_str == "nan": old_price_str = ""
        new_price_str = f"{total_price:,.2f}"
        hsn_str = str(row.get('HSN Code', '-'))[:8]
        
        max_drop = 10
        for i, col in enumerate(visible_cols):
            mid_x = (cols[i]+cols[i+1])/2.0
            if col == 'Date': c.drawCentredString(mid_x, text_y, dt_val)
            elif col == 'Old Date': c.drawCentredString(mid_x, text_y, odt_val)
            elif col == 'HSN Code': c.drawCentredString(mid_x, text_y, hsn_str)
            elif col == 'Old Price': c.drawCentredString(mid_x, text_y, old_price_str)
            elif col == 'Total_Price': c.drawCentredString(mid_x, text_y, new_price_str) 
            elif col == 'Party': c.drawString(cols[i]+5, text_y, str(row.get('Party', ''))[:22])
            elif col == 'Item Details':
                c.setFont("Helvetica", 9)
                item_str = get_item_details_str(row)
                if not is_machine and "Basic Price" in row and "GST" in row:
                    item_str += f" (Basic: Rs.{row['Basic Price']} | GST: {row['GST']})"
                
                c.drawString(cols[i]+5, text_y, item_str)
                temp_y = text_y - 15
                c.setFont("Helvetica-Oblique", 8)
                if is_machine and not opts.get('Is_Custom_Name', False):
                    for name in addons:
                        c.drawString(cols[i]+15, temp_y, f"• Add-on: {name}")
                        temp_y -= 15
                max_drop = max(max_drop, (text_y - temp_y) + 5)
                c.setFont("Helvetica-Bold", 9)
                
        y = text_y - max_drop
        row_y_bot = y; draw_grid_lines(c, row_y_top, row_y_bot, cols)
        
    c.save(); buffer.seek(0); return buffer

def create_factory_pdf(raw_material, search_part, df, orientation="Aadu (Landscape)"):
    buffer = io.BytesIO()
    
    if "Portrait" in orientation:
        pagesize_selected = A4
        cols = [30, 85, 185, 310, 385, 450, 490, 565] 
    else:
        pagesize_selected = landscape(A4)
        cols = [40, 110, 290, 450, 560, 680, 740, 800] 
        
    width, height = pagesize_selected
    c = canvas.Canvas(buffer, pagesize=pagesize_selected)
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(cols[0], height - 40, "Surgicraft Factory Production & Cutting List")
    c.setFont("Helvetica", 10)
    c.drawString(cols[0], height - 60, f"Material Filter: {raw_material}")
    c.drawString(cols[2], height - 60, f"Part Filter: {search_part}")
    c.drawString(cols[4], height - 60, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = height - 100
    c.setFont("Helvetica-Bold", 9)
    row_y_top = y + 20; row_y_bot = y - 5
    
    c.drawCentredString((cols[0]+cols[1])/2.0, y+2, "Date")
    c.drawCentredString((cols[1]+cols[2])/2.0, y+2, "Raw Material")
    c.drawCentredString((cols[2]+cols[3])/2.0, y+2, "Part Name")
    c.drawCentredString((cols[3]+cols[4])/2.0, y+2, "Cut Size")
    c.drawCentredString((cols[4]+cols[5])/2.0, y+2, "Final Size")
    c.drawCentredString((cols[5]+cols[6])/2.0, y+2, "Qty")
    c.drawCentredString((cols[6]+cols[7])/2.0, y+2, "Date") 
    draw_grid_lines(c, row_y_top, row_y_bot, cols); y = row_y_bot
    
    for index, row in df.iterrows():
        if y - 25 < 50:
            c.showPage(); y = height - 50; c.setFont("Helvetica-Bold", 9)
            row_y_top = y+20; row_y_bot = y-5
            c.drawCentredString((cols[0]+cols[1])/2.0, y+2, "Date"); c.drawCentredString((cols[1]+cols[2])/2.0, y+2, "Raw Material")
            c.drawCentredString((cols[2]+cols[3])/2.0, y+2, "Part Name"); c.drawCentredString((cols[3]+cols[4])/2.0, y+2, "Cut Size")
            c.drawCentredString((cols[4]+cols[5])/2.0, y+2, "Final Size"); c.drawCentredString((cols[5]+cols[6])/2.0, y+2, "Qty")
            c.drawCentredString((cols[6]+cols[7])/2.0, y+2, "Date")
            draw_grid_lines(c, row_y_top, row_y_bot, cols); y = row_y_bot
            
        row_y_top = y; text_y = y - 15
        c.setFont("Helvetica", 8)
        
        c.drawCentredString((cols[0]+cols[1])/2.0, text_y, str(row['Date'])[:10])
        c.drawString(cols[1]+5, text_y, str(row['Raw Material']))
        c.drawString(cols[2]+5, text_y, str(row['Part Name']))
        c.drawCentredString((cols[3]+cols[4])/2.0, text_y, str(row['Cutting Size']))
        
        final_sz = str(row.get('Final Size', ''))
        if final_sz == 'nan' or final_sz == '' or final_sz == '-': final_sz = ''
        c.drawCentredString((cols[4]+cols[5])/2.0, text_y, final_sz)
        
        c.drawCentredString((cols[5]+cols[6])/2.0, text_y, str(row['Quantity']))
        row_y_bot = text_y - 5; draw_grid_lines(c, row_y_top, row_y_bot, cols); y = row_y_bot
        
    c.save(); buffer.seek(0); return buffer

def create_hexo_pdf(mat_name, mat_in, mat_out, balance_mm, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14); c.drawString(40, 800, "Surgicraft Godown Balance & Cutting Report")
    c.setFont("Helvetica-Bold", 11); c.drawString(40, 775, f"Material: {mat_name}"); c.drawString(400, 775, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    c.setFont("Helvetica", 10); c.drawString(40, 755, f"📥 Total In (Aavyo): {mm_to_foot_inch(mat_in)}")
    c.drawString(40, 740, f"✂️ Total Out (Kapayo): {mm_to_foot_inch(mat_out)}")
    c.setFillColorRGB(0, 0.5, 0); c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 720, f"✅ Balance (Padyo che): {mm_to_foot_inch(balance_mm)} ({balance_mm:.1f} MM)")
    c.setFillColorRGB(0, 0, 0)
    
    y = 690; c.setFont("Helvetica-Bold", 10)
    cols = [40, 105, 195, 255, 345, 550]
    row_y_top = y + 20; row_y_bot = y - 5
    
    c.drawCentredString((cols[0]+cols[1])/2.0, y+2, "Date"); c.drawCentredString((cols[1]+cols[2])/2.0, y+2, "Cut Size")
    c.drawCentredString((cols[2]+cols[3])/2.0, y+2, "Qty"); c.drawCentredString((cols[3]+cols[4])/2.0, y+2, "Blade Margin")
    c.drawCentredString((cols[4]+cols[5])/2.0, y+2, "Total Used (MM)")
    draw_grid_lines(c, row_y_top, row_y_bot, cols); y = row_y_bot
    
    for index, row in df.iterrows():
        if y - 25 < 50:
            c.showPage(); y = 800; c.setFont("Helvetica-Bold", 10)
            row_y_top = y+20; row_y_bot = y-5
            c.drawCentredString((cols[0]+cols[1])/2.0, y+2, "Date"); c.drawCentredString((cols[1]+cols[2])/2.0, y+2, "Cut Size")
            c.drawCentredString((cols[2]+cols[3])/2.0, y+2, "Qty"); c.drawCentredString((cols[3]+cols[4])/2.0, y+2, "Blade Margin")
            c.drawCentredString((cols[4]+cols[5])/2.0, y+2, "Total Used (MM)")
            draw_grid_lines(c, row_y_top, row_y_bot, cols); y = row_y_bot
            
        row_y_top = y; text_y = y - 15
        c.setFont("Helvetica", 9)
        c.drawCentredString((cols[0]+cols[1])/2.0, text_y, str(row['Date'])[:10])
        c.drawCentredString((cols[1]+cols[2])/2.0, text_y, str(row['Cut Size']))
        c.drawCentredString((cols[2]+cols[3])/2.0, text_y, str(row['Quantity']))
        c.drawCentredString((cols[3]+cols[4])/2.0, text_y, str(row['Blade Margin (MM)']))
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(cols[5]-10, text_y, f"{float(row['Total Used (MM)']):.1f}")
        
        row_y_bot = text_y - 5; draw_grid_lines(c, row_y_top, row_y_bot, cols); y = row_y_bot
        
    c.save(); buffer.seek(0); return buffer

def send_monthly_report_email(month_str, pdf_buffers):
    try:
        if "email_user" not in st.secrets or "email_pass" not in st.secrets:
            return False, "Email Credentials not found in Secrets!"
            
        sender = st.secrets["email_user"]
        password = st.secrets["email_pass"]
        receiver = "surgicraftindustries@gmail.com"

        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = receiver
        msg['Subject'] = f"Surgicraft Monthly Report - {month_str}"

        body = f"""
        Hello Ankit Bhai,
        
        Attached are the Surgicraft Industries monthly reports for {month_str}.
        
        - Factory Production & Cutting Report
        - Master Stock & Hexo Cutting Balance Report
        - Machine Party Detail
        - Parts Party Detail
        
        Regards,
        Surgicraft App
        """
        msg.attach(MIMEText(body, 'plain'))

        for filename, buf in pdf_buffers.items():
            part = MIMEApplication(buf.getvalue(), Name=filename)
            part['Content-Disposition'] = f'attachment; filename="{filename}"'
            msg.attach(part)

        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
        server.quit()
        return True, "Email sent successfully!"
    except Exception as e:
        return False, str(e)


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
    "📧 Monthly Email Reports", 
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
            m_in = pd.to_numeric(stock_df[stock_df['Material Name'] == mat]['Total Length (MM)'], errors='coerce').fillna(0).sum()
            m_out = pd.to_numeric(hexo_df[hexo_df['Material Name'] == mat]['Total Used (MM)'], errors='coerce').fillna(0).sum() if not hexo_df.empty else 0
            if (m_in - m_out) < 1524: alert_list.append(mat)
    if alert_list: st.error(f"🚨 **ALERT!** Nichena maal no stock 5 Foot thi occho che: **{', '.join(alert_list)}**")

    st.write("### 🪚 Hexo Cutting & Live Balance Dashboard")
    htab1, htab2, htab3, htab4 = st.tabs(["✂️ Cutting Entry", "📥 Navo Maal Aavyo", "📊 Search Godown & PDF", "✏️ Edit / Delete"])
    
    with htab1:
        st.write("**Ankit bhai mate - Cutting Entry & Estimator:**")
        c1, c2 = st.columns(2)
        mat_sel = c1.selectbox("1. Material Select Karo:", ["-- Select --", "-- New Material --"] + stock_materials_full, key="mat_sel_hexo")
        if mat_sel == "-- New Material --": cut_mat = c1.text_input("📝 Navu Material Lakho (e.g. Hex 22mm 304):", key="new_mat_hexo")
        else: cut_mat = mat_sel
        
        st.write("**2. Cut Size (e.g., 65, 4 1/8, 4.25):**")
        sc1, sc2 = st.columns(2)
        cut_size_str = sc1.text_input("Size Lakho (Fractions chale che):", value="", key="cut_size_hexo")
        cut_unit = sc2.selectbox("Ekam (Unit) Select:", ["MM", "Inch", "Foot"], key="unit_hexo")
        
        c3, c4 = st.columns(2)
        cut_qty = c3.number_input("3. Tukda ni Quantity (Nang):", min_value=1, step=1, key="qty_hexo")
        blade_margin = c4.number_input("4. Blade Margin (Wastage):", value=1.5, step=0.1, key="margin_hexo")
        
        st.write("---")
        st.write("🧠 **Live Ganatri (Estimator):**")
        rod_foot = st.number_input("Standard Ladi (Rod) Lumbai (Foot ma) - Optional:", min_value=0.0, value=0.0, step=1.0, key="rod_hexo")
        
        if cut_size_str and cut_mat and cut_mat != "-- Select --":
            size_val = parse_smart_size(cut_size_str)
            if size_val > 0 and cut_qty > 0:
                size_in_mm = convert_to_mm(size_val, cut_unit)
                total_used_mm = (size_in_mm + blade_margin) * cut_qty
                
                current_in = pd.to_numeric(stock_df[stock_df['Material Name'] == cut_mat]['Total Length (MM)'], errors='coerce').fillna(0).sum() if not stock_df.empty else 0
                current_out = pd.to_numeric(hexo_df[hexo_df['Material Name'] == cut_mat]['Total Used (MM)'], errors='coerce').fillna(0).sum() if not hexo_df.empty else 0
                current_balance = current_in - current_out
                new_balance = current_balance - total_used_mm
                
                st.info(f"👉 **Kaapva mate jarur:** ({size_in_mm:.1f}mm + {blade_margin}mm) x {cut_qty} = **{mm_to_foot_inch(total_used_mm)}** total maal joise.")
                st.info(f"👉 **Tijori Balance:** Atyare {mm_to_foot_inch(current_balance)} che. Aa kapya pachi **{mm_to_foot_inch(new_balance)}** vadhse.")
                
                if rod_foot > 0:
                    rod_mm = rod_foot * 304.8
                    rods_needed = math.ceil(total_used_mm / rod_mm)
                    wastage = (rods_needed * rod_mm) - total_used_mm
                    st.success(f"📌 **Saliya Ganatri:** Tamare **{rods_needed} aakha saliya** joise. (Chhelle {mm_to_foot_inch(wastage)} no tukdo vadhse).")
                
                if st.button("✂️ Kapi Nakho (Save & Update Stock)", type="primary", key="btn_save_hexo"):
                    dt_str = datetime.now().strftime("%d-%m-%Y")
                    if mat_sel == "-- New Material --" and cut_mat not in stock_materials_full:
                        sheet_stock.append_row([dt_str, cut_mat.strip(), 0, 0, 0])
                    display_size = f'{cut_size_str} {cut_unit}'
                    sheet_hexo.append_row([dt_str, cut_mat.strip(), display_size, cut_qty, blade_margin, total_used_mm])
                    st.success("Cutting save thai gayu! ✅"); clear_all_caches(); st.rerun()
            elif size_val < 0: st.error("Invalid Size! Format check karo (e.g. 65 or 4 1/8)")

    with htab2:
        st.write("**Papa mate - Navo maal aave tyare ahiya nakhvo:**")
        new_mat_name = st.text_input("1. Raw Material Naam (e.g., SS 304 28MM Round):", key="new_stock_name")
        
        st.write("**2. Maap (Lumbai - Fractions chale che):**")
        col_v, col_u, col_k = st.columns(3)
        in_val_str = col_v.text_input("Lumbai Lakho (e.g. 20 ke 20 1/2):", value="", key="new_stock_len")
        in_unit = col_u.selectbox("3. Ekam (Unit):", ["Foot", "Inch", "MM"], key="new_stock_unit")
        weight_kg = col_k.number_input("4. Total Vajan (KG) - Optional:", min_value=0.0, step=1.0, key="new_stock_weight")
        
        if st.button("💾 Save Navo Maal", type="primary", key="btn_save_stock"):
            in_val = parse_smart_size(in_val_str) if in_val_str else 0
            if not new_mat_name or in_val <= 0: st.warning("Material nu naam ane sachi lumbai nakho!")
            else:
                total_mm = convert_to_mm(in_val, in_unit)
                total_foot = total_mm / 304.8
                sheet_stock.append_row([datetime.now().strftime("%d-%m-%Y"), new_mat_name.strip(), total_foot, total_mm, weight_kg])
                st.toast(f"{new_mat_name} aavi gayo! ✅"); clear_all_caches(); st.rerun()

    with htab3:
        st.write("**🔍 Smart Search & Godown PDF:**")
        search_txt = st.text_input("Material nu naam shodhva ahiya lakho (e.g., '32', 'dr', 'patti'):", value="", key="search_hexo_pdf")
        
        if not stock_df.empty:
            filtered_mats = [m for m in stock_materials_full if search_txt.lower() in m.lower()] if search_txt else stock_materials_full
            if not filtered_mats: st.warning("Aa naam no koi maal malyo nathi.")
            
            for mat in filtered_mats:
                mat_in = pd.to_numeric(stock_df[stock_df['Material Name'] == mat]['Total Length (MM)'], errors='coerce').fillna(0).sum()
                mat_hexo_df = hexo_df[hexo_df['Material Name'] == mat] if not hexo_df.empty else pd.DataFrame()
                mat_out = pd.to_numeric(mat_hexo_df['Total Used (MM)'], errors='coerce').fillna(0).sum() if not mat_hexo_df.empty else 0
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
                        with c_dl: st.download_button("📥 Download PDF", data=pdf_buf, file_name=f"{mat}_Report.pdf", mime="application/pdf", use_container_width=True, key=f"dl_{mat}")
                        with c_pv: 
                            if st.button(f"👁️ View Preview", key=f"pv_{mat}", use_container_width=True): display_pdf_in_app(pdf_buf)

    with htab4:
        st.write("**✏️ Edit ke Delete Karo (Hexo & Stock):**")
        edit_type = st.radio("Shu sudharvu che?", ["✂️ Cutting Entry (Stock Out)", "📥 Stock Entry (Navo Maal)"], horizontal=True, key="edit_type_radio")
        
        if edit_type == "✂️ Cutting Entry (Stock Out)":
            if hexo_df.empty: st.info("Koi cutting entry nathi.")
            else:
                h_df = hexo_df.copy()
                h_df['Display'] = h_df['Date'].astype(str) + " | " + h_df['Material Name'].astype(str) + " | Size: " + h_df['Cut Size'].astype(str) + " | Qty: " + h_df['Quantity'].astype(str)
                sel_h_rec = st.selectbox("Select Record to Edit (Cutting):", h_df['Display'].tolist(), key="edit_hexo_sel")
                
                if sel_h_rec:
                    r_d = h_df[h_df['Display'] == sel_h_rec].iloc[0]
                    k_suf = str(hash(sel_h_rec)).replace("-", "") 
                    
                    e1, e2 = st.columns(2)
                    c_mat_index = stock_materials_full.index(str(r_d['Material Name'])) if str(r_d['Material Name']) in stock_materials_full else 0
                    n_mat = e1.selectbox("Edit Material Name:", stock_materials_full, index=c_mat_index, key=f"edit_h_mat_{k_suf}")
                    
                    orig_size = str(r_d['Cut Size'])
                    o_unit = "MM"
                    if "Inch" in orig_size: o_unit = "Inch"
                    elif "Foot" in orig_size: o_unit = "Foot"
                    o_val_str = orig_size.replace('MM', '').replace('Inch', '').replace('Foot', '').strip()
                    
                    st.write("**Cut Size & Unit:**")
                    es1, es2 = st.columns(2)
                    n_cut = es1.text_input("Edit Size:", value=o_val_str, key=f"edit_h_size_{k_suf}")
                    n_unit = es2.selectbox("Edit Unit:", ["MM", "Inch", "Foot"], index=["MM", "Inch", "Foot"].index(o_unit), key=f"edit_h_unit_{k_suf}")
                    
                    e3, e4 = st.columns(2)
                    n_qty = e3.number_input("Edit Qty:", value=safe_int(r_d['Quantity'], 1), min_value=1, key=f"edit_h_qty_{k_suf}")
                    n_margin = e4.number_input("Edit Margin (MM):", value=safe_float(r_d['Blade Margin (MM)'], 1.5), step=0.1, key=f"edit_h_margin_{k_suf}")
                    
                    b1, b2 = st.columns(2)
                    if b1.button("💾 Update Cutting", type="primary", key=f"btn_upd_hexo_{k_suf}"):
                        n_val = parse_smart_size(n_cut)
                        if n_val > 0:
                            n_mm = convert_to_mm(n_val, n_unit)
                            n_total = (n_mm + n_margin) * n_qty
                            n_disp_size = f"{n_cut} {n_unit}"
                            all_vals = sheet_hexo.get_all_values()
                            for i, r in enumerate(all_vals):
                                if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[2]) == str(r_d['Cut Size']) and str(r[3]) == str(r_d['Quantity']):
                                    sheet_hexo.update(f"B{i+1}:F{i+1}", [[n_mat, n_disp_size, n_qty, n_margin, n_total]])
                                    st.success("Updated!"); clear_all_caches(); st.rerun(); break
                        else: st.error("Invalid Size format.")
                            
                    if b2.button("❌ Delete Cutting", key=f"btn_del_hexo_{k_suf}"):
                        all_vals = sheet_hexo.get_all_values()
                        for i, r in enumerate(all_vals):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[2]) == str(r_d['Cut Size']) and str(r[3]) == str(r_d['Quantity']):
                                sheet_hexo.delete_rows(i+1); st.success("Deleted!"); clear_all_caches(); st.rerun(); break

        else:
            if stock_df.empty: st.info("Koi stock entry nathi.")
            else:
                s_df = stock_df.copy()
                s_df['Display'] = s_df['Date'].astype(str) + " | " + s_df['Material Name'].astype(str) + " | Total MM: " + s_df['Total Length (MM)'].astype(str)
                sel_s_rec = st.selectbox("Select Record to Edit (Stock):", s_df['Display'].tolist(), key="edit_stock_sel")
                
                if sel_s_rec:
                    r_d = s_df[s_df['Display'] == sel_s_rec].iloc[0]
                    k_suf = str(hash(sel_s_rec)).replace("-", "")
                    
                    st.write("---")
                    e1, e2 = st.columns(2)
                    n_mat = e1.text_input("Edit Material Name:", value=str(r_d['Material Name']), key=f"edit_s_mat_{k_suf}")
                    n_wt = e2.number_input("Edit Weight (KG):", value=safe_float(r_d.get('Weight (KG)', 0.0)), key=f"edit_s_wt_{k_suf}")
                    
                    st.write("**Nevi Lumbai Nakho (Keep blank to keep old):**")
                    es1, es2 = st.columns(2)
                    n_len = es1.text_input("New Length (e.g., 20 ke 20 1/2):", value="", key=f"edit_s_len_{k_suf}")
                    n_unit = es2.selectbox("New Unit:", ["Foot", "Inch", "MM"], key=f"edit_s_unit_{k_suf}")
                    
                    b1, b2 = st.columns(2)
                    if b1.button("💾 Update Stock", type="primary", key=f"btn_upd_stock_{k_suf}"):
                        if n_len:
                            n_val = parse_smart_size(n_len)
                            if n_val > 0:
                                n_total_mm = convert_to_mm(n_val, n_unit); n_total_ft = n_total_mm / 304.8
                            else: st.error("Invalid Size"); st.stop()
                        else:
                            n_total_mm = float(r_d['Total Length (MM)']); n_total_ft = float(r_d['Total Length (Foot)'])
                            
                        all_vals = sheet_stock.get_all_values()
                        for i, r in enumerate(all_vals):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[3]) == str(r_d['Total Length (MM)']):
                                sheet_stock.update(f"B{i+1}:E{i+1}", [[n_mat, n_total_ft, n_total_mm, n_wt]])
                                st.success("Updated!"); clear_all_caches(); st.rerun(); break
                                
                    if b2.button("❌ Delete Stock", key=f"btn_del_stock_{k_suf}"):
                        all_vals = sheet_stock.get_all_values()
                        for i, r in enumerate(all_vals):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[3]) == str(r_d['Total Length (MM)']):
                                sheet_stock.delete_rows(i+1); st.success("Deleted!"); clear_all_caches(); st.rerun(); break

# ==========================================
# 2. FACTORY PARTS & CUTTING MANAGER 
# ==========================================
elif menu == "✂️ Factory Parts & Cutting":
    display_header()
    st.write("### Factory Production & Cutting Manager")
    tabA, tabB, tabC = st.tabs(["➕ Add Record", "🔍 Search & Report", "✏️ Edit / Delete"])
    
    with tabA:
        st.write("📝 **Record Details:**")
        c01, c02, c03 = st.columns([1, 1, 1])
        rec_date = c01.date_input("Date Select Karo:", datetime.today(), key="fac_date")
        
        c1, c2 = st.columns(2)
        raw_sel = c1.selectbox("1. Raw Material (Optional)", ["-- Khali Rakho (Empty) --", "-- New Material --"] + unique_materials, key="fac_raw_sel")
        if raw_sel == "-- New Material --": raw_val = c1.text_input("New Material Name:", key="fac_new_raw")
        elif raw_sel == "-- Khali Rakho (Empty) --": raw_val = "-"
        else: raw_val = raw_sel
            
        part_sel = c2.selectbox("2. Part Name (Farajiyat)", ["-- New Part --"] + unique_factory_parts, key="fac_part_sel")
        if part_sel == "-- New Part --": part_val = c2.text_input("New Part Name:", key="fac_new_part")
        else: part_val = part_sel
            
        c3, c4, c5 = st.columns([1.5, 1.5, 1])
        cut_size = c3.text_input("3. Cutting Size", key="fac_cut_sz")
        final_size = c4.text_input("4. Final Size (Optional)", key="fac_fin_sz") 
        qty = c5.number_input("5. Quantity", min_value=1, key="fac_qty")
        
        if st.button("💾 Save Cutting Record", type="primary", key="btn_save_fac"):
            if not part_val or not cut_size: st.warning("Part Name ane Cutting Size farajiyat (compulsory) che!")
            else:
                dt_str = rec_date.strftime("%d-%m-%Y")
                f_sz = final_size.strip() if final_size else "-"
                sheet_factory.append_row([dt_str, raw_val.strip(), part_val.strip(), cut_size.strip(), f_sz, int(qty)])
                st.toast("Saved! ✅"); clear_all_caches(); st.rerun()
                
    with tabB:
        st.write("🔍 **Smart Search & Filters:**")
        search_kw_factory = st.text_input("Type here to Search (e.g. 20, MS, Stand):", "", key="search_fac")
        
        sc1, sc2 = st.columns(2)
        search_raw = sc1.selectbox("Filter by Material (Optional):", ["-- All Materials --"] + unique_materials, key="search_fac_raw")
        search_part = sc2.selectbox("Filter by Part (Optional):", ["-- All Parts --"] + unique_factory_parts, key="search_fac_part")
        
        f_df = factory_df.copy()
        if not f_df.empty:
            if search_raw != "-- All Materials --": f_df = f_df[f_df['Raw Material'].astype(str).str.strip() == search_raw]
            if search_part != "-- All Parts --": f_df = f_df[f_df['Part Name'].astype(str).str.strip() == search_part]
            
            if search_kw_factory:
                mask = f_df[['Raw Material', 'Part Name', 'Cutting Size']].astype(str).apply(lambda x: x.str.contains(search_kw_factory, case=False, na=False)).any(axis=1)
                f_df = f_df[mask]
                
            st.dataframe(f_df, use_container_width=True)
            
            safe_qty = pd.to_numeric(f_df['Quantity'], errors='coerce').fillna(0).sum()
            st.success(f"**Total Quantity: {int(safe_qty)}**")
            
            st.write("---")
            pdf_format = st.radio("📄 PDF Design Format Select Karo:", ["Aadu (Landscape) - Best for Long Names", "Ubhu (Portrait)"], horizontal=True, key="fac_pdf_format")
            
            f_pdf = create_factory_pdf(search_raw, search_part, f_df, orientation=pdf_format)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Download List PDF", data=f_pdf, file_name="Factory_List.pdf", mime="application/pdf", use_container_width=True, key="dl_fac_pdf")
            with c2:
                if st.button("👁️ View Preview", use_container_width=True, key="pv_fac_pdf"): display_pdf_in_app(f_pdf)
            
    with tabC:
        if factory_df.empty: st.info("No records.")
        else:
            edit_f_df = factory_df.copy()
            edit_f_df['Final Size'] = edit_f_df.get('Final Size', '')
            edit_f_df['Display'] = edit_f_df['Date'].astype(str) + " | " + edit_f_df['Part Name'].astype(str) + " | Cut: " + edit_f_df['Cutting Size'].astype(str)
            sel_rec = st.selectbox("Select Record:", edit_f_df['Display'].tolist(), key="edit_fac_sel")
            
            if sel_rec:
                r_d = edit_f_df[edit_f_df['Display'] == sel_rec].iloc[0]
                k_suf = str(hash(sel_rec)).replace("-", "")
                
                e_d = st.date_input("Edit Date:", safe_date(str(r_d['Date'])), key=f"edit_fac_date_{k_suf}")
                
                e1, e2 = st.columns(2)
                n_raw = e1.text_input("Edit Material:", value=str(r_d['Raw Material']), key=f"edit_fac_raw_{k_suf}")
                n_prt = e2.text_input("Edit Part Name:", value=str(r_d['Part Name']), key=f"edit_fac_part_{k_suf}")
                e3, e4, e5 = st.columns([1.5, 1.5, 1])
                n_cut = e3.text_input("Edit Cutting Size:", value=str(r_d['Cutting Size']), key=f"edit_fac_cutsz_{k_suf}")
                n_final = e4.text_input("Edit Final Size:", value=str(r_d.get('Final Size', '')), key=f"edit_fac_finsz_{k_suf}")
                n_qty = e5.number_input("Edit Qty:", value=safe_int(r_d.get('Quantity', 1), 1), min_value=1, key=f"edit_fac_qty_{k_suf}")
                
                b1, b2 = st.columns(2)
                if b1.button("💾 Update", type="primary", key=f"btn_upd_fac_{k_suf}"):
                    n_dt_str = e_d.strftime("%d-%m-%Y")
                    for i, r in enumerate(sheet_factory.get_all_values()):
                        if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Raw Material']) and r[2] == str(r_d['Part Name']) and str(r[3]) == str(r_d['Cutting Size']):
                            sheet_factory.update(f"A{i+1}:F{i+1}", [[n_dt_str, n_raw, n_prt, n_cut, n_final if n_final else "-", n_qty]])
                            st.success("Updated!"); clear_all_caches(); st.rerun(); break
                if b2.button("❌ Delete", key=f"btn_del_fac_{k_suf}"):
                    for i, r in enumerate(sheet_factory.get_all_values()):
                        if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Raw Material']) and r[2] == str(r_d['Part Name']) and str(r[3]) == str(r_d['Cutting Size']):
                            sheet_factory.delete_rows(i+1); st.success("Deleted!"); clear_all_caches(); st.rerun(); break

# ==========================================
# 3. ADD NEW ENTRY PAGE
# ==========================================
elif menu == "➕ Add New Entry":
    display_header()
    party_sel = st.selectbox("Select Party:", ["-- New Party --"] + unique_parties_list, index=0, key="add_party_sel")
    party_name = st.text_input("Enter New Party Name:", key="add_party_new") if party_sel == "-- New Party --" else party_sel
    
    if party_name and party_name != "-- New Party --" and not main_df.empty:
        party_hist = main_df[main_df['Party'].astype(str).str.strip().str.title() == party_name.strip().title()].copy()
        if not party_hist.empty:
            st.markdown(f"📜 **{party_name} નો જૂનો રેકોર્ડ (Double Entry Check):**")
            p_hist_proc = prepare_display_df_with_history(party_hist)
            disp_hist = p_hist_proc[['Date', 'Item Details', 'Total_Price']].rename(columns={'Total_Price': 'Final Price (Rs)'})
            styled_hist = disp_hist.style.set_properties(subset=['Final Price (Rs)'], **{'text-align': 'center'})
            st.dataframe(styled_hist, use_container_width=True, hide_index=True)
            
    st.write("---")
    entry_type = st.radio("What do you want to add?", ["Machine", "Spare Part / Custom Item"], horizontal=True, key="add_entry_type")
    
    if entry_type == "Machine":
        col1, col2, col3 = st.columns([2, 2, 2])
        with col1:
            widths = sorted(list(set([k.split('x')[0] for k in settings['prices'].keys() if 'x' in k])))
            w_val = st.selectbox("Width", widths if widths else ["0"], key="add_w")
        with col2:
            lengths = sorted(list(set([k.split('x')[1] for k in settings['prices'].keys() if 'x' in k])))
            l_val = st.selectbox("Length", lengths if lengths else ["0"], key="add_l")
        with col3: 
            speed = st.selectbox("Speed", ["-- None --", "Low", "High", "Low+High"], key="add_speed")
        
        st.write("**Custom Machine Details (નામમાં પાછળ જોડવા માટે):**")
        custom_machine_details = st.text_input("અહીં લખો (દા.ત. Double Door + V.Pump 1 HP):", placeholder="Type details here to add after speed...", key="add_custom_machine_details")

        size = f"{w_val}x{l_val}"
        st.write("### Add-ons (Optional Checkboxes)")
        cols = st.columns(3)
        selected_addons, addons_prices_struct, col_idx = [], {}, 0
        
        lh_label = settings.get('lh_label', 'Low+High Speed Extra')
        if speed == "Low+High": addons_prices_struct[lh_label] = settings['addons'].get(lh_label, 0)
        
        if custom_machine_details.strip():
            addons_prices_struct["Custom_Details"] = custom_machine_details.strip()
            
        for addon_name in settings['addons']:
            if addon_name == lh_label: continue
            if cols[col_idx % 3].checkbox(addon_name, key=f"chk_{addon_name}"):
                selected_addons.append(addon_name)
                addons_prices_struct[addon_name] = settings['addons'].get(addon_name, 0)
            col_idx += 1

        base_machine_price = int(settings['prices'].get(size, 0))
        if base_machine_price == 0: st.error(f"Base price not found for size {size}.")
        else:
            calculated_total_price = base_machine_price + sum([v for k,v in addons_prices_struct.items() if isinstance(v, (int, float))])
            st.info(f"💡 અંદાજિત ગણતરી (Idea માટે): Rs. {calculated_total_price:,.2f}/-")
            
            final_total_price = st.number_input("Final Machine Price (કાગળમાંથી જોઈને જાતે લખો):", value=calculated_total_price, step=100, key="btn_add_manual_price")
            
            if st.button("➕ SAVE ENTRY", type="primary", key="btn_add_entry"):
                if not party_name: st.warning("Please enter Party Name!")
                else:
                    speed_val_to_save = "-" if speed == "-- None --" else speed
                    sheet_main.append_row([st.session_state.q_no, party_name.strip().title(), datetime.now().strftime("%d-%m-%Y"), size, speed_val_to_save, json.dumps(addons_prices_struct), final_total_price])
                    st.toast("Saved! ✅"); clear_all_caches(); st.rerun()

    else:
        st.write("### Add Spare Part Details")
        c1, c2 = st.columns(2)
        with c1:
            part_sel = st.selectbox("Select Part:", ["-- New Part --"] + unique_parts_list, index=0, key="add_sp_sel")
            part_name = st.text_input("Enter New Part Name:", key="add_sp_new") if part_sel == "-- New Part --" else part_sel
        with c2: basic_price = st.number_input("Basic Price (Rs)", min_value=0, step=100, key="add_sp_price")
            
        c3, c4, c5 = st.columns([2, 2, 2])
        with c3: 
            hsn_list = ["None"] + sorted(settings.get("hsn_codes", []))
            hsn_sel = st.selectbox("Select HSN Code:", ["-- Type New --"] + hsn_list, key="add_sp_hsn_sel")
            if hsn_sel == "-- Type New --": hsn_val = st.text_input("📝 Type New HSN Code:", value="", key="add_sp_hsn_new")
            else: hsn_val = hsn_sel
                
        with c4: gst_rate = st.selectbox("GST (%)", [0] + sorted(settings.get("gst_rates", [5, 12, 18, 28])), format_func=lambda x: f"{x}%" if x > 0 else "None (0%)", key="add_sp_gst")
        with c5:
            final_calc_price = basic_price + (basic_price * gst_rate / 100)
            st.info(f"**Final Price: Rs. {final_calc_price:,.2f}**")
        
        if st.button("➕ SAVE PART", type="primary", key="btn_add_part"):
            if not party_name or not part_name or final_calc_price <= 0: st.warning("Please enter all details!")
            else:
                sheet_main.append_row([st.session_state.q_no, party_name.strip().title(), datetime.now().strftime("%d-%m-%Y"), part_name, "Spare Part", json.dumps({"Basic": basic_price, "GST": gst_rate, "HSN": hsn_val}), final_calc_price])
                st.toast("Saved! ✅"); clear_all_caches(); st.rerun()

# ==========================================
# 4. PARTY HISTORY & EDIT PAGE 
# ==========================================
elif menu == "📜 Party History & Edit":
    display_header()
    if main_df.empty: st.info("No records found in Google Sheet.")
    else:
        df = main_df.copy()
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        
        tab1, tab2, tab3, tab4 = st.tabs(["📜 View/Download PDF", "✏️ Edit Record", "❌ Delete Record", "📋 Copy/Clone Party"])
        
        with tab1:
            pdf_party = st.selectbox("Select Party:", ["-- Select Party --"] + unique_parties_list, key="view_party_sel")
            if pdf_party != "-- Select Party --":
                party_df = df[df['Clean_Party'] == pdf_party].copy()
                processed_df = prepare_display_df_with_history(party_df)
                
                search_kw_hist = st.text_input("🔍 Smart Keyword Search (Filter by Item, Speed, Size...):", "", key="search_hist_party")
                if search_kw_hist:
                    mask = processed_df.astype(str).apply(lambda x: x.str.contains(search_kw_hist, case=False, na=False)).any(axis=1)
                    processed_df = processed_df[mask]
                
                if processed_df.empty:
                    st.warning("No records match your search.")
                else:
                    mach_df = processed_df[processed_df['Speed'] != 'Spare Part']
                    part_df = processed_df[processed_df['Speed'] == 'Spare Part']
                    
                    st.write("---")
                    st.write("**⚙️ કઈ કોલમ જોવી છે તે સિલેક્ટ કરો (આ સેટિંગ કાયમ માટે સેવ રહેશે):**")
                    
                    mach_cols_all = ['Date', 'Old Date', 'Item Details', 'Old Price', 'Total_Price']
                    part_cols_all = ['Date', 'Old Date', 'Item Details', 'HSN Code', 'Old Price', 'Total_Price']
                    
                    # CLEANUP OLD SETTINGS TO PREVENT ERRORS
                    saved_mach = settings.get('vis_mach', mach_cols_all)
                    saved_mach = [c if c != 'New Final Price(Rs)' else 'Total_Price' for c in saved_mach]
                    saved_mach = [c for c in saved_mach if c in mach_cols_all]
                    if not saved_mach: saved_mach = mach_cols_all

                    saved_part = settings.get('vis_part', part_cols_all)
                    saved_part = [c if c != 'New Final Price(Rs)' else 'Total_Price' for c in saved_part]
                    saved_part = [c for c in saved_part if c in part_cols_all]
                    if not saved_part: saved_part = part_cols_all
                    
                    c_m, c_p = st.columns(2)
                    sel_mach = c_m.multiselect("Machine Table Columns:", mach_cols_all, default=saved_mach, format_func=lambda x: "New Final Price (Rs)" if x == "Total_Price" else x, key="ms_mach")
                    sel_part = c_p.multiselect("Spare Parts Table Columns:", part_cols_all, default=saved_part, format_func=lambda x: "New Final Price (Rs)" if x == "Total_Price" else x, key="ms_part")
                    
                    if set(sel_mach) != set(saved_mach) or set(sel_part) != set(saved_part):
                        settings['vis_mach'] = sel_mach
                        settings['vis_part'] = sel_part
                        save_settings_to_sheet(settings)
                        st.toast("Column settings saved! ✅")
                    
                    st.write("---")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        if not mach_df.empty:
                            st.write(f"### ⚙️ Machine Records ({len(mach_df)})")
                            mach_disp = mach_df[sel_mach].copy() if sel_mach else mach_df[['Item Details']].copy()
                            
                            if 'Total_Price' in mach_disp.columns:
                                mach_disp.rename(columns={'Total_Price': 'New Final Price (Rs)'}, inplace=True)
                                styled_mach = mach_disp.style.set_properties(subset=['New Final Price (Rs)'], **{'text-align': 'center'})
                                st.dataframe(styled_mach, use_container_width=True, hide_index=True)
                            else:
                                st.dataframe(mach_disp, use_container_width=True, hide_index=True)
                            
                            mach_pdf = create_dynamic_pdf(pdf_party, mach_df, "Surgicraft Industries HHP Machine Price List (GST Extra) HSN CODE - 8419", sel_mach, is_machine=True)
                            st.download_button("📥 Download Machine PDF", data=mach_pdf, file_name=f"{pdf_party}_Machines.pdf", mime="application/pdf", use_container_width=True)
                        else:
                            st.info("આ પાર્ટીમાં કોઈ મશીનનો રેકોર્ડ નથી.")
                            
                    with col2:
                        if not part_df.empty:
                            st.write(f"### 🔧 Spare Parts Records ({len(part_df)})")
                            part_disp = part_df[sel_part].copy() if sel_part else part_df[['Item Details']].copy()
                            
                            if 'Total_Price' in part_disp.columns:
                                part_disp.rename(columns={'Total_Price': 'New Final Price (Rs)'}, inplace=True)
                                styled_part = part_disp.style.set_properties(subset=['New Final Price (Rs)'], **{'text-align': 'center'})
                                st.dataframe(styled_part, use_container_width=True, hide_index=True)
                            else:
                                st.dataframe(part_disp, use_container_width=True, hide_index=True)
                                
                            part_pdf = create_dynamic_pdf(pdf_party, part_df, "Surgicraft Spare Parts Price List", sel_part, is_machine=False)
                            st.download_button("📥 Download Spare Parts PDF", data=part_pdf, file_name=f"{pdf_party}_Parts.pdf", mime="application/pdf", use_container_width=True)
                        else:
                            st.info("આ પાર્ટીમાં કોઈ સ્પેર-પાર્ટ્સનો રેકોર્ડ નથી.")

        with tab2:
            edit_party = st.selectbox("1. Select Party (Edit):", ["-- Select Party --"] + unique_parties_list, key="edit_hist_party")
            if edit_party != "-- Select Party --":
                party_items = df[df['Clean_Party'] == edit_party].copy()
                processed_items = prepare_display_df_with_history(party_items)
                processed_items['Display'] = processed_items.apply(make_full_display_name, axis=1)
                
                selected_display = st.selectbox("2. Select Item:", processed_items['Display'].tolist(), key="edit_hist_item")
                
                if selected_display:
                    row_data = processed_items[processed_items['Display'] == selected_display].iloc[0]
                    is_spare = (str(row_data['Speed']) == 'Spare Part')
                    k_suf = str(hash(selected_display)).replace("-", "")
                    
                    st.write("---")
                    eP1, eP2 = st.columns(2)
                    new_party_name = eP1.text_input("Edit Party Name (Transfer):", value=str(row_data['Party']), key=f"edit_hist_pname_{k_suf}")
                    
                    current_full_name = get_raw_full_name(row_data, settings)
                    new_item = eP2.text_input("Edit Item/Machine Name (આખું નામ બદલવા માટે):", value=current_full_name, key=f"edit_hist_iname_{k_suf}")
                    
                    opts_dict = {}
                    try: opts_dict = json.loads(str(row_data.get('Options', '{}')))
                    except: pass
                    
                    st.write("**Edit Dates & Prices (Leave blank to keep Empty):**")
                    d1, d2 = st.columns(2)
                    n_new_date = d1.text_input("Edit New Date:", value=str(row_data['Date']) if str(row_data['Date']) not in ["-", "nan", ""] else "", key=f"edit_ndate_{k_suf}")
                    n_old_date = d2.text_input("Edit Old Date:", value=str(row_data.get('Old Date', '')) if str(row_data.get('Old Date', '')) not in ["-", "nan", ""] else "", key=f"edit_odate_{k_suf}")
                    
                    d3, d4 = st.columns(2)
                    n_old_price = d3.text_input("Edit Old Price:", value=str(row_data.get('Old Price', '')).replace('-',''), key=f"edit_oprice_{k_suf}")
                    
                    if is_spare:
                        old_basic, old_gst, old_hsn = get_spare_details(row_data.get('Options', '{}'), row_data['Total_Price'])
                        new_basic = st.number_input("Edit Basic Price:", value=safe_int(old_basic, 0), step=100, key=f"edit_hist_sprice_{k_suf}")
                        
                        c1, c2 = st.columns(2)
                        with c1: 
                            hsn_list = ["None"] + sorted(settings.get("hsn_codes", []))
                            if old_hsn and old_hsn not in hsn_list and old_hsn != "-": hsn_list.append(old_hsn)
                            hsn_sel = st.selectbox("Edit HSN:", ["-- Type New --"] + hsn_list, index=hsn_list.index(old_hsn)+1 if old_hsn in hsn_list else 0, key=f"edit_hist_hsnsel_{k_suf}")
                            if hsn_sel == "-- Type New --": new_hsn = st.text_input("📝 Type New HSN Code:", value=old_hsn if old_hsn not in hsn_list and old_hsn != "-" else "", key=f"edit_hist_hsnnew_{k_suf}")
                            else: new_hsn = hsn_sel
                                
                        with c2: new_gst = st.selectbox("Edit GST:", [0] + sorted(settings.get("gst_rates", [5, 12, 18, 28])), key=f"edit_hist_gst_{k_suf}")
                        new_price = d4.number_input("New Final Price (Auto calculated but editable):", value=int(new_basic + (new_basic * new_gst / 100)), step=100, key=f"edit_sp_final_{k_suf}")
                    else: 
                        new_price = d4.number_input("New Final Price:", value=safe_int(row_data['Total_Price'], 0), step=100, key=f"edit_hist_mprice_{k_suf}")
                    
                    if st.button("💾 Update Record", type="primary", key=f"btn_upd_hist_{k_suf}"):
                        if not new_party_name: st.warning("Party Name cannot be empty!")
                        else:
                            all_values = sheet_main.get_all_values()
                            row_index_to_update = -1
                            for i, r in enumerate(all_values):
                                if i > 0 and r[1].strip().title() == edit_party and str(r[2]).strip() == str(row_data['Date']).strip() and str(r[3]).strip() == str(row_data['Size']).strip():
                                    row_index_to_update = i + 1; break
                                    
                            if row_index_to_update != -1:
                                opts_dict['ManualOldDate'] = n_old_date.strip() if n_old_date.strip() else "-"
                                opts_dict['ManualOldPrice'] = n_old_price.strip() if n_old_price.strip() else "-"
                                
                                size_to_save = new_item.strip()
                                opts_dict['Is_Custom_Name'] = True
                                
                                if is_spare:
                                    opts_dict['HSN'] = new_hsn if new_hsn and new_hsn != "None" else "-"
                                    opts_dict['Basic'] = new_basic
                                    opts_dict['GST'] = new_gst
                                
                                final_date = n_new_date.strip() if n_new_date.strip() else "-"
                                
                                sheet_main.update_cell(row_index_to_update, 2, new_party_name.strip().title()) 
                                sheet_main.update_cell(row_index_to_update, 3, final_date)
                                sheet_main.update_cell(row_index_to_update, 4, size_to_save)
                                sheet_main.update_cell(row_index_to_update, 6, json.dumps(opts_dict))
                                sheet_main.update_cell(row_index_to_update, 7, new_price)
                                
                                st.success("Updated Successfully!"); clear_all_caches(); st.rerun()

        with tab3:
            del_party = st.selectbox("1. Select Party (Delete):", ["-- Select Party --"] + unique_parties_list, key="del_hist_party")
            if del_party != "-- Select Party --":
                del_items = df[df['Clean_Party'] == del_party].copy()
                processed_del_items = prepare_display_df_with_history(del_items)
                processed_del_items['Display'] = processed_del_items.apply(make_full_display_name, axis=1)
                
                selected_del = st.selectbox("2. Select Item:", processed_del_items['Display'].tolist(), key="del_hist_item")
                if selected_del and st.button("❌ Delete Permanently", type="primary", key="btn_del_hist"):
                    del_row_data = processed_del_items[processed_del_items['Display'] == selected_del].iloc[0]
                    all_values = sheet_main.get_all_values()
                    for i, r in enumerate(all_values):
                        if i > 0 and r[1].strip().title() == del_party and str(r[2]).strip() == str(del_row_data['Date']).strip() and str(r[3]).strip() == str(del_row_data['Size']).strip():
                            sheet_main.delete_rows(i + 1); st.success("Deleted!"); clear_all_caches(); st.rerun(); break
                            
        with tab4:
            st.write("### 📋 Copy Entire Party List & Apply % Price Change")
            clone_from = st.selectbox("1. Select Party to Copy From:", ["-- Select --"] + unique_parties_list, key="clone_from")
            
            if clone_from != "-- Select --":
                party_data = df[df['Clean_Party'] == clone_from].copy()
                processed_party = prepare_display_df_with_history(party_data)
                processed_party['Display'] = processed_party.apply(make_full_display_name, axis=1)
                
                st.write("**2. Select Items to Clone (Uncheck the ones you don't want):**")
                item_displays = processed_party['Display'].tolist()
                
                selected_clone_items = []
                for i, disp in enumerate(item_displays):
                    if st.checkbox(disp, value=True, key=f"clone_chk_{clone_from}_{i}"):
                        selected_clone_items.append(disp)
                
                st.write("---")
                c1, c2 = st.columns(2)
                pct_change = c1.number_input("3. Percentage Change (+ for Increase, - for Decrease):", value=0.0, step=1.0, key="clone_pct")
                new_party_target = c2.text_input("4. New Party Name (To save these items):", key="clone_new_party")
                
                if st.button("🚀 Clone & Save to New Party", type="primary", key="btn_clone_party"):
                    if not new_party_target:
                        st.warning("Please enter a New Party Name!")
                    elif not selected_clone_items:
                        st.warning("Please select at least one item to copy!")
                    else:
                        new_rows = []
                        dt_str = datetime.now().strftime("%d-%m-%Y")
                        lh_label = settings.get('lh_label', 'Low+High Speed Extra')
                        
                        for disp in selected_clone_items:
                            r_d = processed_party[processed_party['Display'] == disp].iloc[0]
                            old_total = safe_int(r_d['Total_Price'], 0)
                            new_total = int(old_total * (1 + (pct_change / 100.0)))
                            
                            is_spare = (str(r_d['Speed']) == 'Spare Part')
                            new_options = str(r_d.get('Options', '{}'))
                            
                            if is_spare:
                                old_basic, old_gst, old_hsn = get_spare_details(r_d.get('Options', '{}'), old_total)
                                new_basic = int(old_basic * (1 + (pct_change / 100.0)))
                                new_total = int(new_basic + (new_basic * old_gst / 100.0))
                                new_options = json.dumps({"Basic": new_basic, "GST": old_gst, "HSN": old_hsn})
                            else:
                                try:
                                    opts_dict = json.loads(new_options)
                                    for k, v in list(opts_dict.items()):
                                        if k not in ['HSN', 'ManualOldDate', 'ManualOldPrice', lh_label, 'Custom_Details', 'Is_Custom_Name'] and isinstance(v, (int, float)):
                                            opts_dict[k] = int(v * (1 + (pct_change / 100.0)))
                                    opts_dict['ManualOldDate'] = "-"
                                    opts_dict['ManualOldPrice'] = "-"
                                    new_options = json.dumps(opts_dict)
                                except: pass

                            new_rows.append([
                                st.session_state.q_no, 
                                new_party_target.strip().title(), 
                                dt_str, 
                                r_d['Size'], 
                                str(r_d['Speed']), 
                                new_options, 
                                new_total
                            ])
                        
                        if new_rows:
                            sheet_main.append_rows(new_rows)
                            st.success(f"Successfully cloned {len(new_rows)} items to '{new_party_target}' with {pct_change}% adjustment! ✅")
                            clear_all_caches()
                            st.rerun()

# ==========================================
# 5. PART PRICE FINDER PAGE 
# ==========================================
elif menu == "🔍 Part Price Finder":
    display_header()
    if main_df.empty: st.info("No records.")
    else:
        df = main_df.copy(); df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        
        search_kw_price = st.text_input("🔍 Smart Keyword Search (Type Part Name, Size, Machine e.g., 'Valve', '16x24'):", "", key="search_pf")
        
        c1, c2 = st.columns(2)
        search_party_name = c1.selectbox("Filter by Party (Optional):", ["-- All Parties --"] + unique_parties_list, key="search_pf_party")
        party_parts = sorted(df[df['Clean_Party'] == search_party_name]['Size'].astype(str).str.strip().unique().tolist()) if search_party_name != "-- All Parties --" else all_items_list
        search_part_name = c2.selectbox("Filter by Item (Optional):", ["-- All Items --"] + party_parts, key="search_pf_item")
        
        filtered_df = df.copy()
        if search_party_name != "-- All Parties --": filtered_df = filtered_df[filtered_df['Clean_Party'] == search_party_name]
        if search_part_name != "-- All Items --": filtered_df = filtered_df[filtered_df['Size'].astype(str).str.strip() == search_part_name]
        
        if search_kw_price:
            mask = filtered_df[['Size', 'Speed', 'Party']].astype(str).apply(lambda x: x.str.contains(search_kw_price, case=False, na=False)).any(axis=1)
            filtered_df = filtered_df[mask]
            
        if filtered_df.empty: st.warning("No entries found.")
        elif search_party_name == "-- All Parties --" and search_part_name == "-- All Items --" and not search_kw_price: 
            st.info("Select filters or type a keyword to search.")
        else:
            processed_df = prepare_display_df_with_history(filtered_df)
            display_df = processed_df[['Date', 'Old Date', 'Party', 'Item Details', 'HSN Code', 'Basic Price', 'GST', 'Old Price', 'Total_Price']].copy()
            
            if 'Total_Price' in display_df.columns:
                display_df.rename(columns={'Total_Price': 'New Final Price (Rs)'}, inplace=True)
                styled_disp = display_df.style.set_properties(subset=['New Final Price (Rs)'], **{'text-align': 'center'})
                st.dataframe(styled_disp, use_container_width=True, hide_index=True)
            else:
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            pdf_buffer = create_dynamic_pdf(search_party_name, processed_df, "Surgicraft Item / Part Price Report", ['Date', 'Party', 'Item Details', 'Old Price', 'Total_Price'], is_machine=False)
            c1, c2 = st.columns(2)
            with c1: st.download_button("📥 Download PDF", data=pdf_buffer, file_name="Search_Result.pdf", mime="application/pdf", use_container_width=True, key="dl_pf_pdf")
            with c2: 
                if st.button("👁️ View Preview", use_container_width=True, key="pv_pf_pdf"): display_pdf_in_app(pdf_buffer)


# ==========================================
# 6. MONTHLY EMAIL REPORTS PAGE
# ==========================================
elif menu == "📧 Monthly Email Reports":
    display_header()
    st.write("### 📧 Auto-Generate & Email Monthly Reports")
    
    st.info("Select a Month and Year to generate and email all master reports (Factory, Stock, and SEPARATE Party Sales).")
    
    c1, c2 = st.columns(2)
    months = ["01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12"]
    current_month = datetime.now().strftime("%m")
    current_year = datetime.now().year
    years = [str(y) for y in range(current_year - 2, current_year + 3)]
    
    sel_month = c1.selectbox("Select Month:", months, index=months.index(current_month), key="mail_month")
    sel_year = c2.selectbox("Select Year:", years, index=years.index(str(current_year)), key="mail_year")
    target_str = f"-{sel_month}-{sel_year}" 
    display_month_str = f"{datetime.strptime(sel_month, '%m').strftime('%B')} {sel_year}"
    
    st.write("---")
    
    if st.button("🚀 Generate & Send Email Now", type="primary", key="btn_send_mail"):
        with st.spinner(f"Preparing reports for {display_month_str} and sending email... Please wait."):
            
            pdf_attachments = {}
            
            f_df = factory_df.copy()
            if not f_df.empty:
                f_df = f_df[f_df['Date'].astype(str).str.endswith(target_str)]
                if not f_df.empty:
                    pdf_attachments[f"Factory_Report_{display_month_str}.pdf"] = create_factory_pdf("-- All --", "-- All --", f_df, orientation="Aadu (Landscape)")
            
            h_df = hexo_df.copy()
            if not h_df.empty:
                h_df = h_df[h_df['Date'].astype(str).str.endswith(target_str)]
                if not h_df.empty:
                     mat_in = pd.to_numeric(stock_df[stock_df['Date'].astype(str).str.endswith(target_str)]['Total Length (MM)'], errors='coerce').fillna(0).sum() if not stock_df.empty else 0
                     mat_out = pd.to_numeric(h_df['Total Used (MM)'], errors='coerce').fillna(0).sum()
                     pdf_attachments[f"Hexo_Cutting_Report_{display_month_str}.pdf"] = create_hexo_pdf("All Materials", mat_in, mat_out, mat_in - mat_out, h_df)

            m_df = main_df.copy()
            if not m_df.empty:
                m_df = m_df[m_df['Date'].astype(str).str.endswith(target_str)]
                if not m_df.empty:
                    processed_m_df = prepare_display_df_with_history(m_df)
                    
                    machines_df = processed_m_df[processed_m_df['Speed'] != 'Spare Part']
                    parts_df = processed_m_df[processed_m_df['Speed'] == 'Spare Part']
                    
                    if not machines_df.empty:
                        title_machine = f"Surgicraft Monthly Machine Party Detail ({display_month_str})"
                        pdf_attachments[f"Machine_Sales_Report_{display_month_str}.pdf"] = create_dynamic_pdf(title_machine, machines_df, title_machine, settings.get('vis_mach', ['Date', 'Party', 'Item Details', 'Old Price', 'Total_Price']), is_machine=True)
                        
                    if not parts_df.empty:
                        title_parts = f"Surgicraft Monthly Parts Party Detail ({display_month_str})"
                        pdf_attachments[f"Spare_Parts_Sales_Report_{display_month_str}.pdf"] = create_dynamic_pdf(title_parts, parts_df, title_parts, settings.get('vis_part', ['Date', 'Party', 'Item Details', 'HSN Code', 'Old Price', 'Total_Price']), is_machine=False)
            
            if not pdf_attachments:
                st.warning(f"No records found for {display_month_str}. Nothing to email.")
            else:
                success, msg = send_monthly_report_email(display_month_str, pdf_attachments)
                if success:
                    st.success("✅ " + msg)
                    st.balloons()
                else:
                    st.error("❌ Failed to send email: " + msg)

# ==========================================
# 7. MASTER SETTINGS PAGE
# ==========================================
elif menu == "⚙️ Master Settings":
    display_header()
    st.title("Master Settings 🔒")
    pwd_input = st.text_input("Enter Master Password:", type="password", key="pwd_master")
    
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
            if cC.button("❌ Remove", key=f"d_{size}"): del prices[size]; save_settings_to_sheet(settings); st.rerun()
                    
        st.write("---")
        c1, c2, c3 = st.columns(3)
        n_w = c1.text_input("Width (e.g. 24)", key="set_nw")
        n_l = c2.text_input("Length (e.g. 48)", key="set_nl")
        n_p = c3.number_input("Base Price", value=0, step=1000, key="set_np")
        if st.button("➕ Add New Size", key="btn_set_sz") and n_w and n_l and n_p > 0:
            settings['prices'][f"{n_w}x{n_l}"] = n_p; save_settings_to_sheet(settings); st.rerun()

    with tab2:
        st.subheader("Edit/Remove Add-ons")
        addons = settings['addons']
        
        lh_label = settings.get('lh_label', 'Low+High Speed Extra')
        lh_price = settings['addons'].get(lh_label, 0)
        
        st.write("**Special Speed Label & Price:**")
        cA, cB, cC = st.columns([2, 2, 1])
        new_lh_label = cA.text_input("Label Name", value=lh_label, key="set_lh_label", label_visibility="collapsed")
        new_lh_price = cB.number_input("Price", value=lh_price, step=500, key="set_lh_price", label_visibility="collapsed")
        
        if cC.button("💾 Update Label", key="btn_ren_lh"):
            if new_lh_label != lh_label:
                settings['addons'][new_lh_label] = new_lh_price
                if lh_label in settings['addons']:
                    del settings['addons'][lh_label]
                settings['lh_label'] = new_lh_label
            else:
                settings['addons'][lh_label] = new_lh_price
            save_settings_to_sheet(settings)
            st.success("Special Label Updated!")
            st.rerun()
            
        st.write("---")
            
        for name, price in list(addons.items()):
            if name == settings.get('lh_label', 'Low+High Speed Extra'): continue
            cA, cB, cC = st.columns([2, 2, 1])
            cA.write(f"**{name}**")
            addons[name] = cB.number_input("Price", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
            if cC.button("❌ Remove", key=f"da_{name}"): del addons[name]; save_settings_to_sheet(settings); st.rerun()
                        
        if st.button("💾 Save Add-on Changes", type="primary", key="btn_set_add_save"): save_settings_to_sheet(settings); st.success("Updated!")
        st.write("---")
        c1, c2 = st.columns(2)
        new_a = c1.text_input("New Add-on Name", key="set_na")
        new_p = c2.number_input("Add-on Price", value=0, step=500, key="set_nap")
        if st.button("➕ Add Option", key="btn_set_add") and new_a and new_p > 0:
            settings['addons'][new_a] = new_p; save_settings_to_sheet(settings); st.rerun()
                
    with tab3:
        st.subheader("Manage GST Percentages (%)")
        gst_rates = settings.get("gst_rates", [5, 12, 18, 28])
        for g in list(gst_rates):
            cA, cB = st.columns([3, 1])
            cA.write(f"**{g}%** GST")
            if cB.button("❌ Remove", key=f"dgst_{g}"): gst_rates.remove(g); settings["gst_rates"] = gst_rates; save_settings_to_sheet(settings); st.rerun()
        st.write("---")
        n_gst = st.number_input("Add New GST Rate (%)", min_value=1, max_value=100, step=1, key="set_ngst")
        if st.button("➕ Add New GST %", key="btn_set_gst"):
            if n_gst not in gst_rates: gst_rates.append(n_gst); gst_rates.sort(); settings["gst_rates"] = gst_rates; save_settings_to_sheet(settings); st.rerun()

    with tab4:
        st.subheader("Manage HSN Codes")
        hsn_codes = settings.get("hsn_codes", [])
        for h in list(hsn_codes):
            cA, cB = st.columns([3, 1])
            cA.write(f"**{h}**")
            if cB.button("❌ Remove", key=f"dhsn_{h}"): hsn_codes.remove(h); settings["hsn_codes"] = hsn_codes; save_settings_to_sheet(settings); st.rerun()
        st.write("---")
        n_hsn = st.text_input("Add New HSN Code", key="set_nhsn")
        if st.button("➕ Add New HSN", key="btn_set_hsn") and n_hsn:
            if n_hsn not in hsn_codes: hsn_codes.append(n_hsn); hsn_codes.sort(); settings["hsn_codes"] = hsn_codes; save_settings_to_sheet(settings); st.rerun()
