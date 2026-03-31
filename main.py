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
    "lh_label": "Low+High Speed Extra Charge",
    "gst_rates": [5, 12, 18, 28],
    "hsn_codes": [],
    "vis_mach": ['Date', 'Item Details', 'Final Price'],
    "vis_part": ['Date', 'HSN Code', 'Final Price']
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
            if "lh_label" not in data: data["lh_label"] = "Low+High Speed Extra Charge"
            if "vis_mach" not in data: data["vis_mach"] = ['Date', 'Item Details', 'Final Price']
            if "vis_part" not in data: data["vis_part"] = ['Date', 'HSN Code', 'Final Price']
            
            if 'New Final Price(Rs)' in data["vis_mach"]:
                data["vis_mach"] = [x if x != 'New Final Price(Rs)' else 'Final Price' for x in data["vis_mach"]]
            if 'New Final Price(Rs)' in data["vis_part"]:
                data["vis_part"] = [x if x != 'New Final Price(Rs)' else 'Final Price' for x in data["vis_part"]]
                
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
    try: 
        opts = json.loads(str(row.get('Options', '{}')))
    except: 
        pass
    
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
        
    lh_label = settings_dict.get('lh_label', 'Low+High Speed Extra Charge')
    addons = [k for k,v in opts.items() if k not in ['Basic', 'GST', 'HSN', 'ManualOldDate', 'ManualOldPrice', lh_label, 'Custom_Details', 'Is_Custom_Name', 'General_Note'] and isinstance(v, (int, float))]
    if addons:
        base += " + " + " + ".join(addons)
    return base

def get_item_details_str(row):
    opts = {}
    try: 
        opts = json.loads(str(row.get('Options', '{}')))
    except: 
        pass
    
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
        
    lh_label = settings.get('lh_label', 'Low+High Speed Extra Charge')
    addons = [k for k,v in opts.items() if k not in ['Basic', 'GST', 'HSN', 'ManualOldDate', 'ManualOldPrice', lh_label, 'Custom_Details', 'Is_Custom_Name', 'General_Note'] and isinstance(v, (int, float))]
    if addons:
        res += " + " + " + ".join(addons)
    return res

def prepare_display_df_with_history(df):
    if df.empty: return df
    df = df.copy()
    df['DateObj'] = pd.to_datetime(df['Date'], format="%d-%m-%Y", errors='coerce')
    df = df.sort_values('DateObj', ascending=False)

    basics, gsts, hsns = [], [], []
    old_dates, old_prices = [], []
    full_details, notes = [], []  

    for idx, row in df.iterrows():
        opts = {}
        try: 
            opts = json.loads(str(row.get('Options', '{}')))
        except: 
            pass
        
        m_old_date = opts.get('ManualOldDate', '-') if isinstance(opts, dict) else '-'
        m_old_price = opts.get('ManualOldPrice', '-') if isinstance(opts, dict) else '-'
        
        old_dates.append(m_old_date if m_old_date.strip() else "-")
        old_prices.append(m_old_price if str(m_old_price).strip() else "-")
        
        full_details.append(get_item_details_str(row))
        notes.append(opts.get('General_Note', '-') if isinstance(opts, dict) else '-')

        if str(row['Speed']) == 'Spare Part':
            b, g, h = get_spare_details(row.get('Options', '{}'), row.get('Total_Price', 0))
            basics.append(b)
            gsts.append(f"{g}%" if g > 0 else "-")
            hsns.append(h if h and h != "None" else "-")
        else:
            basics.append("-")
            gsts.append("-")
            hsns.append("-")
            
    df['Old Date'] = old_dates
    df['Old Price'] = old_prices
    df['HSN Code'] = hsns
    df['Basic Price'] = basics
    df['GST'] = gsts
    df['Item Details'] = full_details
    df['Note'] = notes 
    df['Final Price'] = df['Total_Price']
    
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

def create_dynamic_pdf(party, records_df, title_str, visible_cols, is_machine=True, orientation="Landscape (આડું)"):
    buffer = io.BytesIO()
    if "Portrait" in orientation:
        pagesize_selected = A4
    else:
        pagesize_selected = landscape(A4)
        
    width, height = pagesize_selected
    c = canvas.Canvas(buffer, pagesize=pagesize_selected)
    
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, height - 40, title_str)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, height - 60, f"Party Name: {party}")
    c.drawString(width - 150, height - 60, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    if not visible_cols: 
        c.drawString(40, height - 100, "No columns selected for PDF.")
        c.save()
        buffer.seek(0)
        return buffer

    vis_pdf_cols = ['Sr. No.'] + [col for col in visible_cols if col != 'Sr. No.']
    
    y = height - 90
    c.setFont("Helvetica-Bold", 10)
    start_x = 40
    end_x = width - 40
    avail_width = end_x - start_x
    
    col_widths = {'Sr. No.': 35, 'Date': 70, 'Party': 100, 'Old Date': 70, 'HSN Code': 60, 'Old Price': 80, 'Final Price': 100}
    
    has_item_details = 'Item Details' in vis_pdf_cols
    fixed_sum = sum([col_widths.get(col, 80) for col in vis_pdf_cols if col in col_widths])
    
    if has_item_details:
        col_widths['Item Details'] = max(100, avail_width - fixed_sum)
        final_avail = sum([col_widths.get(col, 80) for col in vis_pdf_cols])
    else:
        if fixed_sum > 0:
            scale_factor = avail_width / fixed_sum
            for col in vis_pdf_cols: 
                col_widths[col] = col_widths.get(col, 80) * scale_factor
        final_avail = avail_width
        
    cols = [start_x]
    for col in vis_pdf_cols: 
        cols.append(cols[-1] + col_widths.get(col, 80))
        
    row_y_top = y + 20
    row_y_bot = y - 5
    for i, col in enumerate(vis_pdf_cols):
        mid_x = (cols[i]+cols[i+1])/2.0
        if col == 'Item Details': 
            c.drawString(cols[i]+5, y+2, "Item Description / Details")
        else: 
            c.drawCentredString(mid_x, y+2, col)
            
    draw_grid_lines(c, row_y_top, row_y_bot, cols)
    y = row_y_bot

    enum_counter = 1
    
    for index, row in records_df.iterrows():
        total_price = int(row['Total_Price']) if pd.notna(row['Total_Price']) else 0
        opts = {}
        try: 
            opts = json.loads(str(row.get('Options', '{}')))
        except: 
            pass
        
        note_str = opts.get('General_Note', '').strip() if isinstance(opts, dict) else ''
        addons = []
        if is_machine and not opts.get('Is_Custom_Name', False):
            lh_label = settings.get('lh_label', 'Low+High Speed Extra Charge')
            addons = [k for k,v in opts.items() if k not in ['Basic', 'GST', 'HSN', 'ManualOldDate', 'ManualOldPrice', lh_label, 'Custom_Details', 'Is_Custom_Name', 'General_Note'] and isinstance(v, (int, float))]
            
        base_h = 25
        extra_h = 0
        if is_machine and has_item_details:
            extra_h += len(addons) * 15
        if note_str:
            extra_h += 15 
            
        needed_height = base_h + extra_h
            
        if y - needed_height < 50:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica-Bold", 10)
            row_y_top = y + 20
            row_y_bot = y - 5
            for i, col in enumerate(vis_pdf_cols):
                mid_x = (cols[i]+cols[i+1])/2.0
                if col == 'Item Details': 
                    c.drawString(cols[i]+5, y+2, "Item Description / Details")
                else: 
                    c.drawCentredString(mid_x, y+2, col)
            draw_grid_lines(c, row_y_top, row_y_bot, cols)
            y = row_y_bot

        row_y_top = y
        text_y = y - 15 
        c.setFont("Helvetica-Bold", 9)
        
        dt_val = str(row['Date']) if str(row['Date']) not in ["-", "nan", ""] else ""
        odt_val = str(row['Old Date']) if str(row['Old Date']) not in ["-", "nan", ""] else ""
        
        try:
            old_val = str(row['Old Price']).replace(',', '')
            old_price_str = f"{float(old_val):,.2f}"
        except:
            old_price_str = str(row['Old Price'])
        if old_price_str == "-" or old_price_str == "nan": old_price_str = ""
        
        try:
            total_price = float(row['Total_Price'])
        except:
            total_price = 0.0
        new_price_str = f"{total_price:,.2f}"
        
        hsn_str = str(row.get('HSN Code', '-'))[:8]
        party_str = str(row.get('Party', ''))[:15]
        
        max_drop = 10 
        
        for i, col in enumerate(vis_pdf_cols):
            mid_x = (cols[i]+cols[i+1])/2.0
            if col == 'Sr. No.': 
                c.drawCentredString(mid_x, text_y, str(enum_counter))
            elif col == 'Party': 
                c.drawCentredString(mid_x, text_y, party_str)
            elif col == 'Date': 
                c.drawCentredString(mid_x, text_y, dt_val)
            elif col == 'Old Date': 
                c.drawCentredString(mid_x, text_y, odt_val)
            elif col == 'HSN Code': 
                c.drawCentredString(mid_x, text_y, hsn_str)
            elif col == 'Old Price': 
                c.drawCentredString(mid_x, text_y, old_price_str)
            elif col == 'Final Price': 
                c.drawCentredString(mid_x, text_y, new_price_str)
            elif col == 'Item Details':
                c.setFont("Helvetica", 9)
                item_str = get_item_details_str(row)
                if not is_machine and "Basic Price" in row and "GST" in row:
                    try:
                        bp = float(row['Basic Price'])
                        item_str += f" (Basic: Rs.{bp:,.2f} | GST: {row['GST']})"
                    except:
                        item_str += f" (Basic: Rs.{row['Basic Price']} | GST: {row['GST']})"
                
                c.drawString(cols[i]+5, text_y, item_str)
                temp_y = text_y - 15
                
                if is_machine and not opts.get('Is_Custom_Name', False):
                    c.setFont("Helvetica-Oblique", 8)
                    for name in addons:
                        c.drawString(cols[i]+15, temp_y, f"• Add-on: {name}")
                        temp_y -= 15
                        
                max_drop = max(max_drop, (text_y - temp_y))
                c.setFont("Helvetica-Bold", 9)
                
        grid_y_bot = text_y - max_drop - 5
        draw_grid_lines(c, row_y_top, grid_y_bot, cols)
        
        current_y = grid_y_bot
        if note_str:
            c.setFont("Helvetica-Oblique", 9)
            id_idx = vis_pdf_cols.index('Item Details') if has_item_details else 1
            indent_x = cols[id_idx] + 5
            c.drawString(indent_x, current_y - 12, f"Note: {note_str}")
            current_y -= 18 

        y = current_y
        enum_counter += 1
        
    c.save()
    buffer.seek(0)
    return buffer

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
    c.drawString(cols[0], height - 60, f"Material: {raw_material} | Part: {search_part}")
    c.drawString(cols[4], height - 60, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    
    y = height - 100
    c.setFont("Helvetica-Bold", 9)
    row_y_top = y + 20
    row_y_bot = y - 5
    headers = ["Date", "Raw Material", "Part Name", "Cut Size", "Final Size", "Qty", "Date"]
    for i,h in enumerate(headers): 
        c.drawCentredString((cols[i]+cols[i+1])/2.0, y+2, h)
    draw_grid_lines(c, row_y_top, row_y_bot, cols)
    y = row_y_bot
    
    for index, row in df.iterrows():
        if y - 25 < 50:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica-Bold", 9)
            row_y_top = y+20
            row_y_bot = y-5
            for i,h in enumerate(headers): 
                c.drawCentredString((cols[i]+cols[i+1])/2.0, y+2, h)
            draw_grid_lines(c, row_y_top, row_y_bot, cols)
            y = row_y_bot
            
        row_y_top = y
        text_y = y - 15
        c.setFont("Helvetica", 8)
        c.drawCentredString((cols[0]+cols[1])/2.0, text_y, str(row['Date'])[:10])
        c.drawString(cols[1]+5, text_y, str(row['Raw Material']))
        c.drawString(cols[2]+5, text_y, str(row['Part Name']))
        c.drawCentredString((cols[3]+cols[4])/2.0, text_y, str(row['Cutting Size']))
        f_sz = str(row.get('Final Size', ''))
        c.drawCentredString((cols[4]+cols[5])/2.0, text_y, f_sz if f_sz not in ['nan','','-'] else '')
        c.drawCentredString((cols[5]+cols[6])/2.0, text_y, str(row['Quantity']))
        row_y_bot = text_y - 5
        draw_grid_lines(c, row_y_top, row_y_bot, cols)
        y = row_y_bot
        
    c.save()
    buffer.seek(0)
    return buffer

def create_hexo_pdf(mat_name, mat_in, mat_out, balance_mm, df):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, 800, "Surgicraft Godown Balance & Cutting Report")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 775, f"Material: {mat_name}")
    c.drawString(400, 775, f"Date: {datetime.now().strftime('%d-%m-%Y')}")
    c.setFont("Helvetica", 10)
    c.drawString(40, 755, f"📥 Total In: {mm_to_foot_inch(mat_in)}")
    c.drawString(40, 740, f"✂️ Total Out: {mm_to_foot_inch(mat_out)}")
    c.setFillColorRGB(0, 0.5, 0)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, 720, f"✅ Balance: {mm_to_foot_inch(balance_mm)} ({balance_mm:.1f} MM)")
    c.setFillColorRGB(0, 0, 0)
    
    y = 690
    c.setFont("Helvetica-Bold", 10)
    cols = [40, 105, 195, 255, 345, 550]
    row_y_top = y + 20
    row_y_bot = y - 5
    hs = ["Date", "Cut Size", "Qty", "Blade Margin", "Total Used (MM)"]
    for i,h in enumerate(hs): 
        c.drawCentredString((cols[i]+cols[i+1])/2.0, y+2, h)
    draw_grid_lines(c, row_y_top, row_y_bot, cols)
    y = row_y_bot
    
    for index, row in df.iterrows():
        if y - 25 < 50:
            c.showPage()
            y = 800
            c.setFont("Helvetica-Bold", 10)
            row_y_top = y+20
            row_y_bot = y-5
            for i,h in enumerate(hs): 
                c.drawCentredString((cols[i]+cols[i+1])/2.0, y+2, h)
            draw_grid_lines(c, row_y_top, row_y_bot, cols)
            y = row_y_bot
            
        row_y_top = y
        text_y = y - 15
        c.setFont("Helvetica", 9)
        c.drawCentredString((cols[0]+cols[1])/2.0, text_y, str(row['Date'])[:10])
        c.drawCentredString((cols[1]+cols[2])/2.0, text_y, str(row['Cut Size']))
        c.drawCentredString((cols[2]+cols[3])/2.0, text_y, str(row['Quantity']))
        c.drawCentredString((cols[3]+cols[4])/2.0, text_y, str(row['Blade Margin (MM)']))
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(cols[5]-10, text_y, f"{float(row['Total Used (MM)']):.1f}")
        row_y_bot = text_y - 5
        draw_grid_lines(c, row_y_top, row_y_bot, cols)
        y = row_y_bot
        
    c.save()
    buffer.seek(0)
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
    if alert_list: st.error(f"🚨 **ALERT!** 5 Foot thi occho stock: **{', '.join(alert_list)}**")
    st.write("### 🪚 Hexo Cutting & Live Balance Dashboard")
    htab1, htab2, htab3, htab4 = st.tabs(["✂️ Cutting Entry", "📥 Navo Maal Aavyo", "📊 Godown Search", "✏️ Edit / Delete"])
    with htab1:
        c1, c2 = st.columns(2)
        mat_sel = c1.selectbox("Material:", ["-- Select --", "-- New --"] + stock_materials_full, key="mat_sel_hexo")
        cut_mat = c1.text_input("📝 New Name:", key="new_mat_hexo") if mat_sel == "-- New --" else mat_sel
        sc1, sc2 = st.columns(2)
        cut_size_str = sc1.text_input("Size:", key="cut_size_hexo")
        cut_unit = sc2.selectbox("Unit:", ["MM", "Inch", "Foot"], key="unit_hexo")
        c3, c4 = st.columns(2)
        cut_qty = c3.number_input("Qty (Nang):", min_value=1, key="qty_hexo")
        blade_margin = c4.number_input("Margin:", value=1.5, step=0.1, key="margin_hexo")
        rod_foot = st.number_input("Standard Ladi (Foot):", min_value=0.0, value=0.0, key="rod_hexo")
        if cut_size_str and cut_mat and cut_mat != "-- Select --":
            size_val = parse_smart_size(cut_size_str)
            if size_val > 0 and cut_qty > 0:
                size_in_mm = convert_to_mm(size_val, cut_unit)
                total_used_mm = (size_in_mm + blade_margin) * cut_qty
                cur_in = pd.to_numeric(stock_df[stock_df['Material Name'] == cut_mat]['Total Length (MM)'], errors='coerce').fillna(0).sum() if not stock_df.empty else 0
                cur_out = pd.to_numeric(hexo_df[hexo_df['Material Name'] == cut_mat]['Total Used (MM)'], errors='coerce').fillna(0).sum() if not hexo_df.empty else 0
                cur_bal = cur_in - cur_out
                new_bal = cur_bal - total_used_mm
                st.info(f"👉 **Jarur:** {mm_to_foot_inch(total_used_mm)} total maal.")
                st.info(f"👉 **Balance:** {mm_to_foot_inch(cur_bal)} -> **{mm_to_foot_inch(new_bal)}** vadhse.")
                if rod_foot > 0:
                    rod_mm = rod_foot * 304.8
                    rods_needed = math.ceil(total_used_mm / rod_mm)
                    wastage = (rods_needed * rod_mm) - total_used_mm
                    st.success(f"📌 **Saliya:** **{rods_needed} aakha saliya** ({mm_to_foot_inch(wastage)} wastage).")
                if st.button("✂️ Kapi Nakho", type="primary", key="btn_save_hexo"):
                    dt_str = datetime.now().strftime("%d-%m-%Y")
                    if mat_sel == "-- New --" and cut_mat not in stock_materials_full: 
                        sheet_stock.append_row([dt_str, cut_mat.strip(), 0, 0, 0])
                    sheet_hexo.append_row([dt_str, cut_mat.strip(), f'{cut_size_str} {cut_unit}', cut_qty, blade_margin, total_used_mm])
                    st.success("Cutting saved!")
                    clear_all_caches()
                    st.rerun()
    with htab2:
        new_mat_name = st.text_input("Raw Material Name:", key="new_stock_name")
        col_v, col_u, col_k = st.columns(3)
        in_val_str = col_v.text_input("Length:", key="new_stock_len")
        in_unit = col_u.selectbox("Unit:", ["Foot", "Inch", "MM"], key="new_stock_unit")
        weight_kg = col_k.number_input("Weight (KG):", key="new_stock_weight")
        if st.button("💾 Save Stock", type="primary", key="btn_save_stock"):
            in_val = parse_smart_size(in_val_str) if in_val_str else 0
            if not new_mat_name or in_val <= 0: 
                st.warning("Enter name and length!")
            else:
                total_mm = convert_to_mm(in_val, in_unit)
                total_foot = total_mm / 304.8
                sheet_stock.append_row([datetime.now().strftime("%d-%m-%Y"), new_mat_name.strip(), total_foot, total_mm, weight_kg])
                st.toast("Saved!")
                clear_all_caches()
                st.rerun()
    with htab3:
        search_txt = st.text_input("🔍 Search:", key="search_hexo_pdf")
        if not stock_df.empty:
            filtered_mats = [m for m in stock_materials_full if search_txt.lower() in m.lower()] if search_txt else stock_materials_full
            for mat in filtered_mats:
                mat_in = pd.to_numeric(stock_df[stock_df['Material Name'] == mat]['Total Length (MM)'], errors='coerce').fillna(0).sum()
                mat_hexo_df = hexo_df[hexo_df['Material Name'] == mat] if not hexo_df.empty else pd.DataFrame()
                mat_out = pd.to_numeric(mat_hexo_df['Total Used (MM)'], errors='coerce').fillna(0).sum() if not mat_hexo_df.empty else 0
                bal_mm = mat_in - mat_out
                with st.expander(f"📦 {mat} | Bal: {mm_to_foot_inch(bal_mm)}", expanded=(len(filtered_mats)==1)):
                    sc1, sc2, sc3 = st.columns(3)
                    sc1.metric("Total In", mm_to_foot_inch(mat_in))
                    sc2.metric("Total Out", mm_to_foot_inch(mat_out))
                    sc3.metric("Live Balance", mm_to_foot_inch(bal_mm))
                    if not mat_hexo_df.empty:
                        st.dataframe(mat_hexo_df[['Date', 'Cut Size', 'Quantity', 'Total Used (MM)']], use_container_width=True, hide_index=True)
                        pdf_buf = create_hexo_pdf(mat, mat_in, mat_out, bal_mm, mat_hexo_df)
                        c_dl, c_pv = st.columns(2)
                        with c_dl: 
                            st.download_button("📥 PDF", data=pdf_buf, file_name=f"{mat}_Report.pdf", use_container_width=True, key=f"dl_{mat}")
                        with c_pv: 
                            if st.button(f"👁️ Preview", key=f"pv_{mat}", use_container_width=True): 
                                display_pdf_in_app(pdf_buf)
    with htab4:
        edit_type = st.radio("Edit?", ["Cutting", "Stock"], horizontal=True, key="edit_type_radio")
        if edit_type == "Cutting":
            if hexo_df.empty: 
                st.info("No records found.") # <-- અહીંયા તમારો કોડ કપાઈ ગયો હતો, મેં તેને વ્યવસ્થિત રીતે પૂરો કરી દીધો છે.
