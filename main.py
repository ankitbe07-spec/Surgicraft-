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
                st.info("No records.")
            else:
                h_df = hexo_df.copy()
                h_df['Display'] = h_df['Date'].astype(str) + " | " + h_df['Material Name'].astype(str) + " | Size: " + h_df['Cut Size'].astype(str)
                sel_h = st.selectbox("Select Cutting:", h_df['Display'].tolist(), key="edit_hexo_sel")
                if sel_h:
                    r_d = h_df[h_df['Display'] == sel_h].iloc[0]
                    ks = str(hash(sel_h))
                    e1, e2 = st.columns(2)
                    c_mat_i = stock_materials_full.index(str(r_d['Material Name'])) if str(r_d['Material Name']) in stock_materials_full else 0
                    n_mat = e1.selectbox("Edit Material:", stock_materials_full, index=c_mat_i, key=f"eh_mat_{ks}")
                    o_sz = str(r_d['Cut Size'])
                    o_ut = "MM"
                    o_val_s = o_sz.strip()
                    if "Inch" in o_sz: 
                        o_ut = "Inch"
                        o_val_s = o_sz.replace('Inch','').strip()
                    elif "Foot" in o_sz: 
                        o_ut = "Foot"
                        o_val_s = o_sz.replace('Foot','').strip()
                    elif "MM" in o_sz: 
                        o_ut = "MM"
                        o_val_s = o_sz.replace('MM','').strip()
                    es1, es2 = st.columns(2)
                    n_cut = es1.text_input("Edit Size:", value=o_val_s, key=f"eh_size_{ks}")
                    n_unit = es2.selectbox("Unit:", ["MM", "Inch", "Foot"], index=["MM", "Inch", "Foot"].index(o_ut), key=f"eh_unit_{ks}")
                    e3, e4 = st.columns(2)
                    n_qty = e3.number_input("Qty:", value=safe_int(r_d['Quantity'], 1), key=f"eh_qty_{ks}")
                    n_margin = e4.number_input("Margin:", value=safe_float(r_d['Blade Margin (MM)'], 1.5), key=f"eh_margin_{ks}")
                    b1, b2 = st.columns(2)
                    if b1.button("💾 Update", key=f"btn_upd_h_{ks}"):
                        n_val = parse_smart_size(n_cut)
                        if n_val > 0:
                            n_mm = convert_to_mm(n_val, n_unit)
                            n_total = (n_mm + n_margin) * n_qty
                            for i, r in enumerate(sheet_hexo.get_all_values()):
                                if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[2]) == str(r_d['Cut Size']):
                                    sheet_hexo.update(f"B{i+1}:F{i+1}", [[n_mat, f"{n_cut} {n_unit}", n_qty, n_margin, n_total]])
                                    st.success("Updated!")
                                    clear_all_caches()
                                    st.rerun()
                                    break
                    if b2.button("❌ Delete", key=f"btn_del_h_{ks}"):
                        for i, r in enumerate(sheet_hexo.get_all_values()):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']) and str(r[2]) == str(r_d['Cut Size']):
                                sheet_hexo.delete_rows(i+1)
                                st.success("Deleted!")
                                clear_all_caches()
                                st.rerun()
                                break
        else:
            if stock_df.empty: 
                st.info("No records.")
            else:
                s_df = stock_df.copy()
                s_df['Display'] = s_df['Date'].astype(str) + " | " + s_df['Material Name'].astype(str)
                sel_s = st.selectbox("Select Stock:", s_df['Display'].tolist(), key="edit_stock_sel")
                if sel_s:
                    r_d = s_df[s_df['Display'] == sel_s].iloc[0]
                    ks = str(hash(sel_s))
                    e1, e2 = st.columns(2)
                    n_mat = e1.text_input("Name:", value=str(r_d['Material Name']), key=f"es_mat_{ks}")
                    n_wt = e2.number_input("Weight:", value=safe_float(r_d.get('Weight (KG)', 0.0)), key=f"es_wt_{ks}")
                    es1, es2 = st.columns(2)
                    n_len = es1.text_input("Add Length (Opt):", key=f"es_len_{ks}")
                    n_unit = es2.selectbox("Unit:", ["Foot", "Inch", "MM"], key=f"es_unit_{ks}")
                    b1, b2 = st.columns(2)
                    if b1.button("💾 Update", key=f"btn_upd_s_{ks}"):
                        n_total_mm = float(r_d['Total Length (MM)'])
                        n_total_ft = float(r_d['Total Length (Foot)'])
                        if n_len:
                            n_val = parse_smart_size(n_len)
                            if n_val > 0: 
                                n_total_mm = convert_to_mm(n_val, n_unit)
                                n_total_ft = n_total_mm / 304.8
                        for i, r in enumerate(sheet_stock.get_all_values()):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']):
                                sheet_stock.update(f"B{i+1}:E{i+1}", [[n_mat, n_total_ft, n_total_mm, n_wt]])
                                st.success("Updated!")
                                clear_all_caches()
                                st.rerun()
                                break
                    if b2.button("❌ Delete", key=f"btn_del_s_{ks}"):
                        for i, r in enumerate(sheet_stock.get_all_values()):
                            if i > 0 and r[0] == str(r_d['Date']) and r[1] == str(r_d['Material Name']):
                                sheet_stock.delete_rows(i+1)
                                st.success("Deleted!")
                                clear_all_caches()
                                st.rerun()
                                break

# ==========================================
# 2. FACTORY PARTS & CUTTING MANAGER 
# ==========================================
elif menu == "✂️ Factory Parts & Cutting":
    display_header()
    st.write("### Factory Production & Cutting Manager")
    tabA, tabB, tabC = st.tabs(["➕ Add Record", "🔍 Search & Report", "✏️ Edit / Delete"])
    with tabA:
        c01, c02 = st.columns(2)
        rec_date = c01.date_input("Date:", datetime.today(), key="fac_date")
        c1, c2 = st.columns(2)
        raw_sel = c1.selectbox("Material:", ["-- Empty --", "-- New --"] + unique_materials, key="fac_raw_sel")
        raw_val = c1.text_input("New Name:", key="fac_new_raw") if raw_sel == "-- New --" else raw_sel
        part_sel = c2.selectbox("Part Name:", ["-- New --"] + unique_factory_parts, key="fac_part_sel")
        part_val = c2.text_input("New Part:", key="fac_new_part") if part_sel == "-- New --" else part_sel
        c3, c4, c5 = st.columns([1.5, 1.5, 1])
        cut_size = c3.text_input("Cut Size", key="fac_cut_sz")
        final_size = c4.text_input("Final Size", key="fac_fin_sz")
        qty = c5.number_input("Qty", min_value=1, key="fac_qty")
        if st.button("💾 Save", type="primary", key="btn_save_fac"):
            if not part_val or part_val == "-- New --" or not cut_size: 
                st.warning("Name & Cut Size compulsory!")
                st.stop()
            sheet_factory.append_row([rec_date.strftime("%d-%m-%Y"), raw_val if raw_val != "-- Empty --" else "-", part_val.strip(), cut_size.strip(), final_size.strip() if final_size else "-", int(qty)])
            st.toast("Saved!")
            clear_all_caches()
            st.rerun()
    with tabB:
        skw = st.text_input("🔍 Search:", key="search_fac")
        c1, c2 = st.columns(2)
        search_raw = c1.selectbox("Filter Material:", ["-- All --"] + unique_materials, key="search_fac_raw")
        search_part = c2.selectbox("Filter Part:", ["-- All --"] + unique_factory_parts, key="search_fac_part")
        f_df = factory_df.copy()
        if not f_df.empty:
            if search_raw != "-- All --": 
                f_df = f_df[f_df['Raw Material'].astype(str).str.strip() == search_raw]
            if search_part != "-- All --": 
                f_df = f_df[f_df['Part Name'].astype(str).str.strip() == search_part]
            if skw: 
                f_df = f_df[f_df[['Raw Material', 'Part Name', 'Cutting Size']].astype(str).apply(lambda x: x.str.contains(skw, case=False)).any(axis=1)]
            st.dataframe(f_df, use_container_width=True, hide_index=True)
            tqty = pd.to_numeric(f_df['Quantity'], errors='coerce').fillna(0).sum()
            st.success(f"**Total Qty: {int(tqty)}**")
            st.write("---")
            pdf_fmt = st.radio("PDF Format:", ["Landscape (આડું)", "Portrait (ઊભું)"], horizontal=True, key="fac_pdf_format")
            f_pdf = create_factory_pdf(search_raw, search_part, f_df, pdf_fmt)
            c1, c2 = st.columns(2)
            with c1: 
                st.download_button("📥 PDF", data=f_pdf, file_name="Factory_List.pdf", use_container_width=True, key="dl_fac_pdf")
            with c2: 
                if st.button("👁️ Preview", use_container_width=True, key="pv_fac_pdf"): 
                    display_pdf_in_app(f_pdf)
    with tabC:
        if factory_df.empty: 
            st.info("No records.")
        else:
            e_df = factory_df.copy()
            e_df['Final Size'] = e_df.get('Final Size', '')
            e_df['Display'] = e_df['Date'].astype(str) + " | " + e_df['Part Name'].astype(str) + " | " + e_df['Cutting Size'].astype(str)
            sel_r = st.selectbox("Select Record:", e_df['Display'].tolist(), key="edit_fac_sel")
            if sel_r:
                r_d = e_df[e_df['Display'] == sel_r].iloc[0]
                ks = str(hash(sel_r))
                e_d = st.date_input("Date:", safe_date(str(r_d['Date'])), key=f"ef_date_{ks}")
                e1, e2 = st.columns(2)
                n_raw = e1.text_input("Material:", value=str(r_d['Raw Material']), key=f"ef_raw_{ks}")
                n_prt = e2.text_input("Part:", value=str(r_d['Part Name']), key=f"ef_part_{ks}")
                e3, e4, e5 = st.columns([1.5, 1.5, 1])
                n_cut = e3.text_input("Cut Size:", value=str(r_d['Cutting Size']), key=f"ef_cut_{ks}")
                n_fin = e4.text_input("Final Size:", value=str(r_d.get('Final Size', '')), key=f"ef_fin_{ks}")
                n_qty = e5.number_input("Qty:", value=safe_int(r_d.get('Quantity', 1), 1), min_value=1, key=f"ef_qty_{ks}")
                b1, b2 = st.columns(2)
                if b1.button("💾 Update", key=f"btn_upd_f_{ks}"):
                    sheet_factory.delete_rows(factory_df[factory_df.index == r_d.name].index[0]+2) 
                    sheet_factory.append_row([e_d.strftime("%d-%m-%Y"), n_raw, n_prt, n_cut, n_fin if n_fin else "-", n_qty])
                    st.success("Updated!")
                    clear_all_caches()
                    st.rerun()
                if b2.button("❌ Delete", key=f"btn_del_f_{ks}"):
                    sheet_factory.delete_rows(factory_df[factory_df.index == r_d.name].index[0]+2)
                    st.success("Deleted!")
                    clear_all_caches()
                    st.rerun()

# ==========================================
# 3. ADD NEW ENTRY PAGE
# ==========================================
elif menu == "➕ Add New Entry":
    display_header()
    party_sel = st.selectbox("Select Party:", ["-- New --"] + unique_parties_list, key="add_party_sel")
    party_name = st.text_input("New Party Name:", key="add_party_new") if party_sel == "-- New --" else party_sel
    
    if party_name and party_name != "-- New --" and not main_df.empty:
        party_hist = main_df[main_df['Party'].astype(str).str.strip().str.title() == party_name.strip().title()].copy()
        if not party_hist.empty:
            st.markdown(f"📜 **{party_name} Old Record:**")
            p_hist_proc = prepare_display_df_with_history(party_hist)
            disp_h = p_hist_proc[['Date', 'Item Details', 'Final Price']].reset_index(drop=True)
            disp_h.index = range(1, len(disp_h)+1)
            styled_h = disp_h.style.format({'Final Price': "{:,.2f}"}).set_properties(subset=['Final Price'], **{'text-align': 'center'})
            st.dataframe(styled_h, use_container_width=True)
            
    st.write("---")
    entry_type = st.radio("Add What?", ["Machine", "Spare Part / Custom"], horizontal=True, key="add_entry_type")
    
    if entry_type == "Machine":
        c1, c2, c3 = st.columns(3)
        ws = sorted(list(set([k.split('x')[0] for k in settings['prices'].keys()])))
        w_val = c1.selectbox("Width", ws, key="add_w")
        ls = sorted(list(set([k.split('x')[1] for k in settings['prices'].keys()])))
        l_val = c2.selectbox("Length", ls, key="add_l")
        speed = c3.selectbox("Speed", ["-- None --", "Low", "High", "Low+High"], key="add_speed")
        cust_dtl = st.text_input("Custom Machine Details (Join in Name):", placeholder="e.g. Double Door + V.Pump", key="add_cust_dtl")
        
        st.write("### Add-ons")
        cls = st.columns(3)
        sel_ads, ads_struct, ci = [], {}, 0
        lhl = settings.get('lh_label', 'Low+High Speed Extra Charge')
        if speed == "Low+High": 
            ads_struct[lhl] = settings['addons'].get(lhl, 0)
        if cust_dtl.strip(): 
            ads_struct["Custom_Details"] = cust_dtl.strip()
        for an in settings['addons']:
            if an == lhl: continue
            if cls[ci%3].checkbox(an, key=f"chk_{an}"): 
                ads_struct[an] = settings['addons'][an]
            ci += 1
            
        base_p = int(settings['prices'].get(f"{w_val}x{l_val}", 0))
        calc_t = base_p + sum([v for k,v in ads_struct.items() if isinstance(v, (int, float))])
        st.info(f"💡 Idea Price: Rs. {calc_t:,.2f}")
        final_t = st.number_input("Final Machine Price:", value=calc_t, key="btn_add_manual_price")
        
        gen_note = st.text_area("🗒️ General Note / Remarks (Optional - Visible below item in PDF):", key="add_mach_note")
        if gen_note.strip(): 
            ads_struct["General_Note"] = gen_note.strip()
        
        if st.button("➕ SAVE MACHINE", type="primary", key="btn_add_entry"):
            if not party_name: 
                st.warning("Party Name compulsory!")
            else:
                speed_val_to_save = "-" if speed == "-- None --" else speed
                sheet_main.append_row([st.session_state.q_no, party_name.strip().title(), datetime.now().strftime("%d-%m-%Y"), f"{w_val}x{l_val}", speed_val_to_save, json.dumps(ads_struct), final_t])
                st.toast("Saved!")
                clear_all_caches()
                st.rerun()

    else:
        st.write("### Spare Part Details")
        c1, c2 = st.columns(2)
        ps = st.selectbox("Select Part:", ["-- New --"] + unique_parts_list, key="add_sp_sel")
        p_name = st.text_input("New Part Name:", key="add_sp_new") if ps == "-- New --" else ps
        basic_p = c2.number_input("Basic Price:", key="add_sp_price")
        c3, c4 = st.columns(2)
        hsnl = ["None"] + sorted(settings.get("hsn_codes", []))
        hsns = c3.selectbox("HSN Code:", ["-- New --"] + hsnl, key="add_sp_hsn_sel")
        hsn_v = c3.text_input("📝 New HSN:", key="add_sp_hsn_new") if hsns == "-- New --" else hsns
        
        gst_r = c4.selectbox("GST (%)", [0] + sorted(settings.get("gst_rates", [])), key="add_sp_gst")
        
        final_c = basic_p + (basic_p * gst_r / 100)
        st.info(f"**Final: Rs. {final_c:,.2f}**")
        
        gen_note_sp = st.text_area("🗒️ General Note / Remarks (Optional - Visible below item in PDF):", key="add_sp_note")
        opts_sp = {"Basic": basic_p, "GST": gst_r, "HSN": hsn_v if hsn_v!="None" else "-"}
        if gen_note_sp.strip(): 
            opts_sp["General_Note"] = gen_note_sp.strip()
        
        if st.button("➕ SAVE PART", type="primary", key="btn_add_part"):
            if not party_name or not p_name or p_name=="-- New --": 
                st.warning("Enter Name!")
                st.stop()
            sheet_main.append_row([st.session_state.q_no, party_name.strip().title(), datetime.now().strftime("%d-%m-%Y"), p_name.strip(), "Spare Part", json.dumps(opts_sp), final_c])
            st.toast("Saved!")
            clear_all_caches()
            st.rerun()

# ==========================================
# 4. PARTY HISTORY & EDIT PAGE 
# ==========================================
elif menu == "📜 Party History & Edit":
    display_header()
    if main_df.empty: 
        st.info("No records.")
    else:
        df = main_df.copy()
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        tab1, tab2, tab3, tab4 = st.tabs(["📜 PDF / View", "✏️ Edit Record", "❌ Delete", "📋 Copy Party"])
        
        with tab1:
            pdf_p = st.selectbox("Select Party:", ["-- Select --"] + unique_parties_list, key="view_party_sel")
            if pdf_p != "-- Select --":
                p_df = prepare_display_df_with_history(df[df['Clean_Party'] == pdf_p])
                skw = st.text_input("🔍 Search Item/Note:", key="search_hist_party")
                if skw: 
                    p_df = p_df[p_df.astype(str).apply(lambda x: x.str.contains(skw, case=False)).any(axis=1)]
                
                if p_df.empty: 
                    st.warning("No matches.")
                else:
                    mach_cols_all = ['Date', 'Old Date', 'Item Details', 'Old Price', 'Final Price', 'Note']
                    part_cols_all = ['Date', 'Old Date', 'Item Details', 'HSN Code', 'Old Price', 'Final Price', 'Note']
                    saved_mach = settings.get('vis_mach', ['Date','Item Details','Final Price'])
                    saved_part = settings.get('vis_part', ['Date','HSN Code','Final Price'])
                    c_m, c_p = st.columns(2)
                    sel_mach = c_m.multiselect("Machine Columns:", mach_cols_all, default=[c for c in saved_mach if c in mach_cols_all], key="ms_mach")
                    sel_part = c_p.multiselect("Parts Columns:", part_cols_all, default=[c for c in saved_part if c in part_cols_all], key="ms_part")
                    
                    if set(sel_mach) != set(saved_mach) or set(sel_part) != set(saved_part):
                        settings['vis_mach'] = sel_mach
                        settings['vis_part'] = sel_part
                        save_settings_to_sheet(settings)
                        st.toast("Saved! ✅")
                    
                    st.write("---")
                    pdf_fmt_hist = st.radio("📄 PDF Design Format:", ["Landscape (આડું)", "Portrait (ઊભું)"], horizontal=True, key="hist_pdf_format")
                    
                    col1, col2 = st.columns(2)
                    m_records = p_df[p_df['Speed'] != 'Spare Part']
                    with col1:
                        if not m_records.empty:
                            st.write(f"### ⚙️ Machine Records ({len(m_records)})")
                            md = m_records[sel_mach].copy() if sel_mach else pd.DataFrame()
                            md.insert(0, 'Sr. No.', range(1, len(md)+1))
                            if 'Final Price' in md.columns: 
                                styled_m = md.style.format({'Final Price': "{:,.2f}"}).set_properties(subset=['Final Price'], **{'text-align': 'center'})
                                st.dataframe(styled_m, use_container_width=True, hide_index=True)
                            else: 
                                st.dataframe(md, use_container_width=True, hide_index=True)
                            
                            m_pdf = create_dynamic_pdf(pdf_p, m_records, "HHP Machine Price List (GST Extra) HSN 8419", sel_mach, True, orientation=pdf_fmt_hist)
                            c_dl_m, c_pv_m = st.columns(2)
                            with c_dl_m:
                                st.download_button("📥 PDF", data=m_pdf, file_name=f"{pdf_p}_Machines.pdf", use_container_width=True)
                            with c_pv_m:
                                if st.button("👁️ Preview", use_container_width=True, key="pv_mach_hist"):
                                    display_pdf_in_app(m_pdf)
                        else: 
                            st.info("No machines.")
                            
                    p_records = p_df[p_df['Speed'] == 'Spare Part']
                    with col2:
                        if not p_records.empty:
                            st.write(f"### 🔧 Spare Parts Records ({len(p_records)})")
                            pd_d = p_records[sel_part].copy() if sel_part else pd.DataFrame()
                            pd_d.insert(0, 'Sr. No.', range(1, len(pd_d)+1))
                            if 'Final Price' in pd_d.columns: 
                                styled_p = pd_d.style.format({'Final Price': "{:,.2f}"}).set_properties(subset=['Final Price'], **{'text-align': 'center'})
                                st.dataframe(styled_p, use_container_width=True, hide_index=True)
                            else: 
                                st.dataframe(pd_d, use_container_width=True, hide_index=True)
                            
                            p_pdf = create_dynamic_pdf(pdf_p, p_records, "Spare Parts Price List", sel_part, False, orientation=pdf_fmt_hist)
                            c_dl_p, c_pv_p = st.columns(2)
                            with c_dl_p:
                                st.download_button("📥 PDF", data=p_pdf, file_name=f"{pdf_p}_Parts.pdf", use_container_width=True)
                            with c_pv_p:
                                if st.button("👁️ Preview", use_container_width=True, key="pv_part_hist"):
                                    display_pdf_in_app(p_pdf)
                        else: 
                            st.info("No parts.")

        with tab2:
            edit_p = st.selectbox("Select Party (Edit):", ["-- Select --"] + unique_parties_list, key="edit_hist_party")
            if edit_p != "-- Select --":
                p_items = prepare_display_df_with_history(df[df['Clean_Party'] == edit_p])
                p_items['Display'] = p_items.apply(make_full_display_name, axis=1)
                sel_i = st.selectbox("Select Item:", p_items['Display'].tolist(), key="edit_hist_item")
                if sel_i:
                    r_d = p_items[p_items['Display'] == sel_i].iloc[0]
                    is_sp = (str(r_d['Speed']) == 'Spare Part')
                    ks = str(hash(sel_i))
                    st.write("---")
                    e1, e2 = st.columns(2)
                    n_pn = e1.text_input("Party (Transfer):", value=str(r_d['Party']), key=f"eh_pname_{ks}")
                    n_item = e2.text_input("Item Name (Edit Full):", value=get_raw_full_name(r_d, settings), key=f"eh_iname_{ks}")
                    
                    opts_d = {}
                    try: 
                        opts_d = json.loads(str(r_d.get('Options', '{}'))) 
                    except: 
                        pass
                        
                    st.write("**Date/Price:**")
                    d1, d2 = st.columns(2)
                    n_nd = d1.text_input("New Date:", value=str(r_d['Date']), key=f"eh_nd_{ks}")
                    n_od = d2.text_input("Old Date:", value=str(r_d.get('Old Date','-')), key=f"eh_od_{ks}")
                    d3, d4 = st.columns(2)
                    n_op = d3.text_input("Old Price:", value=str(r_d.get('Old Price','')), key=f"eh_op_{ks}")
                    n_note = st.text_area("🗒️ Note / Remarks:", value=opts_d.get('General_Note', ''), key=f"eh_note_{ks}")
                    
                    if is_sp:
                        o_basic, o_gst, o_hsn = get_spare_details(r_d.get('Options', '{}'), r_d['Total_Price'])
                        n_basic = st.number_input("Basic:", value=safe_int(o_basic, 0), key=f"eh_sp_{ks}")
                        c1, c2 = st.columns(2)
                        hsnl = ["None"] + sorted(settings.get("hsn_codes", []))
                        if o_hsn and o_hsn not in hsnl and o_hsn!="-": 
                            hsnl.append(o_hsn)
                        hsns = c1.selectbox("Edit HSN:", ["-- New --"] + hsnl, index=hsnl.index(o_hsn)+1 if o_hsn in hsnl else 0, key=f"eh_hsns_{ks}")
                        n_hsn = c1.text_input("New HSN:", value=o_hsn if hsns=="-- New --" else "", key=f"eh_hsnn_{ks}") if hsns=="-- New --" else hsns
                        
                        safe_gst_rates = sorted(settings.get("gst_rates", []))
                        gst_idx = safe_gst_rates.index(o_gst) + 1 if o_gst in safe_gst_rates else 0
                        n_gst = c2.selectbox("GST:", [0] + safe_gst_rates, index=gst_idx, key=f"eh_gst_{ks}")
                        
                        n_price = d4.number_input("Final Price:", value=int(n_basic + (n_basic*n_gst/100)), key=f"eh_spf_{ks}")
                    else: 
                        n_price = d4.number_input("Final Price:", value=safe_int(r_d['Total_Price'], 0), key=f"eh_mf_{ks}")
                    
                    if st.button("💾 Update", type="primary", key=f"btn_upd_h_{ks}"):
                        if not n_pn: 
                            st.warning("Party compulsory!")
                            st.stop()
                        opts_d['ManualOldDate'] = n_od.strip() if n_od.strip() else "-"
                        opts_d['ManualOldPrice'] = n_op.strip() if n_op.strip() else "-"
                        opts_d['Is_Custom_Name'] = True
                        if is_sp: 
                            opts_d['HSN'] = n_hsn if n_hsn and n_hsn!="None" else "-"
                            opts_d['Basic'] = n_basic
                            opts_d['GST'] = n_gst
                            
                        if n_note.strip(): 
                            opts_d["General_Note"] = n_note.strip()
                        elif "General_Note" in opts_d: 
                            del opts_d["General_Note"] 
                            
                        all_vals = sheet_main.get_all_values()
                        for i, r in enumerate(all_vals):
                            if i > 0 and r[1].strip().title() == edit_p and str(r[2]).strip() == str(r_d['Date']).strip() and str(r[3]).strip() == str(r_d['Size']).strip():
                                ridx = i + 1
                                sheet_main.update_cell(ridx, 2, n_pn.strip().title())
                                sheet_main.update_cell(ridx, 3, n_nd.strip() if n_nd.strip() else "-")
                                sheet_main.update_cell(ridx, 4, n_item.strip())
                                sheet_main.update_cell(ridx, 6, json.dumps(opts_d))
                                sheet_main.update_cell(ridx, 7, n_price)
                                st.success("Updated!")
                                clear_all_caches()
                                st.rerun()
                                break

        with tab3:
            del_p = st.selectbox("Select Party (Delete):", ["-- Select --"] + unique_parties_list, key="del_hist_party")
            if del_p != "-- Select --":
                del_items = prepare_display_df_with_history(df[df['Clean_Party'] == del_p])
                del_items['Display'] = del_items.apply(make_full_display_name, axis=1)
                sel_del = st.selectbox("Select Item:", del_items['Display'].tolist(), key="del_hist_item")
                if sel_del and st.button("❌ Delete Permanently", type="primary", key="btn_del_hist"):
                    del_row = del_items[del_items['Display'] == sel_del].iloc[0]
                    all_vals = sheet_main.get_all_values()
                    for i, r in enumerate(all_vals):
                        if i > 0 and r[1].strip().title() == del_p and str(r[2]).strip() == str(del_row['Date']).strip() and str(r[3]).strip() == str(del_row['Size']).strip():
                            sheet_main.delete_rows(i + 1)
                            st.success("Deleted!")
                            clear_all_caches()
                            st.rerun()
                            break
                            
        with tab4:
            st.write("### 📋 Copy Party & Apply % Change")
            cf = st.selectbox("Copy From:", ["-- Select --"] + unique_parties_list, key="clone_from")
            if cf != "-- Select --":
                p_data = prepare_display_df_with_history(df[df['Clean_Party'] == cf])
                p_data['Display'] = p_data.apply(make_full_display_name, axis=1)
                sel_cls = []
                st.write("**Select Items:**")
                for i, d in enumerate(p_data['Display'].tolist()):
                    if st.checkbox(d, value=True, key=f"cl_{cf}_{i}"): 
                        sel_cls.append(d)
                st.write("---")
                c1, c2 = st.columns(2)
                pct = c1.number_input("% Change (+/-):", key="clone_pct")
                npt = c2.text_input("New Party Name:", key="clone_new_party")
                if st.button("🚀 Clone", type="primary", key="btn_clone_party"):
                    if not npt or not sel_cls: 
                        st.warning("Enter Name & Select Items!")
                        st.stop()
                    n_rows = []
                    dt_s = datetime.now().strftime("%d-%m-%Y")
                    for d in sel_cls:
                        r_d = p_data[p_data['Display'] == d].iloc[0]
                        ot = safe_int(r_d['Total_Price'], 0)
                        is_sp = (str(r_d['Speed']) == 'Spare Part')
                        n_opt = str(r_d.get('Options', '{}'))
                        n_ttl = int(ot * (1 + (pct / 100.0)))
                        
                        if is_sp:
                            ob, og, oh = get_spare_details(r_d.get('Options', '{}'), ot)
                            nb = int(ob * (1 + (pct / 100.0)))
                            n_ttl = int(nb + (nb * og / 100.0))
                            opts_d = {"Basic": nb, "GST": og, "HSN": oh}
                            try:
                                old_opts = json.loads(str(r_d.get('Options','{}')))
                                if "General_Note" in old_opts: 
                                    opts_d["General_Note"] = old_opts["General_Note"]
                            except: 
                                pass
                            n_opt = json.dumps(opts_d)
                        else:
                            try:
                                opts_d = json.loads(n_opt)
                                lhl = settings.get('lh_label','Low+High Speed Extra Charge')
                                for k,v in list(opts_d.items()):
                                    if k not in ['HSN', 'ManualOldDate', 'ManualOldPrice', lhl, 'Custom_Details', 'Is_Custom_Name', 'General_Note'] and isinstance(v, (int, float)): 
                                        opts_d[k] = int(v * (1 + (pct/100.0)))
                                opts_d['ManualOldDate'] = "-"
                                opts_d['ManualOldPrice'] = "-"
                                n_opt = json.dumps(opts_d)
                            except: 
                                pass
                        n_rows.append([st.session_state.q_no, npt.strip().title(), dt_s, r_d['Size'], str(r_d['Speed']), n_opt, n_ttl])
                    sheet_main.append_rows(n_rows)
                    st.success(f"Cloned {len(n_rows)} to '{npt}'! ✅")
                    clear_all_caches()
                    st.rerun()

# ==========================================
# 5. PART PRICE FINDER PAGE 
# ==========================================
elif menu == "🔍 Part Price Finder":
    display_header()
    if main_df.empty: 
        st.info("No records.")
    else:
        df = main_df.copy()
        df['Clean_Party'] = df['Party'].astype(str).str.strip().str.title()
        skw = st.text_input("🔍 Smart Search (Name/Size):", key="search_pf")
        c1, c2 = st.columns(2)
        sp = c1.selectbox("Filter Party:", ["-- All --"] + unique_parties_list, key="search_pf_party")
        f_items = sorted(df[df['Clean_Party'] == sp]['Size'].astype(str).unique().tolist()) if sp != "-- All --" else all_items_list
        si = c2.selectbox("Filter Item:", ["-- All --"] + f_items, key="search_pf_item")
        
        f_df = df.copy()
        if sp != "-- All --": 
            f_df = f_df[f_df['Clean_Party'] == sp]
        if si != "-- All --": 
            f_df = f_df[f_df['Size'].astype(str).str.strip() == si]
        if skw: 
            f_df = f_df[f_df[['Size', 'Speed', 'Party']].astype(str).apply(lambda x: x.str.contains(skw, case=False)).any(axis=1)]
        
        if f_df.empty: 
            st.warning("No entries.")
        elif sp == "-- All --" and si == "-- All --" and not skw: 
            st.info("Select filters to search.")
        else:
            p_df = prepare_display_df_with_history(f_df)
            disp_df = p_df[['Date', 'Party', 'Item Details', 'HSN Code', 'Final Price']].reset_index(drop=True)
            disp_df.index = range(1, len(disp_df)+1)
            styled_disp = disp_df.style.format({'Final Price': "{:,.2f}"}).set_properties(subset=['Final Price'], **{'text-align': 'center'})
            st.dataframe(styled_disp, use_container_width=True)
            
            st.write("---")
            pdf_fmt_find = st.radio("📄 PDF Design Format:", ["Landscape (આડું)", "Portrait (ઊભું)"], horizontal=True, key="find_pdf_format")
            
            p_buf = create_dynamic_pdf(sp if sp!="-- All --" else "Search Result", p_df, "Item / Part Price Report", ['Date', 'Party', 'Item Details', 'Final Price'], False, orientation=pdf_fmt_find) 
            c1, c2 = st.columns(2)
            with c1: 
                st.download_button("📥 PDF", data=p_buf, file_name="Search_Result.pdf", use_container_width=True, key="dl_pf_pdf")
            with c2: 
                if st.button("👁️ Preview", use_container_width=True, key="pv_pf_pdf"): 
                    display_pdf_in_app(p_buf)

# ==========================================
# 6. MONTHLY EMAIL REPORTS PAGE
# ==========================================
elif menu == "📧 Monthly Email Reports":
    display_header()
    st.write("### 📧 Auto-Generate & Email Monthly Reports")
    c1, c2 = st.columns(2)
    ms = ["01","02","03","04","05","06","07","08","09","10","11","12"]
    cm = datetime.now().strftime("%m")
    cy = datetime.now().year
    ys = [str(y) for y in range(cy-2, cy+3)]
    sel_m = c1.selectbox("Month:", ms, index=ms.index(cm))
    sel_y = c2.selectbox("Year:", ys, index=ys.index(str(cy)))
    tstr = f"-{sel_m}-{sel_y}"
    dmstr = f"{datetime.strptime(sel_m, '%m').strftime('%B')} {sel_y}"
    st.write("---")
    
    if st.button("🚀 Send Email Now", type="primary", key="btn_send_mail"):
        with st.spinner(f"Preparing reports for {dmstr}..."):
            pdf_atts = {}
            
            f_df = factory_df.copy()
            if not f_df.empty:
                f_df = f_df[f_df['Date'].astype(str).str.endswith(tstr)]
                if not f_df.empty: 
                    pdf_atts[f"Factory_{dmstr}.pdf"] = create_factory_pdf("-- All --", "-- All --", f_df)
                    
            h_df = hexo_df.copy()
            if not h_df.empty:
                h_df = h_df[h_df['Date'].astype(str).str.endswith(tstr)]
                if not h_df.empty:
                     mat_in = pd.to_numeric(stock_df[stock_df['Date'].astype(str).str.endswith(tstr)]['Total Length (MM)'], errors='coerce').fillna(0).sum() if not stock_df.empty else 0
                     mat_out = pd.to_numeric(h_df['Total Used (MM)'], errors='coerce').fillna(0).sum()
                     pdf_atts[f"Hexo_{dmstr}.pdf"] = create_hexo_pdf("All Materials", mat_in, mat_out, mat_in - mat_out, h_df)
                     
            m_df = main_df.copy()
            if not m_df.empty:
                m_df = m_df[m_df['Date'].astype(str).str.endswith(tstr)]
                if not m_df.empty:
                    p_m_df = prepare_display_df_with_history(m_df)
                    machines_df = p_m_df[p_m_df['Speed'] != 'Spare Part']
                    parts_df = p_m_df[p_m_df['Speed'] == 'Spare Part']
                    v_mach = settings.get('vis_mach', ['Date','Item Details','Final Price'])
                    v_part = settings.get('vis_part', ['Date','HSN Code','Final Price'])
                    if not machines_df.empty: 
                        pdf_atts[f"Machines_{dmstr}.pdf"] = create_dynamic_pdf(dmstr, machines_df, f"Monthly Machines Detail ({dmstr})", v_mach, True)
                    if not parts_df.empty: 
                        pdf_atts[f"Parts_{dmstr}.pdf"] = create_dynamic_pdf(dmstr, parts_df, f"Monthly Parts Detail ({dmstr})", v_part, False)
                        
            if not pdf_atts: 
                st.warning("No records found.")
                st.stop()
                
            success, msg = send_monthly_report_email(dmstr, pdf_atts)
            if success: 
                st.success("✅ " + msg)
                st.balloons()
            else: 
                st.error("❌ Failed: " + msg)

# ==========================================
# 7. MASTER SETTINGS PAGE
# ==========================================
elif menu == "⚙️ Master Settings":
    display_header()
    st.title("Master Settings 🔒")
    pwd_input = st.text_input("Master Password:", type="password", key="pwd_master")
    if pwd_input != settings.get('password', '1234'):
        if pwd_input: st.error("❌ Incorrect Password!")
        st.stop()
    st.success("Granted!")
    tab1, tab2, tab3, tab4 = st.tabs(["Base Prices", "Add-ons", "GST %", "HSN Codes"])
    
    with tab1:
        st.subheader("Base Sizes")
        prices = settings['prices']
        for size, price in list(prices.items()):
            cA, cB, cC = st.columns([2, 2, 1])
            cA.write(f"**{format_size(size)}**")
            prices[size] = cB.number_input("Price", value=price, step=1000, key=f"p_{size}", label_visibility="collapsed")
            if cC.button("❌", key=f"d_{size}"): 
                del prices[size]
                save_settings_to_sheet(settings)
                st.rerun()
        st.write("---")
        c1, c2, c3 = st.columns(3)
        n_w = c1.text_input("W (e.g. 24)")
        n_l = c2.text_input("L (e.g. 48)")
        n_p = c3.number_input("Base Price", step=1000)
        if st.button("➕ Add Size", key="btn_set_sz") and n_w and n_l and n_p > 0: 
            settings['prices'][f"{n_w}x{n_l}"] = n_p
            save_settings_to_sheet(settings)
            st.rerun()
            
    with tab2:
        st.subheader("Add-ons")
        addons = settings['addons']
        lhl = settings.get('lh_label', 'Low+High Speed Extra Charge')
        lhp = settings['addons'].get(lhl, 0)
        cA, cB, cC = st.columns([2, 2, 1])
        new_lh_l = cA.text_input("Special Label", value=lhl)
        new_lh_p = cB.number_input("Price", value=lhp, step=500)
        if cC.button("💾 Label", key="btn_ren_lh"):
            if new_lh_l != lhl: 
                settings['addons'][new_lh_l] = new_lh_p
                if lhl in settings['addons']: 
                    del settings['addons'][lhl]
                settings['lh_label'] = new_lh_l
            else: 
                settings['addons'][lhl] = new_lh_p
            save_settings_to_sheet(settings)
            st.rerun()
            
        st.write("---")
        for name, price in list(addons.items()):
            if name == settings.get('lh_label'): continue
            cA, cB, cC = st.columns([2, 2, 1])
            cA.write(f"**{name}**")
            addons[name] = cB.number_input("Price", value=price, step=500, key=f"a_{name}", label_visibility="collapsed")
            if cC.button("❌", key=f"da_{name}"): 
                del addons[name]
                save_settings_to_sheet(settings)
                st.rerun()
        if st.button("💾 Save Add-ons", type="primary"): 
            save_settings_to_sheet(settings)
            st.toast("Saved!")
        st.write("---")
        c1, c2 = st.columns(2)
        new_a = c1.text_input("Name:")
        new_p = c2.number_input("Price:", step=500)
        if st.button("➕ Add", key="btn_set_add") and new_a and new_p > 0: 
            settings['addons'][new_a] = new_p
            save_settings_to_sheet(settings)
            st.rerun()
            
    with tab3:
        st.subheader("GST rates")
        gst_rates = settings.get("gst_rates", [])
        for g in list(gst_rates):
            cA, cB = st.columns([3, 1])
            cA.write(f"**{g}%**")
            if cB.button("❌", key=f"dgst_{g}"): 
                gst_rates.remove(g)
                settings["gst_rates"] = gst_rates
                save_settings_to_sheet(settings)
                st.rerun()
        st.write("---")
        n_gst = st.number_input("New GST %", min_value=1, max_value=100)
        if st.button("➕ Add GST"):
            if n_gst not in gst_rates: 
                gst_rates.append(n_gst)
                gst_rates.sort()
                settings["gst_rates"] = gst_rates
                save_settings_to_sheet(settings)
                st.rerun()
                
    with tab4:
        st.subheader("HSN Codes")
        hsn_codes = settings.get("hsn_codes", [])
        for h in list(hsn_codes):
            cA, cB = st.columns([3, 1])
            cA.write(f"**{h}**")
            if cB.button("❌", key=f"dhsn_{h}"): 
                hsn_codes.remove(h)
                settings["hsn_codes"] = hsn_codes
                save_settings_to_sheet(settings)
                st.rerun()
        st.write("---")
        n_hsn = st.text_input("New HSN:")
        if st.button("➕ Add HSN") and n_hsn:
            if n_hsn not in hsn_codes: 
                hsn_codes.append(n_hsn)
                hsn_codes.sort()
                settings["hsn_codes"] = hsn_codes
                save_settings_to_sheet(settings)
                st.rerun()
