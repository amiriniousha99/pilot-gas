import streamlit as st
from auth import authenticate_user, USERS, has_access
from styles import load_login_css, load_dashboard_css, show_custom_navbar
import pandas as pd
from datetime import datetime, timedelta
import jdatetime
import requests
import plotly.express as px
import plotly.graph_objects as go
import base64
import os


st.set_page_config(
    page_title="سامانه پیلوت گاز",
    page_icon="assets/sitelogo.png",
    layout="wide",
    initial_sidebar_state="collapsed"
)

if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if 'personnel_data' not in st.session_state:
    st.session_state.personnel_data = None

if 'employee_data' not in st.session_state:
    st.session_state.employee_data = None
    
if 'monthlylist_data' not in st.session_state:
    st.session_state.monthlylist_data = None

if 'last_update_monthlylist' not in st.session_state:
    st.session_state.last_update_monthlylist = None
    
if 'last_update_personnel' not in st.session_state:
    st.session_state.last_update_personnel = None

if 'last_update_employee' not in st.session_state:
    st.session_state.last_update_employee = None
    
if 'search_triggered' not in st.session_state:
    st.session_state.search_triggered = False

target_user = st.query_params.get("user")
if target_user and target_user in USERS:
    st.session_state.logged_in = True
    st.session_state.user_info = USERS[target_user]

if st.query_params.get("action") == "logout":
    st.session_state.logged_in = False
    st.session_state.user_info = None
    st.query_params.clear()
    st.rerun()

SCRIPT_URL = "https://script.google.com/macros/s/AKfycbw9VrEUyzTpbxeQf7vB8IzZ7BmmsYP65yy-dWGvTCBRLorDc8dCm0f5O3NPQxV9hXn0/exec"

# =========================================================
# 🛠️ موتور مرکزی ETL (تمیزکاری و استانداردسازی داده‌ها)
# =========================================================

def global_clean_text(text):
    """تابع تمیزکاری متون فارسی (استانداردسازی ی/ک و حذف فاصله)"""
    if pd.isna(text) or text == "" or str(text).lower() in ['nan', 'none', 'null']:
        return "نامشخص"
    
    text = str(text).strip()
    replacements = {
        'ي': 'ی', 'ك': 'ک', 'ى': 'ی', 'ة': 'ه',
        'أ': 'ا', 'إ': 'ا', 'آ': 'ا',
        '\u200c': ' ', '¬': ''
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def categorize_rejection_reason(text):
    """دسته‌بندی هوشمند دلایل رد یا انصراف"""
    if text == "نامشخص": return "نامشخص"
    text = text.replace(' ', '') # حذف فاصله برای جستجوی بهتر
    
    keywords = {
        'حقوق': ['حقوق', 'تومان', 'مبلغ', 'پول', 'درامد', 'مزایا', 'پایه'],
        'مشکل_اضافه_کاری': ['اضافه', 'ساعت', 'شیفت', 'تایم', 'تعطیل', 'پنجشنبه'],
        'مسیر_و_سرویس': ['ناهار', 'سرویس', 'غذا', 'مسیر', 'راه', 'تردد', 'دور', 'مسافت'],
        'عدم_مراجعه': ['مراجعه', 'انصراف', 'نیامد', 'پاسخ', 'گوشی', 'تماس', 'جواب'],
        'عدم_تایید_فنی': ['تایید', 'رد', 'فنی', 'قبول', 'شرایط', 'سن', 'مهارت', 'سابقه'],
        'محیط_کاری': ['محیط', 'برخورد', 'فرهنگ', 'جو', 'اخلاق']
    }
    
    for category, keys in keywords.items():
        if any(k in text for k in keys):
            return category.replace('_', ' ')
            
    return 'سایر موارد'

@st.cache_data(ttl=7200, show_spinner=False)
def fetch_and_clean_data(sheet_name):
    """
    این تابع هم داده را می‌گیرد و هم همان لحظه تمیز می‌کند.
    نتیجه در کش ذخیره می‌شود تا سرعت بالا برود.
    """
    try:
        response = requests.get(f"{SCRIPT_URL}?sheet={sheet_name}", timeout=15)
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and 'error' in data:
                st.error(f"خطا: {data['error']}")
                return None
            
            if not data:
                return pd.DataFrame() # برگرداندن جدول خالی به جای None

            # 1. تبدیل به دیتافریم
            df = pd.DataFrame(data)
            
            # 2. تمیزکاری نام ستون‌ها
            df.columns = df.columns.str.strip()
            
            # 3. تمیزکاری سلول‌ها (اعمال روی تمام ستون‌های متنی)
            # این کار باعث می‌شود دیگر نیازی به clean_text در محیط کاربری نباشد
            object_cols = df.select_dtypes(include=['object']).columns
            for col in object_cols:
                df[col] = df[col].apply(global_clean_text)

            # 4. عملیات اختصاصی بر اساس نوع شیت (Specific Transformations)
            
            # الف) اگر شیت استخدام بود: دسته‌بندی دلایل اضافه شود
            if sheet_name == "employment":
                if 'علت نپذیرفتن' in df.columns:
                    df['علت_دسته_بندی_شده'] = df['علت نپذیرفتن'].apply(categorize_rejection_reason)
                else:
                    df['علت_دسته_بندی_شده'] = "نامشخص"

            # ب) اگر شیت کارکرد ماهانه بود: مرتب‌سازی ماه‌ها
            if sheet_name == "monthlylist" and 'ماه' in df.columns:
                persian_months = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", 
                                  "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
                df['month_idx'] = df['ماه'].apply(lambda x: persian_months.index(x) if x in persian_months else -1)
                df = df.sort_values('month_idx', ascending=False).drop(columns=['month_idx'])

            # ج) اگر شیت پرسنل بود: معکوس کردن ستون‌ها (طبق سلیقه شما)
            if sheet_name == "personnel":
                df = df[df.columns[::-1]]

            return df
            
        else:
            st.error(f"خطا در اتصال: {response.status_code}")
            return None
    except Exception as e:
        st.error(f"خطا سیستمی: {str(e)}")
        return None

# توابع Wrapper برای سازگاری با کد قبلی شما
def load_personnel_data():
    df = fetch_and_clean_data("personnel")
    if df is not None:
        st.session_state.personnel_data = df
        st.session_state.last_update_personnel = datetime.now()

def load_employee_data():
    df = fetch_and_clean_data("employment")
    if df is not None:
        st.session_state.employee_data = df
        st.session_state.last_update_employee = datetime.now()

def load_monthlylist_data():
    df = fetch_and_clean_data("monthlylist")
    if df is not None:
        st.session_state.monthlylist_data = df
        st.session_state.last_update_monthlylist = datetime.now()
        # =========================================================
# ⏰ توابع مدیریت زمان و آپدیت خودکار
# =========================================================

def should_update_data(last_update):
    """بررسی می‌کند آیا ۲ ساعت از آخرین آپدیت گذشته است؟"""
    if last_update is None:
        return True
    time_diff = datetime.now() - last_update
    return time_diff >= timedelta(hours=2)

def auto_update_check():
    """چک کردن تمام دیتاها و آپدیت خودکار در صورت قدیمی بودن"""
    
    # 1. بررسی پرسنل
    if should_update_data(st.session_state.last_update_personnel):
        # پاک کردن کش تابعی که ساختیم
        fetch_and_clean_data.clear()
        load_personnel_data()
        
    # 2. بررسی استخدام
    if should_update_data(st.session_state.last_update_employee):
        fetch_and_clean_data.clear()
        load_employee_data()

    # 3. بررسی گزارش ماهانه (اختیاری)
    if should_update_data(st.session_state.last_update_monthlylist):
        fetch_and_clean_data.clear()
        load_monthlylist_data()
def login_page():
    load_login_css()
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.form("login_form", clear_on_submit=False):
            
            # 👇👇👇 کد لوگوی وسط‌چین با سایز ۱۰۰ 👇👇👇
            # سه ستون مساوی ایجاد می‌کنیم تا ستون وسط دقیقاً در مرکز باشد
            l_col, m_col, r_col = st.columns(3)
            
            with m_col:
                try:
                    # لوگو را در ستون وسط قرار می‌دهیم با عرض ۱۰۰
                    st.image("assets/logo.png", width=100)
                except:
                    pass
            # 👆👆👆 پایان کد لوگو 👆👆👆

            st.markdown("## پیلوت گاز")
            username = st.text_input("نام کاربری")
            password = st.text_input("رمز عبور", type="password")
            st.markdown("")
            submitted = st.form_submit_button("ورود", use_container_width=True)
            if submitted:
                user = authenticate_user(username, password)
                if user:
                    st.session_state.logged_in = True
                    st.session_state.user_info = user
                    st.session_state.username = username
                    st.query_params["user"] = username
                    st.rerun()
                else:
                    st.error("رمز یا نام کاربری اشتباه است!")

def show_home_content():
    st.markdown('<h1>🏠 خوش آمدید به سامانه مدیریت پیلوت گاز</h1>', unsafe_allow_html=True)
    # 1. تابع کمکی برای تبدیل عکس به کد
    def get_base64_image(image_path):
        try:
            if os.path.exists(image_path):
                with open(image_path, "rb") as img_file:
                    return base64.b64encode(img_file.read()).decode()
            return None
        except:
            return None
        # 2. خواندن عکس‌ها از پوشه assets (با نام‌های slide1.jpg تا slide5.jpg)
    # اگر عکس در پوشه assets باشد آن را می‌خواند، اگر نباشد عکس اینترنتی نشان می‌دهد
    img1_b64 = get_base64_image("assets/slide1.jpg")
    src1 = f"data:image/jpeg;base64,{img1_b64}" if img1_b64 else "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=1200&h=500&fit=crop"

    img2_b64 = get_base64_image("assets/slide2.jpg")
    src2 = f"data:image/jpeg;base64,{img2_b64}" if img2_b64 else "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=1200&h=500&fit=crop"

    img3_b64 = get_base64_image("assets/slide3.jpg")
    src3 = f"data:image/jpeg;base64,{img3_b64}" if img3_b64 else "https://images.unsplash.com/photo-1552664730-d307ca884978?w=1200&h=500&fit=crop"

    img4_b64 = get_base64_image("assets/slide4.jpg")
    src4 = f"data:image/jpeg;base64,{img4_b64}" if img4_b64 else "https://images.unsplash.com/photo-1504384308090-c894fdcc538d?w=1200&h=500&fit=crop"

    img5_b64 = get_base64_image("assets/slide5.jpg")
    src5 = f"data:image/jpeg;base64,{img5_b64}" if img5_b64 else "https://images.unsplash.com/photo-1460925895917-afdab827c52f?w=1200&h=500&fit=crop"

    # 3. قرار دادن کدهای تولید شده در HTML
    st.components.v1.html(f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            * {{margin: 0; padding: 0; box-sizing: border-box;}}
            body {{font-family: Arial, sans-serif; direction: rtl;}}
            .slider-container {{position: relative; width: 100%; max-width: 1200px; height: 500px; margin: 0 auto; overflow: hidden; border-radius: 15px; box-shadow: 0 8px 24px rgba(0,0,0,0.15);}}
            .slider-wrapper {{position: relative; width: 100%; height: 100%;}}
            .slide {{position: absolute; top: 0; left: 0; width: 100%; height: 100%; opacity: 0; transition: opacity 1s ease-in-out;}}
            .slide.active {{opacity: 1;}}
            .slide img {{width: 100%; height: 100%; object-fit: cover;}}
            .slide-overlay {{position: absolute; bottom: 0; left: 0; right: 0; background: linear-gradient(to top, rgba(0,0,0,0.7), transparent); padding: 30px; color: white;}}
            .slide-title {{font-size: 2rem; font-weight: bold; margin-bottom: 10px;}}
            .slide-description {{font-size: 1.1rem;}}
            .nav-button {{position: absolute; top: 50%; transform: translateY(-50%); background: rgba(255,255,255,0.9); border: none; width: 50px; height: 50px; border-radius: 50%; cursor: pointer; font-size: 1.5rem; color: #033270; transition: all 0.3s; z-index: 10; display: flex; align-items: center; justify-content: center;}}
            .nav-button:hover {{background: white; transform: translateY(-50%) scale(1.1); box-shadow: 0 4px 12px rgba(0,0,0,0.2);}}
            .nav-button.prev {{left: 20px;}}
            .nav-button.next {{right: 20px;}}
            .indicators {{position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); display: flex; gap: 10px; z-index: 10;}}
            .indicator {{width: 12px; height: 12px; border-radius: 50%; background: rgba(255,255,255,0.5); cursor: pointer; transition: all 0.3s; border: none;}}
            .indicator.active {{background: white; width: 40px; border-radius: 6px;}}
        </style>
    </head>
    <body>
        <div class="slider-container">
            <div class="slider-wrapper">
                <div class="slide active"><img src="{src1}"><div class="slide-overlay"><div class="slide-title">مدیریت هوشمند</div><div class="slide-description">سامانه جامع مدیریت کسب و کار</div></div></div>
                <div class="slide"><img src="{src2}"><div class="slide-overlay"><div class="slide-title">تحلیل داده‌ها</div><div class="slide-description">گزارش‌های تحلیلی پیشرفته</div></div></div>
                <div class="slide"><img src="{src3}"><div class="slide-overlay"><div class="slide-title">همکاری تیمی</div><div class="slide-description">مدیریت و هماهنگی کامل تیم</div></div></div>
                <div class="slide"><img src="{src4}"><div class="slide-overlay"><div class="slide-title">رشد کسب و کار</div><div class="slide-description">افزایش بهره‌وری و سودآوری</div></div></div>
                <div class="slide"><img src="{src5}"><div class="slide-overlay"><div class="slide-title">تکنولوژی پیشرفته</div><div class="slide-description">ابزارهای مدرن مدیریتی</div></div></div>
            </div>
            <button class="nav-button prev" onclick="changeSlide(-1)">◀</button>
            <button class="nav-button next" onclick="changeSlide(1)">▶</button>
            <div class="indicators">
                <button class="indicator active" onclick="goToSlide(0)"></button>
                <button class="indicator" onclick="goToSlide(1)"></button>
                <button class="indicator" onclick="goToSlide(2)"></button>
                <button class="indicator" onclick="goToSlide(3)"></button>
                <button class="indicator" onclick="goToSlide(4)"></button>
            </div>
        </div>
        <script>
            let currentSlide = 0;
            const slides = document.querySelectorAll('.slide');
            const indicators = document.querySelectorAll('.indicator');
            function showSlide(index) {{
                slides.forEach(s => s.classList.remove('active'));
                indicators.forEach(i => i.classList.remove('active'));
                if (index >= slides.length) currentSlide = 0;
                else if (index < 0) currentSlide = slides.length - 1;
                else currentSlide = index;
                slides[currentSlide].classList.add('active');
                indicators[currentSlide].classList.add('active');
            }}
            function changeSlide(dir) {{ showSlide(currentSlide + dir); }}
            function goToSlide(idx) {{ showSlide(idx); }}
            setInterval(() => changeSlide(1), 5000);
        </script>
    </body>
    </html>
    """, height=550)
   
    st.subheader("📊 خلاصه وضعیت سیستم")
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown('<div class="dashboard-card"><h3 style="color: #033270;">👥 منابع انسانی</h3><p style="font-size: 2rem; font-weight: bold; color: #2ecc71;">150</p><p style="color: #666;">تعداد کارکنان</p></div>', unsafe_allow_html=True)
    with col2:
        st.markdown('<div class="dashboard-card"><h3 style="color: #033270;">🏭 تولید</h3><p style="font-size: 2rem; font-weight: bold; color: #3498db;">1,234</p><p style="color: #666;">واحد تولید شده</p></div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="dashboard-card"><h3 style="color: #033270;">💰 فروش</h3><p style="font-size: 2rem; font-weight: bold; color: #e74c3c;">₽2.5M</p><p style="color: #666;">فروش ماهانه</p></div>', unsafe_allow_html=True)
    with col4:
        st.markdown('<div class="dashboard-card"><h3 style="color: #033270;">📦 انبار</h3><p style="font-size: 2rem; font-weight: bold; color: #f39c12;">567</p><p style="color: #666;">اقلام موجود</p></div>', unsafe_allow_html=True)
# =========================================================
# 🛠️ توابع کمکی لود دیتا (حتما قبل از show_hr_content باشد)
# =========================================================

def should_update_data(last_update):
    """بررسی می‌کند آیا ۲ ساعت از آخرین آپدیت گذشته است؟"""
    if last_update is None:
        return True
    time_diff = datetime.now() - last_update
    return time_diff >= timedelta(hours=12)

def ensure_data_loaded(data_type):
    """
    این تابع چک می‌کند اگر داده مورد نیاز موجود نبود یا قدیمی بود، آن را دانلود کند.
    data_type: 'personnel', 'employee', 'monthly'
    """
    if data_type == "personnel":
        if st.session_state.personnel_data is None or should_update_data(st.session_state.last_update_personnel):
            with st.spinner("⏳ در حال دریافت لیست پرسنل..."):
                load_personnel_data()
                
    elif data_type == "employee":
        if st.session_state.employee_data is None or should_update_data(st.session_state.last_update_employee):
            with st.spinner("⏳ در حال دریافت اطلاعات جذب و استخدام..."):
                load_employee_data()
                
    elif data_type == "monthly":
        if st.session_state.monthlylist_data is None or should_update_data(st.session_state.last_update_monthlylist):
            with st.spinner("⏳ در حال دریافت گزارش کارکرد ماهانه..."):
                load_monthlylist_data()
def show_hr_content():
   
    # ==========================================
    # 🎨 استایل CSS نهایی (اصلاح فاصله‌ها)
    # ==========================================
    st.markdown("""
        <style>
        div[data-testid="stVerticalBlock"] {
            gap: 0.5rem !important;
            /* 1. تنظیم فاصله کلی صفحه */
            .block-container {
                padding-top: 3rem !important;
                padding-bottom: 2rem !important;
            }
            
            /* 2. استایل باکس تیتر */
            .header-box {
                background-color: white;
                width: 100%;
                padding: 15px 20px;
                border-radius: 10px;
                border: 1px solid #E2E8F0;
                border-bottom: 4px solid #033270;
                box-shadow: 0 4px 6px rgba(0,0,0,0.05);
                margin-bottom: 15px; /* کاهش فاصله پایین هدر */
                direction: rtl;
                text-align: right;
            }
            
            .header-title {
                color: #033270;
                margin: 0;
                font-size: 26px;
                font-weight: 900;
                font-family: 'Tahoma', sans-serif;
            }

           /* 3. خط جداکننده با مارجین منفی (برای حذف فاصله اجباری) */
            .compact-separator {
                margin-top: -20px !important;    /* خط را ۲۰ پیکسل بالا می‌کشد */
                margin-bottom: -20px !important; /* محتوای پایین را ۲۰ پیکسل بالا می‌کشد */
                border-bottom: 1px solid #E2E8F0;
                width: 100%;
                display: block;
            }

            /* حذف فاصله بالای تیترهای صفحات (مثل لیست جامع پرسنل) */
            h3, h2, .stHeadingContainer {
                padding-top: 0px !important;
                margin-top: 0px !important;
            }
            
            /* حذف فاصله اضافی بین دکمه‌ها و خط */
            div[data-testid="column"] {
                margin-bottom: -10px !important;
            }
            /* 4. استایل دکمه‌های منو */
            div.stButton > button[kind="primary"] {
                background: linear-gradient(135deg, #034870 0%, #164e96 100%) !important;
                border: none !important;
                border-radius: 12px !important;
                padding: 10px 20px !important;
                box-shadow: 0 4px 10px rgba(3, 50, 112, 0.3) !important;
                transition: all 0.3s ease !important;
            }
            /* اجبار رنگ سفید برای متن دکمه فعال */
            div.stButton > button[kind="primary"] p {
                color: #ffffff !important; 
                font-weight: 900 !important;
                font-size: 16px !important;
            }
            div.stButton > button[kind="primary"] * { color: #ffffff !important; }

            div.stButton > button[kind="primary"]:hover {
                box-shadow: 0 6px 15px rgba(3, 60, 112, 0.4) !important;
                transform: translateY(-1px) !important;
            }

            div.stButton > button[kind="secondary"] {
                background-color: #E3F2FD !important;
                border: 1px solid #e2e8f0 !important;
                border-radius: 12px !important;
                padding: 10px 20px !important;
                box-shadow: 0 2px 5px rgba(0,0,0,0.02) !important;
                transition: all 0.3s ease !important;
            }
            div.stButton > button[kind="secondary"] p {
                color: #033270 !important;
                font-weight: 600 !important;
            }
            div.stButton > button[kind="secondary"] * { color: #033270 !important; }

            div.stButton > button[kind="secondary"]:hover {
                background-color: #BFDBFE !important;
                border-color: #033270 !important;
                transform: translateY(-2px) !important;
                box-shadow: 0 5px 15px rgba(3, 50, 112, 0.1) !important;
            }

            /* استایل کارت‌های آماری */
            .stat-card-new {
                background: white; border-radius: 10px; padding: 15px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08); border-left: 5px solid #033270;
                text-align: center; transition: transform 0.2s;
            }
            .stat-card-new:hover { transform: scale(1.02); }
            .stat-value { font-size: 24px; font-weight: 900; color: #033270; }
            .stat-label { font-size: 13px; color: #64748B; font-weight: bold; }
        </style>
        
        <div class="header-box">
            <div class="header-title">👥 مدیریت منابع انسانی</div>
        </div>
    """, unsafe_allow_html=True)
    # 3. مدیریت وضعیت تب فعال
    if 'hr_active_tab' not in st.session_state:
        st.session_state.hr_active_tab = "رویدادها" # پیش‌فرض
    # نوار دکمه‌ها
    b1, b2, b3, b4, b5 = st.columns(5)
    
    with b1:
        type_ = "primary" if st.session_state.hr_active_tab == "رویدادها" else "secondary"
        if st.button("رویدادها 📅", use_container_width=True, type=type_):
            st.session_state.hr_active_tab = "رویدادها"
            st.rerun()
            
    with b2:
        type_ = "primary" if st.session_state.hr_active_tab == "لیست جامع پرسنل" else "secondary"
        if st.button("لیست جامع پرسنل 🗂️", use_container_width=True, type=type_):
            st.session_state.hr_active_tab = "لیست جامع پرسنل"
            st.rerun()
    with b3:
        type_ = "primary" if st.session_state.hr_active_tab == "گزارش ماهانه" else "secondary"
        if st.button("گزارش ماهانه 📊", use_container_width=True, type=type_):
            st.session_state.hr_active_tab = "گزارش ماهانه"
            st.rerun()
            
    with b4:
        type_ = "primary" if st.session_state.hr_active_tab == "جذب و استخدام" else "secondary"
        if st.button("جذب و استخدام 📝", use_container_width=True, type=type_):
            st.session_state.hr_active_tab = "جذب و استخدام"
            st.rerun()

    with b5:
        type_ = "primary" if st.session_state.hr_active_tab == "داشبورد تحلیلی" else "secondary"
        if st.button("داشبورد تحلیلی 📈", use_container_width=True, type=type_):
            st.session_state.hr_active_tab = "داشبورد تحلیلی"
            st.rerun()

    st.markdown("---") 

    # =========================================================
    # محتوای صفحات (کپی دقیق از کد اصلی شما)
    # =========================================================

    # بخش ۵: داشبورد تحلیل (شامل تمام نمودارها و تحلیل‌ها)
    # ---------------------------------------------------------
    if st.session_state.hr_active_tab == "داشبورد تحلیلی":
        ensure_data_loaded("employee")
        ensure_data_loaded("personnel")
        
        # تب‌های فرعی برای پرسنل و جذب (این‌ها باید باشند چون در کد اصلی بودند)
        sub_tab1, sub_tab2 = st.tabs(["👥 تحلیل پرسنل", "📝 تحلیل جذب و استخدام"])
        
        with sub_tab1:
            st.markdown("#### نمودارهای تحلیلی پرسنل")
            if st.session_state.personnel_data is not None:
                df_pers = st.session_state.personnel_data.copy()
                col1, col2 = st.columns(2)
                with col1:
                    if 'واحد' in df_pers.columns:
                        unit_counts = df_pers['واحد'].value_counts().reset_index()
                        unit_counts.columns = ['واحد', 'تعداد']
                        fig1 = px.pie(unit_counts, values='تعداد', names='واحد', title='توزیع پرسنل بر اساس واحد')
                        fig1.update_traces(textposition='inside', textinfo='percent+label')
                        st.plotly_chart(fig1, use_container_width=True)
                with col2:
                    if 'زیرگروه' in df_pers.columns:
                        subgroup_counts = df_pers['زیرگروه'].value_counts().reset_index()
                        subgroup_counts.columns = ['زیرگروه', 'تعداد']
                        fig2 = px.bar(subgroup_counts, x='تعداد', y='زیرگروه', orientation='h', title='توزیع پرسنل بر اساس زیرگروه')
                        st.plotly_chart(fig2, use_container_width=True)
            else: st.warning("داده‌های پرسنل بارگذاری نشده‌اند.")
        
        with sub_tab1:
            st.markdown("#### نمودارهای تحلیلی پرسنل")
            
            if st.session_state.personnel_data is not None:
                df_pers = st.session_state.personnel_data.copy()
                
                col1, col2 = st.columns(2)
                
                with col1:
                    if 'واحد' in df_pers.columns:
                        unit_counts = df_pers['واحد'].value_counts().reset_index()
                        unit_counts.columns = ['واحد', 'تعداد']
                        fig1 = px.pie(unit_counts, values='تعداد', names='واحد', 
                                     title='توزیع پرسنل بر اساس واحد',
                                     color_discrete_sequence=px.colors.qualitative.Set3)
                        fig1.update_traces(textposition='inside', textinfo='percent+label')
                        fig1.update_layout(
                            font=dict(family="Vazirmatn, Arial", size=12),
                            title_font=dict(size=16, family="Vazirmatn, Arial"),
                            height=400
                        )
                        st.plotly_chart(fig1, use_container_width=True)
                
                with col2:
                    if 'زیرگروه' in df_pers.columns:
                        subgroup_counts = df_pers['زیرگروه'].value_counts().reset_index()
                        subgroup_counts.columns = ['زیرگروه', 'تعداد']
                        fig2 = px.bar(subgroup_counts, x='تعداد', y='زیرگروه', 
                                     title='توزیع پرسنل بر اساس زیرگروه',
                                     color='تعداد',
                                     color_continuous_scale='Blues',
                                     orientation='h')
                        fig2.update_layout(
                            font=dict(family="Vazirmatn, Arial", size=12),
                            title_font=dict(size=16, family="Vazirmatn, Arial"),
                            height=400,
                            yaxis={'categoryorder':'total ascending'}
                        )
                        st.plotly_chart(fig2, use_container_width=True)
                
                col3, col4 = st.columns(2)
                
                with col3:
                    if 'جنسیت' in df_pers.columns:
                        gender_counts = df_pers['جنسیت'].value_counts().reset_index()
                        gender_counts.columns = ['جنسیت', 'تعداد']
                        fig3 = px.pie(gender_counts, values='تعداد', names='جنسیت',
                                     title='توزیع جنسیتی پرسنل',
                                     color_discrete_sequence=['#3498db', '#e74c3c'])
                        fig3.update_traces(textposition='inside', textinfo='percent+label')
                        fig3.update_layout(
                            font=dict(family="Vazirmatn, Arial", size=12),
                            title_font=dict(size=16, family="Vazirmatn, Arial"),
                            height=400
                        )
                        st.plotly_chart(fig3, use_container_width=True)
                
                with col4:
                    if 'واحد' in df_pers.columns and 'زیرگروه' in df_pers.columns:
                        unit_subgroup = df_pers.groupby(['واحد', 'زیرگروه']).size().reset_index(name='تعداد')
                        fig4 = px.sunburst(unit_subgroup, path=['واحد', 'زیرگروه'], values='تعداد',
                                          title='توزیع سلسله‌مراتبی پرسنل',
                                          color='تعداد',
                                          color_continuous_scale='RdYlGn')
                        fig4.update_layout(
                            font=dict(family="Vazirmatn, Arial", size=12),
                            title_font=dict(size=16, family="Vazirmatn, Arial"),
                            height=400
                        )
                        st.plotly_chart(fig4, use_container_width=True)
            else:
                st.warning("داده‌های پرسنل بارگذاری نشده‌اند.")
        
        with sub_tab2:
            st.markdown("### 📊 سامانه هوشمند تحلیل جذب")
            
            if st.session_state.employee_data is not None:
                df_emp = st.session_state.employee_data.copy()
                
                filter_col1, filter_col2 = st.columns([3, 1])
                

                with filter_col1:
                    if 'جنسیت' in df_emp.columns:
                        selected_gender = st.radio(
                            "نمایش بر اساس:",
                            ["👥 همه", "👨 آقایان", "👩 خانم‌ها"],
                            horizontal=True,
                            label_visibility="collapsed",
                            key="gender_filter_radio"
                        )
                        # اعمال فیلتر روی کل دیتافریم
                        if selected_gender == "👨 آقایان":
                            df_emp = df_emp[df_emp['جنسیت'] == 'مرد']
                        elif selected_gender == "👩 خانم‌ها":
                            df_emp = df_emp[df_emp['جنسیت'] == 'زن']
                    else:
                        st.warning("ستون 'جنسیت' یافت نشد.")

                with filter_col2:
                    # فضای خالی یا دکمه رفرش (اختیاری)
                    pass
            
                # =========================================================
                # 1. محاسبات پیشرفته (Advanced Calculations)
                # =========================================================
                total_candidates = len(df_emp)
                # اطمینان از وجود ستون وضعیت نهایی
                if 'وضعیت نهایی' in df_emp.columns:
                    total_hired = len(df_emp[df_emp['وضعیت نهایی'] == 'استخدام شد'])
                    total_rejected = len(df_emp[df_emp['وضعیت نهایی'] == 'رد شد'])
                    total_withdrawal = len(df_emp[df_emp['وضعیت نهایی'] == 'انصراف داد'])
                else:
                    total_hired = 0
                    total_rejected = 0
                    total_withdrawal = 0
                
                # الف) نرخ‌ها
                conversion_rate = (total_hired / total_candidates * 100) if total_candidates > 0 else 0
                rejection_rate = (total_rejected / total_candidates * 100) if total_candidates > 0 else 0
                withdrawal_rate = (total_withdrawal / total_candidates * 100) if total_candidates > 0 else 0
                
                # ب) شاخص‌های تحلیلی
                selection_ratio = f"1:{int(total_candidates/total_hired)}" if total_hired > 0 else "0"
                
                # امتیاز سلامت فرآیند
                health_score = 100
                if withdrawal_rate > 20: health_score -= 30
                if conversion_rate < 5: health_score -= 20
                if conversion_rate > 50: health_score -= 10
                
                # =========================================================
                # محاسبات تکمیلی برای کارت‌های جدید
                # =========================================================
                # 1. محاسبه نامشخص‌ها (کسانی که وضعیت نهایی‌شان خالی است یا استاندارد نیست)
                known_statuses = ['استخدام شد', 'رد شد', 'انصراف داد']
                # فرض بر این است که هر چیزی غیر از این سه تا، نامشخص است
                total_unknown = len(df_emp[~df_emp['وضعیت نهایی'].isin(known_statuses)])
                
                # 2. محاسبه بیشترین مصاحبه (واحدی که بیشترین رکورد را دارد)
                if 'واحد' in df_emp.columns and not df_emp.empty:
                    top_interview_unit = df_emp['واحد'].value_counts().idxmax()
                    top_interview_count = df_emp['واحد'].value_counts().max()
                    top_interview_pct = (top_interview_count / total_candidates * 100) if total_candidates > 0 else 0
                else:
                    top_interview_unit = "---"
                    top_interview_count = 0
                    top_interview_pct = 0

                # 3. محاسبه بیشترین استخدام (واحد + جنسیت)
                hired_df_only = df_emp[df_emp['وضعیت نهایی'] == 'استخدام شد']
                if 'واحد' in hired_df_only.columns and not hired_df_only.empty:
                    top_hired_unit = hired_df_only['واحد'].value_counts().idxmax()
                    top_hired_count = hired_df_only['واحد'].value_counts().max()
                    
                    # محاسبه درصد زن و مرد در همین واحد خاص
                    unit_specific_hired = hired_df_only[hired_df_only['واحد'] == top_hired_unit]
                    if 'جنسیت' in unit_specific_hired.columns:
                        m_count = len(unit_specific_hired[unit_specific_hired['جنسیت'] == 'مرد'])
                        f_count = len(unit_specific_hired[unit_specific_hired['جنسیت'] == 'زن'])
                        total_unit_hired = len(unit_specific_hired)
                        m_pct = int((m_count / total_unit_hired) * 100) if total_unit_hired > 0 else 0
                        f_pct = int((f_count / total_unit_hired) * 100) if total_unit_hired > 0 else 0
                        gender_detail = f"👨{m_pct}% | 👩{f_pct}%"
                    else:
                        gender_detail = "نامشخص"
                else:
                    top_hired_unit = "---"
                    top_hired_count = 0
                    gender_detail = ""

# =========================================================
                # محاسبات تکمیلی و آماده‌سازی داده‌ها (نسخه نهایی با تفکیک جنسیت همه کارت‌ها)
                # =========================================================
                
                # تابع کمکی برای تولید HTML آمار جنسیتی (استایل شیشه‌ای)
                def get_gender_glass_html(df_subset, color_code):
                    if df_subset.empty or 'جنسیت' not in df_subset.columns:
                        return '<div style="height: 25px;"></div>' # فضای خالی برای حفظ ساختار
                    
                    total = len(df_subset)
                    m_count = len(df_subset[df_subset['جنسیت'] == 'مرد'])
                    f_count = len(df_subset[df_subset['جنسیت'] == 'زن'])
                    
                    m_pct = int((m_count / total) * 100) if total > 0 else 0
                    f_pct = int((f_count / total) * 100) if total > 0 else 0
                    
                    # باکس سفید نیمه‌شفاف برای آمار
                    return f"""
                    <div style="
                        background: rgba(255, 255, 255, 0.6); 
                        border-radius: 8px; 
                        padding: 6px 10px; 
                        display: flex; 
                        justify-content: space-between; 
                        align-items: center; 
                        margin-top: auto;
                        font-size: 14px; 
                        color: #444; 
                        font-weight: 600;
                        backdrop-filter: blur(4px);
                        border: 1px solid rgba(255,255,255,0.4);">
                        <div style="display:flex; align-items:center;">👨 {m_count} <span style="font-size:11px; opacity:0.7; margin-right:2px;">({m_pct}%)</span></div>
                        <div style="width:1px; height:12px; background:#ccc; margin:0 5px;"></div>
                        <div style="display:flex; align-items:center;">👩 {f_count} <span style="font-size:11px; opacity:0.7; margin-right:2px;">({f_pct}%)</span></div>
                    </div>
                    """

                # 1. کل متقاضیان
                gender_html_total = get_gender_glass_html(df_emp, "#3498db")

                # 2. وضعیت نامشخص
                known_statuses = ['استخدام شد', 'رد شد', 'انصراف داد']
                unknown_df = df_emp[~df_emp['وضعیت نهایی'].isin(known_statuses)]
                total_unknown = len(unknown_df)
                gender_html_unknown = get_gender_glass_html(unknown_df, "#7f8c8d")

                # 3. بیشترین مصاحبه (اصلاح شده: اضافه شدن محاسبه جنسیت)
                if 'واحد' in df_emp.columns and not df_emp.empty:
                    top_interview_unit = df_emp['واحد'].value_counts().idxmax()
                    top_interview_count = df_emp['واحد'].value_counts().max()
                    # فیلتر کردن دیتا فقط برای همین واحد شلوغ
                    interview_unit_df = df_emp[df_emp['واحد'] == top_interview_unit]
                    gender_html_interview = get_gender_glass_html(interview_unit_df, "#9b59b6")
                else:
                    top_interview_unit = "---"; top_interview_count = 0; gender_html_interview = ""

                # 4. غربالگری (رد شده)
                rejected_df = df_emp[df_emp['وضعیت نهایی'] == 'رد شد']
                rejection_rate = (len(rejected_df) / total_candidates * 100) if total_candidates > 0 else 0
                # اگر برای رد شده‌ها هم جنسیت می‌خواهید، خط زیر را فعال کنید:
                # gender_html_rejected = get_gender_glass_html(rejected_df, "#c0392b")

                # 5. انصراف
                withdrawal_df = df_emp[df_emp['وضعیت نهایی'] == 'انصراف داد']
                gender_html_withdrawal = get_gender_glass_html(withdrawal_df, "#e67e22")

                # 6. استخدام نهایی
                hired_df_only = df_emp[df_emp['وضعیت نهایی'] == 'استخدام شد']
                gender_html_hired = get_gender_glass_html(hired_df_only, "#2ecc71")

                # 7. بیشترین جذب
                if 'واحد' in hired_df_only.columns and not hired_df_only.empty:
                    top_hired_unit = hired_df_only['واحد'].value_counts().idxmax()
                    top_hired_count = hired_df_only['واحد'].value_counts().max()
                    unit_specific = hired_df_only[hired_df_only['واحد'] == top_hired_unit]
                    gender_html_top_unit = get_gender_glass_html(unit_specific, "#16a085")
                else:
                    top_hired_unit = "---"; top_hired_count = 0; gender_html_top_unit = ""

                # 8. شاخص تلاش
                if total_hired > 0:
                    effort_ratio = round(total_candidates / total_hired, 1)
                    effort_text = f"1 : {effort_ratio}"
                else:
                    effort_text = "---"

                # =========================================================
                # 2. نمایش کارت‌های رنگی (Soft Gradient Style)
                # =========================================================
                st.markdown("""
                <style>
                    .gradient-card {
                        border-radius: 16px;
                        padding: 16px;
                        height: 170px;
                        display: flex;
                        flex-direction: column;
                        justify-content: space-between;
                        position: relative;
                        overflow: hidden;
                        transition: transform 0.3s ease, box-shadow 0.3s ease;
                        border: 1px solid rgba(255,255,255,0.5);
                    }
                    
                    .gradient-card:hover {
                        transform: translateY(-5px);
                        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
                    }

                    .watermark-icon {
                        position: absolute;
                        top: -10px;
                        left: -10px;
                        font-size: 80px;
                        opacity: 0.1;
                        pointer-events: none;
                        transform: rotate(15deg);
                    }

                    .card-content {
                        position: relative;
                        z-index: 2;
                        display: flex;
                        flex-direction: column;
                        height: 100%;
                    }

                    .g-title {
                        font-size: 13px;
                        font-weight: 800;
                        color: rgba(0,0,0,0.6);
                        text-transform: uppercase;
                        letter-spacing: 0.5px;
                        margin-bottom: 5px;
                    }

                    .g-value {
                        font-size: 32px;
                        font-weight: 900;
                        color: #333;
                        margin-bottom: 2px;
                        text-shadow: 2px 2px 0px rgba(255,255,255,0.5);
                    }

                    .g-sub {
                        font-size: 11px;
                        color: rgba(0,0,0,0.5);
                        font-weight: 600;
                        margin-bottom: auto;
                    }
                </style>
                """, unsafe_allow_html=True)

                # --- ردیف اول ---
                r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
                
                with r1_c1: # کل متقاضیان
                    bg = "linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg};">
                        <div class="watermark-icon">📂</div>
                        <div class="card-content">
                            <div class="g-title">کل متقاضیان</div>
                            <div class="g-value">{total_candidates}</div>
                            <div class="g-sub">رزومه‌های دریافتی</div>
                            {gender_html_total}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with r1_c2: # نامشخص
                    bg = "linear-gradient(135deg, #f5f5f5 0%, #e0e0e0 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg};">
                        <div class="watermark-icon">❓</div>
                        <div class="card-content">
                            <div class="g-title">وضعیت نامشخص</div>
                            <div class="g-value">{total_unknown}</div>
                            <div class="g-sub">در انتظار بررسی</div>
                            {gender_html_unknown}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with r1_c3: # ترافیک مصاحبه (آمار جنسیت اضافه شد ✅)
                    bg = "linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg};">
                        <div class="watermark-icon">🔥</div>
                        <div class="card-content">
                            <div class="g-title">ترافیک مصاحبه</div>
                            <div class="g-value">{top_interview_count}</div>
                            <div class="g-sub">{top_interview_unit}</div>
                            {gender_html_interview}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                with r1_c4: # رد شده
                    bg = "linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg};">
                        <div class="watermark-icon">🛡️</div>
                        <div class="card-content">
                            <div class="g-title">رد شده</div>
                            <div class="g-value">{total_rejected}</div>
                            <div class="g-sub">در مرحله غربالگری</div>
                            <div style="margin-top:auto; font-size:11px; color:#b71c1c; background:rgba(255,255,255,0.5); padding:4px 8px; border-radius:6px; text-align:center;">
                                نرخ ریزش: {rejection_rate:.1f}٪
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                # --- ردیف دوم ---
                st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
                r2_c1, r2_c2, r2_c3, r2_c4 = st.columns(4)

                with r2_c1: # انصراف
                    bg = "linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg};">
                        <div class="watermark-icon">🏃</div>
                        <div class="card-content">
                            <div class="g-title">انصراف داوطلب</div>
                            <div class="g-value">{total_withdrawal}</div>
                            <div class="g-sub">خروج از فرآیند</div>
                            {gender_html_withdrawal}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with r2_c2: # استخدام نهایی
                    bg = "linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg};">
                        <div class="watermark-icon">🤝</div>
                        <div class="card-content">
                            <div class="g-title">استخدام نهایی</div>
                            <div class="g-value">{total_hired}</div>
                            <div class="g-sub">جذب موفق</div>
                            {gender_html_hired}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                with r2_c3: # بیشترین جذب
                    bg = "linear-gradient(135deg, #e0f2f1 0%, #b2dfdb 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg};">
                        <div class="watermark-icon">🏆</div>
                        <div class="card-content">
                            <div class="g-title">واحد برتر جذب</div>
                            <div class="g-value">{top_hired_count}</div>
                            <div class="g-sub">{top_hired_unit}</div>
                            {gender_html_top_unit}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with r2_c4: # شاخص تلاش
                    bg = "linear-gradient(135deg, #eceff1 0%, #cfd8dc 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg};">
                        <div class="watermark-icon">⚖️</div>
                        <div class="card-content">
                            <div class="g-title">شاخص تلاش</div>
                            <div class="g-value">{effort_text}</div>
                            <div class="g-sub">بررسی به ازای ۱ استخدام</div>
                            <div style="margin-top:auto; font-size:11px; color:#455a64; background:rgba(255,255,255,0.6); padding:4px 8px; border-radius:6px; text-align:center;">
                                کارایی فرآیند جذب
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                # =========================================================
                # 3. تحلیل عمیق و استراتژیک (Strategic Analysis)
                # =========================================================
                st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)
                
                # منطق تولید متن تحلیل
                if withdrawal_rate > rejection_rate:
                    main_insight = "⚠️ **چالش برند کارفرمایی:** نرخ انصراف بیشتر از نرخ رد شدن است. سازمان در «جذب» مشکل ندارد اما در «متقاعدسازی و نگهداشت» کاندیداها چالش دارد."
                    action_item = "بررسی رقابتی بودن حقوق و مزایا."
                    sentiment_color = "#fff3cd" # زرد
                elif rejection_rate > 70:
                    main_insight = "⚠️ **چالش کانال‌های ورودی:** نرخ رد شدن بسیار بالاست (بیش از ۷۰٪). زمان زیادی صرف مصاحبه با افراد نامرتبط می‌شود."
                    action_item = "اصلاح شرح شغل (Job Description) در آگهی‌ها + استفاده از فیلترهای اولیه دقیق‌تر."
                    sentiment_color = "#f8d7da" # قرمز
                else:
                    main_insight = "✅ **تعادل پایدار:** نسبت‌های جذب، رد و انصراف در وضعیت نرمال و سالمی قرار دارند."
                    action_item = "حفظ رویه فعلی و تمرکز بر کاهش زمان استخدام (Time to Hire)."
                    sentiment_color = "#d4edda" # سبز

                with st.expander("🧠اتاق فکر و بینش", expanded=False):
                    ac1, ac2, ac3 = st.columns([1.5, 1.5, 1])
                    
                    with ac1:
                        st.markdown(f"""
                        <div style="direction: rtl; text-align: right; height: 100%;">
                            <h5 style="color: #033270; border-bottom: 1px solid #eee; padding-bottom: 5px;">📊 تفسیر قیف جذب</h5>
                            <ul style="font-size: 13px; line-height: 2.2; color: #444;">
                                <li><b>کارایی سیستم:</b> برای هر استخدام نهایی، تیم منابع انسانی <b style="color:#033270">{selection_ratio.split(':')[1] if ':' in selection_ratio else 0}</b> مصاحبه انجام داده است.</li>
                                <li><b>کیفیت ورودی:</b> <b style="color:#e74c3c">{rejection_rate:.1f}٪</b> از متقاضیان استانداردهای لازم را نداشتند.</li>
                                <li><b>جذابیت سازمان:</b> <b style="color:#f39c12">{withdrawal_rate:.1f}٪</b> از افراد با وجود تایید اولیه، انصراف دادند.</li>
                            </ul>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with ac2:
                        st.markdown(f"""
                        <div style="direction: rtl; text-align: right; height: 100%;">
                            <h5 style="color: #033270; border-bottom: 1px solid #eee; padding-bottom: 5px;">💡 تجویز مدیریتی</h5>
                            <div style="background-color: {sentiment_color}; padding: 10px; border-radius: 8px; font-size: 13px; line-height: 1.6; color: #333;">
                                {main_insight}
                            </div>
                            <div style="margin-top: 10px; font-size: 12px; font-weight: bold; color: #033270;">
                                🚀 اقدام پیشنهادی:<br>
                                <span style="font-weight: normal; color: #555;">{action_item}</span>
                            </div>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    with ac3:
                        # نمایش شاخص کیفیت جذب به صورت دایره‌ای
                        st.markdown(f"""
                        <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%;">
                            <div style="font-size: 12px; color: #666; margin-bottom: 5px;">شاخص کیفیت جذب</div>
                            <div style="
                                width: 80px; height: 80px; 
                                border-radius: 50%; 
                                background: conic-gradient(#2ecc71 {health_score}%, #eee 0);
                                display: flex; align-items: center; justify-content: center;
                            ">
                                <div style="
                                    width: 65px; height: 65px; 
                                    background: white; 
                                    border-radius: 50%; 
                                    display: flex; align-items: center; justify-content: center;
                                    font-weight: bold; font-size: 18px; color: #2ecc71;
                                ">
                                    {health_score}
                                </div>
                            </div>
                            <div style="font-size: 11px; color: #999; margin-top: 5px;">از 100</div>
                        </div>
                        """, unsafe_allow_html=True)
                # --- استایل CSS ---
                st.markdown("""
                <style>
                div[data-testid="stExpander"] details > summary {
                    background-color: #033270 !important; color: white !important; border-radius: 10px !important; padding: 10px !important; border: 1px solid #033270 !important; margin-bottom: 0px !important;
                }
                div[data-testid="stExpander"] details > summary span, div[data-testid="stExpander"] details > summary p, div[data-testid="stExpander"] details > summary svg {
                    color: white !important; fill: white !important;
                }
                div[data-testid="stExpander"] details > div {
                    background-color: #ffffff !important; border: 2px solid #033270 !important; border-radius: 0 0 10px 10px !important; border-top: none !important; margin-top: -5px !important; padding-top: 15px !important; position: relative; z-index: 0;
                }
                div[data-testid="stExpander"] details[open] > summary {
                    border-bottom-left-radius: 0 !important; border-bottom-right-radius: 0 !important; border-bottom: 1px solid #033270 !important;
                }
                </style>
                """, unsafe_allow_html=True)

                # =========================================================
                # گام ۱: انجام تمام محاسبات (قبل از رسم)
                # =========================================================
                
                # --- محاسبات سمت راست (قیف جذب) ---
                if 'واحد' in df_emp.columns:
                    interview_counts = df_emp['واحد'].value_counts()
                    # شرط استخدام (بدون فیلتر رد شد)
                    if 'تاریخ شروع بکار' in df_emp.columns:
                        hired_mask = (df_emp['تاریخ شروع بکار'].notna()) & \
                                     (~df_emp['تاریخ شروع بکار'].astype(str).str.contains('عدم استخدام|نامشخص', case=False, na=False))
                        hired_counts = df_emp.loc[hired_mask, 'واحد'].value_counts()
                    else:
                        hired_counts = pd.Series()
                    
                    df_chart_all = pd.DataFrame({'Interview': interview_counts, 'Hired': hired_counts}).fillna(0)
                    df_chart_all['Hired'] = df_chart_all['Hired'].astype(int)
                    df_chart_all['Rate'] = (df_chart_all['Hired'] / df_chart_all['Interview'] * 100).fillna(0).round(1)
                    
                    # شاخص‌های کلیدی
                    total_int_sum = df_chart_all['Interview'].sum()
                    total_hired_sum = df_chart_all['Hired'].sum()
                    avg_conversion = (total_hired_sum / total_int_sum * 100) if total_int_sum > 0 else 0
                    iph = (total_int_sum / total_hired_sum) if total_hired_sum > 0 else total_int_sum
                    
                    # پیدا کردن بهترین و بدترین واحد
                    if not df_chart_all.empty:
                        qualified = df_chart_all[df_chart_all['Interview'] >= 3]
                        if not qualified.empty:
                            best_unit = qualified.sort_values('Rate', ascending=False).iloc[0]
                            worst_unit = qualified.sort_values('Rate', ascending=True).iloc[0]
                        else:
                            best_unit = worst_unit = df_chart_all.iloc[0]
                    else:
                        best_unit = None
                else:
                    df_chart_all = pd.DataFrame()

                # --- محاسبات سمت چپ (کانال جذب) ---
                if 'معرف' in df_emp.columns:
                    df_emp['معرف'] = df_emp['معرف'].fillna('نامشخص').astype(str)
                    referrer_total = df_emp['معرف'].value_counts()
                    
                    if 'تاریخ شروع بکار' in df_emp.columns:
                        hired_from_referrer = df_emp[
                            (df_emp['تاریخ شروع بکار'].notna()) & 
                            (~df_emp['تاریخ شروع بکار'].astype(str).str.contains('عدم استخدام|نامشخص', case=False, na=False))
                        ]['معرف'].value_counts()
                    else:
                        hired_from_referrer = pd.Series()
                    
                    ref_df = pd.DataFrame({'کل معرفی': referrer_total}).reset_index()
                    ref_df.columns = ['معرف', 'کل معرفی']
                    ref_df['جذب شده'] = ref_df['معرف'].map(hired_from_referrer).fillna(0)
                    ref_df['نرخ تبدیل'] = (ref_df['جذب شده'] / ref_df['کل معرفی'] * 100).fillna(0)
                else:
                    ref_df = pd.DataFrame()

                # =========================================================
                # گام ۲: رسم ردیف اول (فقط نمودارها)
                # =========================================================
                col_chart_right, col_chart_left = st.columns(2)

                # --- رسم نمودار راست ---
                with col_chart_right:
                    if not df_chart_all.empty:
                        df_chart_plot = df_chart_all.sort_values('Interview', ascending=False)
                        fig_ov = go.Figure()
                        fig_ov.add_trace(go.Bar(
                            x=df_chart_plot.index, y=df_chart_plot['Interview'], name='کل متقاضیان',
                            marker_color='rgba(189, 195, 199, 0.5)', marker_line_width=0, width=0.75,
                            hovertemplate='واحد: %{x}<br>کل مصاحبه: %{y}<extra></extra>'
                        ))
                        fig_ov.add_trace(go.Bar(
                            x=df_chart_plot.index, y=df_chart_plot['Hired'], name='جذب موفق',
                            marker_color='#033270', width=0.35, text=df_chart_plot['Hired'], textposition='outside',
                            textfont=dict(color='#033270', weight='bold', size=13),
                            hovertemplate='واحد: %{x}<br>تعداد جذب: %{y}<br>نرخ موفقیت: %{customdata}%<extra></extra>',
                            customdata=df_chart_plot['Rate']
                        ))
                        max_y_ov = df_chart_plot['Interview'].max() if not df_chart_plot.empty else 10
                        fig_ov.update_layout(
                            title={'text': '📊 کارنامه جذب واحدها', 'y': 0.95, 'x': 1, 'xanchor': 'right', 'xref': 'paper'},
                            title_font=dict(size=16, family="Vazirmatn, Arial", color='#033270', weight="bold"),
                            font=dict(family="Vazirmatn, Arial", size=12, color="black"),
                            plot_bgcolor='#ffffff',paper_bgcolor='#ffffff',height=480, barmode='overlay',
                            legend=dict(
                            orientation="h",       # افقی
                            yanchor="top",         # تراز از بالا
                            y=0.99,                # چسبیده به سقف (داخل کادر)
                            xanchor="left",        # تراز از چپ
                            x=0.01,                # چسبیده به چپ (داخل کادر)
                            bgcolor='rgba(255, 255, 255, 0.8)', # پس‌زمینه سفید نیمه‌شفاف
                            font=dict(color="black")
                            # خطوط مربوط به کادر (border) حذف شدند
                        ),
                            xaxis=dict(tickangle=-45, tickfont=dict(size=11, weight='bold', color='black'), showline=True, linecolor='#ccc'),
                            yaxis=dict(title="تعداد نفرات", showgrid=True, gridcolor='#eee', tickfont=dict(color='black'), range=[0, max_y_ov * 1.25]),
                            margin=dict(t=80, b=80, l=50, r=40)
                        )
                        st.plotly_chart(fig_ov, use_container_width=True, theme=None)
                    else:
                        st.warning("داده‌ای برای واحدها یافت نشد.")

                # --- رسم نمودار چپ ---
                with col_chart_left:
                    if not ref_df.empty:
                        plot_df = ref_df[ref_df['کل معرفی'] > 0].sort_values('جذب شده', ascending=False).head(8)
                        fig_ref = go.Figure()
                        fig_ref.add_trace(go.Bar(
                            x=plot_df['معرف'], y=plot_df['کل معرفی'], name='تعداد ورودی', 
                            marker_color='#4FC3F7', marker_line_width=0, text=plot_df['کل معرفی'], 
                            textposition='outside', marker_cornerradius=8, textfont=dict(size=11, color='#000000'), cliponaxis=False
                        ))
                        fig_ref.add_trace(go.Scatter(
                            x=plot_df['معرف'], y=plot_df['جذب شده'], name='استخدام موفق', 
                            mode='lines+markers+text', text=plot_df['جذب شده'], textposition='top center',
                            textfont=dict(color='#0D47A1', weight='bold'), line=dict(color='#0D47A1', width=3),
                            marker=dict(size=12, color='#0D47A1', line=dict(width=2, color='white'))
                        ))
                        max_ref = plot_df['کل معرفی'].max() if not plot_df.empty else 10
                        fig_ref.update_layout(
                            title={'text': '<b>💎 عملکرد کانال‌های جذب نیرو</b>', 'y': 0.95, 'x': 1, 'xanchor': 'right', 'xref': 'paper'},
                            title_font=dict(size=18, family="Vazirmatn, Arial", color='#033270', weight="bold"),
                            font=dict(family="Vazirmatn, Arial", size=12, color="#000000"),
                            plot_bgcolor='#f8f9fa', paper_bgcolor='white', height=480,
                            xaxis=dict(title="", tickfont=dict(color="#000000", weight="bold"), automargin=True),
                            yaxis=dict(title="تعداد نفرات", showgrid=True, gridcolor='#e0e0e0', griddash='dash', title_font=dict(color="#000000", size=13, weight="bold"), tickfont=dict(color="#000000"), range=[0, max_ref * 1.3]),
                            legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0, font=dict(color="black")),
                            margin=dict(t=80, b=50, l=40, r=40)
                        )
                        st.plotly_chart(fig_ref, use_container_width=True, theme=None)
                    else:
                        st.warning("داده‌ای برای کانال‌ها یافت نشد.")
# =========================================================
                # ردیف دوم: فقط تحلیل‌ها (اصلاح شده: فونت و تراز کارت‌ها)
                # =========================================================
                st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
                col_anal_right, col_anal_left = st.columns(2)

                # --- تحلیل سمت راست (Executive Summary) ---
                with col_anal_right:
                    if not df_chart_all.empty and best_unit is not None:
                        with st.expander("🎯 تابلوی فرمان شاخص‌ها ", expanded=False):
                            c1, c2, c3, c4 = st.columns(4)
                            
                            # استایل مشترک برای کارت‌ها (ارتفاع ثابت برای تراز شدن خط زیرین)
                            card_style = "text-align: center; border-bottom: 3px solid {}; padding-bottom: 10px; height: 120px; display: flex; flex-direction: column; justify-content: center; align-items: center;"
                            
                            with c1:
                                st.markdown(f"""<div style="{card_style.format('#033270')}"><span style="font-size: 11px; color: #666;">کل استخدام‌ها</span><div style="font-size: 22px; font-weight: 900; color: #033270; margin: 5px 0;">{total_hired_sum}</div><span style="font-size: 10px; color: #888;">نفر</span></div>""", unsafe_allow_html=True)
                            with c2:
                                st.markdown(f"""<div style="{card_style.format('#3498db')}"><span style="font-size: 11px; color: #666;">نرخ تبدیل سازمان</span><div style="font-size: 22px; font-weight: 900; color: #3498db; margin: 5px 0;">{avg_conversion:.1f}%</div></div>""", unsafe_allow_html=True)
                            with c3:
                                iph_color = "#27ae60" if iph < 5 else ("#f39c12" if iph < 10 else "#e74c3c")
                                st.markdown(f"""<div style="{card_style.format(iph_color)}"><span style="font-size: 11px; color: #666;">شاخص تلاش (IPH)</span><div style="font-size: 22px; font-weight: 900; color: {iph_color}; margin: 5px 0;">{iph:.1f}</div><span style="font-size: 10px; color: #888;">مصاحبه/استخدام</span></div>""", unsafe_allow_html=True)
                            with c4:
                                st.markdown(f"""<div style="{card_style.format('#2ecc71')}"><span style="font-size: 11px; color: #666;">واحد ستاره</span><div style="font-size: 15px; font-weight: 900; color: #2ecc71; margin: 5px 0;">{best_unit.name}</div><span style="font-size: 10px; color: #27ae60;">نرخ: {best_unit['Rate']}%</span></div>""", unsafe_allow_html=True)

                            gap = best_unit['Rate'] - avg_conversion
                            efficiency_status = "مطلوب" if iph < 6 else ("نیازمند بهبود" if iph < 12 else "بحرانی")
                            
                            analysis_text = f"""
                            <div style="direction: rtl; font-size: 13px; line-height: 2.4; text-align: justify; color: #333;">
                                <b>💡 تحلیل عملکرد جذب:</b><br>
                                در بازه زمانی فعلی، سازمان برای جذب هر <b>۱ نفر</b> نیروی انسانی، به طور متوسط با <b>{iph:.1f} نفر</b> مصاحبه انجام داده است که نشان‌دهنده وضعیت <b>«{efficiency_status}»</b> در غربالگری اولیه است.
                                <br>
                                <ul>
                                    <li><b>نقطه قوت (Strength):</b> واحد <b>«{best_unit.name}»</b> با نرخ تبدیل <b>{best_unit['Rate']}%</b> (حدود <b>{gap:+.1f}%</b> بالاتر از میانگین سازمان)، بهینه‌ترین فرآیند انتخاب را داشته است.</li>
                                    <li><b>نقطه تمرکز (Focus Area):</b> واحد <b>«{worst_unit.name}»</b> با نرخ تبدیل <b>{worst_unit['Rate']}%</b>، بیشترین هدررفت زمان مصاحبه را داشته است. پیشنهاد می‌شود شرح شغل (JD) بازنگری شود.</li>
                                </ul>
                            </div>
                            """
                            st.markdown(analysis_text, unsafe_allow_html=True)
                    else:
                        st.info("داده کافی برای تحلیل موجود نیست.")

                # --- تحلیل سمت چپ (Sourcing Analysis) ---
                with col_anal_left:
                    if not ref_df.empty:
                        with st.expander("📊 تحلیل عملکرد کانال‌های جذب", expanded=False):
                            top_volume_channel = ref_df.sort_values('کل معرفی', ascending=False).iloc[0]
                            top_quality_channel = ref_df[ref_df['کل معرفی'] >= 3].sort_values('نرخ تبدیل', ascending=False).iloc[0] if len(ref_df) > 0 else top_volume_channel
                            
                            # ✅ اصلاح سایز فونت به 13px برای هماهنگی با سمت راست
                            st.markdown(f"""
                            <div style="color: #333 !important; text-align: right; direction: rtl; line-height: 2.4; font-size: 13px;">
                            <b>🧠 بینش آماری:</b><br>
                            🔹 <b>کانال حجمی:</b> بیشترین رزومه از <b>«{top_volume_channel['معرف']}»</b> ({int(top_volume_channel['کل معرفی'])} مورد).<br>
                            🔸 <b>کانال کیفی:</b> بهترین بازدهی مربوط به <b>«{top_quality_channel['معرف']}»</b> با نرخ <b>{top_quality_channel['نرخ تبدیل']:.1f}٪</b> است.
                            </div>
                            <div style="margin-bottom: 15px;"></div>
                            """, unsafe_allow_html=True)
                            
                            display_ref_df = ref_df[['معرف', 'کل معرفی', 'جذب شده', 'نرخ تبدیل']].sort_values('نرخ تبدیل', ascending=False).head(10)
                            display_ref_df.columns = ['کانال', 'ورودی', 'جذب', 'نرخ تبدیل (%)']
                            st.dataframe(display_ref_df.style.format({'نرخ تبدیل (%)': '{:.1f}%', 'ورودی': '{:,}', 'جذب': '{:,}'}).background_gradient(cmap='Greens', subset=['نرخ تبدیل (%)']), use_container_width=True)
                    else:
                        st.info("داده کافی برای تحلیل موجود نیست.")
# =========================================================
                # 3. بخش نمودارهای تحلیل ریزش (نمودار سوم و چهارم) - اصلاح نهایی و قطعی
                # =========================================================
                st.markdown("<div style='margin-top: -30px;'></div>", unsafe_allow_html=True)
            
                # 1. آماده‌سازی و فیلتر داده‌ها
                status_col = df_emp['وضعیت نهایی'] if 'وضعیت نهایی' in df_emp.columns else pd.Series()
                # تبدیل به رشته و حذف فاصله برای اطمینان از فیلتر صحیح
                churn_mask = status_col.astype(str).str.strip().isin(['رد شد', 'انصراف داد'])
                churn_df = df_emp[churn_mask].copy()
                
                # پر کردن ستون‌های خالی برای جلوگیری از ارور
                if 'علت_دسته_بندی_شده' not in churn_df.columns:
                    if 'علت نپذیرفتن' in churn_df.columns:
                        churn_df['علت نپذیرفتن'] = churn_df['علت نپذیرفتن'].fillna('نامشخص').replace(['-', ''], 'نامشخص')
                        churn_df['علت_دسته_بندی_شده'] = churn_df['علت نپذیرفتن'].apply(categorize_reason)
                    else:
                        churn_df['علت_دسته_بندی_شده'] = 'نامشخص'; churn_df['علت نپذیرفتن'] = 'نامشخص'

                if len(churn_df) > 0:
                    fixed_chart_height = 460
                    total_churn_count = len(churn_df)
                    
                    # =====================================================
                    # ردیف اول: رسم نمودارها
                    # =====================================================
                    c_chart_right, c_chart_left = st.columns([2, 1])
                    
                    # --- نمودار سوم (راست - Scatter) ---
                    with c_chart_right:
                        h_filter, h_title = st.columns([1, 2])
                        with h_title:
                            st.markdown("<h3 style='text-align: right; margin: 0; padding-top: 5px; color:#033270; font-size:16px; font-weight:bold; font-family:tahoma;'>نقشه حرارتی ریزش نیرو🗺️</h3>", unsafe_allow_html=True)
                        with h_filter:
                            selected_view = st.selectbox("سطح نمایش:", ["👁️ نمای هلیکوپتری (کلان)", "📂 تفکیک واحدی", "🔍 ریشه‌یابی دقیق"], key="lvl_select_final", label_visibility="collapsed")
                        
                        import textwrap
                        if "👁️ نمای هلیکوپتری (کلان)" in selected_view:
                            plot_df = churn_df.copy(); y_col = 'وضعیت نهایی'; color_col = 'وضعیت نهایی'; color_scale = None; color_map = {'رد شد': '#c0392b', 'انصراف داد': '#e67e22'} 
                        elif "📂 تفکیک واحدی" in selected_view:
                            plot_df = churn_df.copy(); y_col = 'علت_دسته_بندی_شده'; color_col = 'تعداد'; color_scale = 'Reds'; color_map=None
                        else:
                            plot_df = churn_df.copy(); y_col = 'علت نپذیرفتن'; color_col = 'تعداد'; color_scale = 'Oranges'; color_map=None

                        if y_col not in plot_df.columns: plot_df[y_col] = "نامشخص"

                        chart_data = plot_df.groupby([y_col, 'واحد']).size().reset_index(name='تعداد')
                        chart_data['نمایش_محور'] = chart_data[y_col].apply(lambda x: '<br>'.join(textwrap.wrap(str(x), width=35)))
                        
                        fig_main = px.scatter(
                            chart_data, x='واحد', y='نمایش_محور', size='تعداد', 
                            color=color_col, color_continuous_scale=color_scale, color_discrete_map=color_map,
                            size_max=50, text='تعداد'
                        )
                        fig_main.update_traces(textposition='top center', textfont=dict(family="Vazirmatn, Tahoma", size=14, color="black", weight="bold"), marker=dict(line=dict(width=1, color='DarkSlateGrey')))
                        fig_main.update_layout(
                            font=dict(family="Vazirmatn, Tahoma", size=13, color="black"),
                            plot_bgcolor='#ffffff', paper_bgcolor='#ffffff', height=fixed_chart_height,
                            margin=dict(t=30, b=110, l=160, r=20),
                            xaxis=dict(title="", tickangle=-45, tickfont=dict(size=12, weight='bold', color='black'), showline=True, linecolor='black', linewidth=1.5, gridcolor='#e9ecef', automargin=True),
                            yaxis=dict(title="", tickfont=dict(size=12, weight='bold', color='black'), showline=True, linecolor='black', linewidth=1.5, gridcolor='#d3d3d3'),
                            legend=dict(font=dict(color="black", size=12, weight="bold"), orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                            coloraxis_colorbar=dict(title=dict(text="تعداد", font=dict(color="black", weight="bold")), tickfont=dict(color="black", weight="bold"))
                        )
                        st.plotly_chart(fig_main, use_container_width=True, key="main_chart_black_text", theme=None)

                    # --- نمودار چهارم (چپ - Pareto) ---
                    with c_chart_left:
                        st.markdown("<div style='height: 8px;'></div>", unsafe_allow_html=True)
                        st.markdown("<div style='text-align: right; border-bottom: 2px solid #eee; margin-bottom: 10px;'><span style='color:#033270; font-size:15px; font-weight:bold; font-family:tahoma;'>گلوگاه‌های اصلی (پارتو)🚧</span></div>", unsafe_allow_html=True)
                        
                        if 'علت_دسته_بندی_شده' in churn_df.columns:
                            pareto_df = churn_df['علت_دسته_بندی_شده'].value_counts().head(5).reset_index()
                            pareto_df.columns = ['علت', 'تعداد']
                            pareto_df['درصد_از_کل'] = ((pareto_df['تعداد'] / total_churn_count) * 100).round(1)
                            max_val = pareto_df['تعداد'].max() if len(pareto_df) > 0 else 10
                            
                            fig_pareto = px.bar(pareto_df, x='علت', y='تعداد', text='تعداد', color='تعداد', color_continuous_scale='Reds', custom_data=['درصد_از_کل'])
                            fig_pareto.update_traces(textposition='outside', marker_cornerradius=6, textfont=dict(size=14, weight="bold", color="#000000"), cliponaxis=False, hovertemplate="<b>%{x}</b><br>تعداد: %{y}<br>سهم از کل: %{customdata[0]}%<extra></extra>")
                            fig_pareto.update_layout(
                                font=dict(family="Vazirmatn, Tahoma", size=12, color="black"),
                                plot_bgcolor='#ffffff', paper_bgcolor='#ffffff', height=fixed_chart_height,
                                xaxis=dict(title="", tickangle=-45, tickfont=dict(size=13, weight="bold", color="#000000"), showline=True, linecolor="black", linewidth=2, automargin=True),
                                yaxis=dict(title="", showgrid=False, showticklabels=True, tickfont=dict(size=12, weight="bold", color="#000000"), range=[0, max_val * 1.35]),
                                margin=dict(t=40, b=130, l=80, r=20), showlegend=False, coloraxis_showscale=False
                            )
                            st.plotly_chart(fig_pareto, use_container_width=True, key="pareto_chart_margin_fix", theme=None)
                        else:
                            st.error("داده‌های پارتو یافت نشد.")

                    # =====================================================
                    # ردیف دوم: تحلیل‌های هوشمند (تراز شده)
                    # =====================================================
                    st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
                    c_an_right, c_an_left = st.columns([2, 1])

                    # --- تحلیل ساده و کاربردی نمودار سوم (راست) ---
                    with c_an_right:
                        try:
                            # 1. محاسبات امن (با استفاده از جستجوی متنی منعطف)
                            total_c = len(churn_df)
                            
                            # شمارش منعطف: هر سلولی که شامل کلمه باشد را می‌شمارد
                            status_str = churn_df['وضعیت نهایی'].astype(str)
                            rej_count = len(churn_df[status_str.str.contains('رد|عدم|کنسل|reject', case=False, na=False)])
                            wdr_count = len(churn_df[status_str.str.contains('انصراف|withdrawal', case=False, na=False)])
                            
                            # جلوگیری از تقسیم بر صفر
                            if total_c > 0:
                                rr = int((rej_count / total_c) * 100)
                                wr = int((wdr_count / total_c) * 100)
                            else:
                                rr = 0; wr = 0
                            
                            # پیدا کردن واحدی که بیشترین مشکل را دارد
                            if not churn_df.empty:
                                top_unit = churn_df['واحد'].value_counts().idxmax()
                            else:
                                top_unit = "---"
                            
                            # 2. منطق تحلیل ساده
                            if wr > rr:
                                state_title = "📉 چالش جذابیت شغلی"
                                state_desc = "تعداد **انصرافی‌ها** بیشتر است. متقاضیان شرایط (حقوق/ساعت) را نمی‌پسندند."
                                bg_color = "#fff3e0"; border_color = "#ef6c00"; icon = "⚠️"
                                action = "آیا حقوق و مزایا رقابتی است؟"
                            elif rr > wr:
                                state_title = "🔍 ورودی‌های نامناسب"
                                state_desc = "تعداد **رد شدگان** بیشتر است. رزومه‌های غیرمرتبط زیادی دریافت می‌کنید."
                                bg_color = "#ffebee"; border_color = "#c62828"; icon = "🚫"
                                action = "شرایط احراز شغل را شفاف‌تر کنید."
                            else:
                                state_title = "⚖️ وضعیت متعادل"
                                state_desc = "نرخ رد و انصراف تقریباً برابر است."
                                bg_color = "#e8f5e9"; border_color = "#2e7d32"; icon = "✅"
                                action = "فرآیند فعلی مطلوب است."

                            # 3. نمایش (داخل Expander)
                            with st.expander(" ⚖️ترازنامه رد و انصراف ", expanded=False):
                                st.markdown(f"""
                                <div style="font-size: 13px; line-height: 2.2; direction: rtl; text-align: justify; color: #333;">
                                    <div style="background-color: {bg_color}; border-right: 4px solid {border_color}; padding: 10px; border-radius: 6px; margin-bottom: 15px;">
                                        <div style="font-weight: bold; color: {border_color}; font-size: 14px; margin-bottom: 5px;">
                                            {icon} {state_title}
                                        </div>
                                        {state_desc}
                                    </div>
                                    <div style="display: flex; justify-content: space-between; text-align: center; margin-bottom: 15px; border-bottom: 1px dashed #ccc; padding-bottom: 10px;">
                                        <div><div style="color: #666; font-size: 11px;">نرخ انصراف</div><div style="font-weight: bold; color: #ef6c00; font-size: 16px;">{wr}%</div></div>
                                        <div><div style="color: #666; font-size: 11px;">نرخ رد شدن</div><div style="font-weight: bold; color: #c62828; font-size: 16px;">{rr}%</div></div>
                                        <div><div style="color: #666; font-size: 11px;">واحد پرچالش</div><div style="font-weight: bold; color: #333; font-size: 14px;">{top_unit}</div></div>
                                    </div>
                                    <div><b>💡 پیشنهاد:</b> <span style="color: {border_color};">{action}</span></div>
                                </div>
                                """, unsafe_allow_html=True)
                        except Exception as e:
                            st.error(f"خطا در تحلیل: {e}")
                    # --- تحلیل حرفه‌ای نمودار چهارم (چپ) ---
                with c_an_left:
                        if 'علت' in pareto_df.columns and not pareto_df.empty:
                            # محاسبات پارتو
                            top_cause = pareto_df.iloc[0]
                            top3_df = pareto_df.head(3)
                            cumulative_impact = top3_df['درصد_از_کل'].sum()
                            top_cause_name = top_cause['علت']
                            top_cause_impact = top_cause['درصد_از_کل']
                            
                            # دیکشنری راهکارها
                            solution_map = {
                                'حقوق': ("بازنگری در جبران خدمات", "بنچ‌مارک مجدد حقوق با بازار و بررسی مزایا."),
                                'مسیر': ("موانع لجستیکی", "بررسی سرویس ایاب و ذهاب."),
                                'فنی': ("شکاف مهارتی", "بازنگری شرح شغل (JD)."),
                                'ساعت': ("تعادل کار و زندگی", "شفاف‌سازی شرایط کار در آگهی."),
                                'محیط': ("برند کارفرمایی", "بهبود فضای کاری و فرهنگ سازمانی."),
                                'عدم تایید': ("کیفیت ورودی", "اصلاح فیلترهای اولیه.")
                            }
                            
                            strategic_action = ("بررسی مصاحبه خروج", "انجام مصاحبه عمیق با افراد انصرافی.")
                            for key, value in solution_map.items():
                                if key in str(top_cause_name):
                                    strategic_action = value
                                    break
                            
                            if cumulative_impact >= 80: focus_msg = "🔴 **تمرکز حیاتی:**"
                            elif cumulative_impact >= 50: focus_msg = "🟠 **تمرکز بالا:**"
                            else: focus_msg = "🟡 **پراکندگی دلایل:**"

                            with st.expander("🩺 عارضه‌یابی ریشه‌ای و تجویز راهبردی ", expanded=False):
                                st.markdown(f"""
                                <div style="font-size: 13px; line-height: 2.4; text-align: justify; direction: rtl; color: #333;">
                                    <div style="background-color: #f8f9fa; border-right: 4px solid #d35400; padding: 10px 12px; border-radius: 4px; margin-bottom: 10px;">
                                        <div style="color: #d35400; font-weight: bold; font-size: 13px; margin-bottom: 3px;">⚠️ گلوگاه اصلی: {top_cause_name}</div>
                                        عامل <b>«{top_cause_name}»</b> مسئول <b>{top_cause_impact:.1f}٪</b> از کل شکست‌هاست.
                                    </div>
                                    <div style="margin-bottom: 8px;">
                                        <b>📊 تحلیل پارتو:</b><br>
                                        {focus_msg} ۳ عامل اول، <b>{cumulative_impact:.1f}٪</b> مشکلات را ایجاد کرده‌اند.
                                    </div>
                                    <div style="border-top: 1px dashed #ccc; margin-top: 10px; padding-top: 10px;">
                                        <b>🚀 تجویز ({strategic_action[0]}):</b><br>
                                        <span style="color: #2c3e50;">{strategic_action[1]}</span>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                        else:
                            st.info("داده‌ای برای تحلیل موجود نیست.")
            else:
                    st.success("✨ داده‌ای برای تحلیل ریزش موجود نیست.")
                    
    # ---------------------------------------------------------
    # بخش 1: رویدادها
    # ---------------------------------------------------------
    elif st.session_state.hr_active_tab == "رویدادها":
        st.subheader("📅 رویدادها و برنامه‌های آینده")
        col1, col2 = st.columns(2)
        with col1:
            st.info("**جلسه معارفه کارکنان جدید**\n\nتاریخ: 1403/09/25\nساعت: 10:00")
            st.success("**دوره آموزشی ایمنی**\n\nتاریخ: 1403/09/28\nساعت: 14:00")
        with col2:
            st.warning("**بازنگری قراردادها**\n\nتاریخ: 1403/10/01\nساعت: 09:00")
            st.error("**ارزیابی عملکرد فصلی**\n\nتاریخ: 1403/10/05\nساعت: 11:00")
   # ---------------------------------------------------------
    # بخش 2: لیست پرسنل
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # بخش 3: لیست جامع پرسنل (با ترتیب ستون‌های درخواستی)
    # ---------------------------------------------------------
    elif st.session_state.hr_active_tab == "لیست جامع پرسنل":
        ensure_data_loaded("personnel")
        st.subheader("🗂️  لیست جامع پرسنل")
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔄 بارگذاری مجدد", use_container_width=True, key="reload_personnel"):
                fetch_and_clean_data.clear()
                with st.spinner("در حال بارگذاری..."):
                    load_personnel_data()
                st.rerun()
        
        if st.session_state.last_update_personnel:
            shamsi_date = jdatetime.datetime.fromgregorian(datetime=st.session_state.last_update_personnel)
            st.info(f"آخرین به‌روزرسانی: {shamsi_date.strftime('%Y/%m/%d - %H:%M:%S')}")
        
        if st.session_state.personnel_data is not None:
            df = st.session_state.personnel_data.copy()
            
            # 1. تمیزکاری نام ستون‌ها (حذف فاصله و ی/ک عربی)
            df.columns = [str(col).strip().replace('ي', 'ی').replace('ك', 'ک') for col in df.columns]

            # 2. فیلترها
            st.markdown("### 🔍 فیلترها")
            col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4)
            
            with col_filter1: family_filter = st.text_input("نام خانوادگی", key="family_filter")
            with col_filter2: personnel_code_filter = st.text_input("شماره پرسنلی", key="personnel_code_filter")
            
            with col_filter3:
                subgroup_col = 'زیر گروه' if 'زیر گروه' in df.columns else ('زیرگروه' if 'زیرگروه' in df.columns else None)
                if subgroup_col:
                    all_subgroups = ['همه'] + sorted(df[subgroup_col].dropna().unique().tolist())
                    subgroup_filter = st.selectbox("زیر گروه", all_subgroups, key="subgroup_filter")
                else: subgroup_filter = "همه"
            
            with col_filter4:
                if 'واحد' in df.columns:
                    if subgroup_filter != "همه" and subgroup_col:
                        valid_units_df = df[df[subgroup_col] == subgroup_filter]
                        available_units = ['همه'] + sorted(valid_units_df['واحد'].dropna().unique().tolist())
                    else:
                        available_units = ['همه'] + sorted(df['واحد'].dropna().unique().tolist())
                    unit_filter = st.selectbox("واحد سازمانی", available_units, key="unit_filter")
                else: unit_filter = "همه"
            
            # 3. اعمال فیلتر
            filtered_df = df.copy()
            if family_filter and 'نام خانوادگی' in df.columns: 
                filtered_df = filtered_df[filtered_df['نام خانوادگی'].astype(str).str.contains(family_filter, na=False, case=False)]
            if personnel_code_filter and 'شماره پرسنلی' in df.columns: 
                filtered_df = filtered_df[filtered_df['شماره پرسنلی'].astype(str).str.contains(personnel_code_filter, na=False)]
            if subgroup_filter != "همه" and subgroup_col: 
                filtered_df = filtered_df[filtered_df[subgroup_col] == subgroup_filter]
            if unit_filter != "همه" and 'واحد' in df.columns: 
                filtered_df = filtered_df[filtered_df['واحد'] == unit_filter]
            
            # 4. تنظیم ترتیب ستون‌ها (دقیقاً طبق لیست شما)
            target_columns_personnel = [
   
                "محل خدمت",
                "میانگین حقوق"
                "رشته تحصیلی",
                "وضعیت نظام وظیفه",
                "تعداد فرزند",
                "وضعیت تاهل",
                "جنسیت",
                "میزان تحصیلات",
                "آدرس",
                "تاریخ تولد",
                "نوع قرارداد",
                "وضعیت کار",
                "تاریخ ترک کار",
                "مدت آخرین قرارداد(ماه)",
                "تاریخ آخرین قرارداد",
                "تاریخ استخدام",
                "زیر گروه",
                "واحد",
                "نام خانوادگی",
                "نام",
                "شماره پرسنلی",
            ]
            
            # انتخاب ستون‌هایی که در فایل موجود هستند
            final_cols = [col for col in target_columns_personnel if col in filtered_df.columns]
            
            if final_cols:
                filtered_df = filtered_df[final_cols]

            st.dataframe(filtered_df, use_container_width=True, height=600, hide_index=True)
        else:
            st.warning("هنوز داده‌ای بارگذاری نشده است.")
   # ---------------------------------------------------------
    # بخش 4: جذب و استخدام (اصلاح نهایی و قطعی)
    # ---------------------------------------------------------
    elif st.session_state.hr_active_tab == "جذب و استخدام":
        ensure_data_loaded("employee")
        st.subheader("📝 جذب و استخدام")
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔄 بارگذاری مجدد", use_container_width=True, key="reload_employee"):
                fetch_and_clean_data.clear()
                with st.spinner("در حال بارگذاری..."):
                    load_employee_data()
                st.rerun()
        
        if st.session_state.last_update_employee:
            shamsi_date = jdatetime.datetime.fromgregorian(datetime=st.session_state.last_update_employee)
            st.info(f"آخرین به‌روزرسانی: {shamsi_date.strftime('%Y/%m/%d - %H:%M:%S')}")
        
        # --- اصلاح مهم: بررسی وجود داده ---
        if st.session_state.employee_data is not None:
            # 1. ابتدا متغیر را می‌سازیم
            df_emp = st.session_state.employee_data.copy()
            
            # 2. تمام محاسبات حتماً باید با یک پله فاصله (Indent) داخل همین if باشند
            total_interviewed = len(df_emp)
            
            if 'تاریخ شروع بکار' in df_emp.columns:
                hired_df = df_emp[(df_emp['تاریخ شروع بکار'].notna()) & (~df_emp['تاریخ شروع بکار'].astype(str).str.contains('عدم استخدام|نامشخص', case=False, na=False))]
            else: 
                hired_df = pd.DataFrame()

            hired_count = len(hired_df)
            hired_percentage = round((hired_count / total_interviewed) * 100, 1) if total_interviewed > 0 else 0
            
            most_interviewed_unit = "نامشخص"; most_interviewed_count = 0; most_interviewed_percentage = 0
            if 'واحد' in df_emp.columns:
                unit_counts = df_emp['واحد'].value_counts()
                if len(unit_counts) > 0:
                    most_interviewed_unit = unit_counts.index[0]
                    most_interviewed_count = unit_counts.iloc[0]
                    if total_interviewed > 0: most_interviewed_percentage = round((most_interviewed_count / total_interviewed) * 100, 1)
            
            most_hired_unit = "نامشخص"
            if not hired_df.empty and 'واحد' in hired_df.columns:
                hired_units = hired_df['واحد'].value_counts()
                if len(hired_units) > 0: most_hired_unit = hired_units.index[0]
            
            gender_percentages = {"مرد": 0, "زن": 0}
            if not hired_df.empty and 'جنسیت' in hired_df.columns:
                gender_counts = hired_df['جنسیت'].value_counts()
                total_hired_len = len(hired_df)
                for gender in gender_counts.index:
                    if gender in gender_percentages: gender_percentages[gender] = round((gender_counts[gender] / total_hired_len) * 100, 1)
            
            undecided_count = 0; undecided_percentage = 0
            if 'تاریخ شروع بکار' in df_emp.columns:
                undecided_df = df_emp[df_emp['تاریخ شروع بکار'].astype(str).str.contains('نامشخص', case=False, na=False)]
                undecided_count = len(undecided_df)
                if total_interviewed > 0: undecided_percentage = round((undecided_count / total_interviewed) * 100, 1)
            
            st.markdown("### 📊 آمار استخدام")
            col1, col2, col3, col4, col5 = st.columns(5)
            with col1: st.markdown(f'<div class="stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"><h3 style="color: white !important;">👥 نفرات مصاحبه شده</h3><div class="stat-number">{total_interviewed}</div><div class="stat-label">نفر</div></div>', unsafe_allow_html=True)
            with col2: st.markdown(f'<div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);"><h3 style="color: white !important;">🎯 بیشترین مصاحبه</h3><div class="stat-number">{most_interviewed_count}</div><div class="stat-label">{most_interviewed_unit} ({most_interviewed_percentage}%)</div></div>', unsafe_allow_html=True)
            with col3: st.markdown(f'<div class="stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);"><h3 style="color: white !important;">✅ استخدام شدگان</h3><div class="stat-number">{hired_count}</div><div class="stat-label">{hired_percentage}% از {total_interviewed} نفر</div></div>', unsafe_allow_html=True)
            with col4: st.markdown(f'<div class="stat-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);"><h3 style="color: white !important;">🏆 بیشترین استخدام</h3><div class="stat-number">{most_hired_unit}</div><div class="stat-label">مرد: {gender_percentages.get("مرد", 0)}% | زن: {gender_percentages.get("زن", 0)}%</div></div>', unsafe_allow_html=True)
            with col5: st.markdown(f'<div class="stat-card" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);"><h3 style="color: white !important;">❓ نامشخص</h3><div class="stat-number">{undecided_count}</div><div class="stat-label">{undecided_percentage}% از {total_interviewed} نفر</div></div>', unsafe_allow_html=True)
        # ✅✅✅ ایجاد فاصله ۵۰ پیکسلی از بالا
            st.markdown('<div style="margin-top: 50px;"></div>', unsafe_allow_html=True)
            # --- نمایش جدول با ترتیب ستون‌های دلخواه ---
            st.subheader("📊 لیست مصاحبه‌شوندگان")
            
            # تعریف ترتیب ستون‌ها
            desired_columns = [
                
                "ماه"
                "وضعیت نهایی", 
                "علت_دسته_بندی_شده",
                "علت نپذیرفتن", 
                "تاریخ شروع بکار", 
                "معرف", 
                "جنسیت", 
                "واحد", 
                "نام و نام خانوادگی", 

            ]
            
            # فقط ستون‌هایی را انتخاب می‌کنیم که واقعاً در فایل اکسل/شیت موجود باشند (برای جلوگیری از ارور)
            final_cols = [col for col in desired_columns if col in df_emp.columns]
            
            # اگر ستونی پیدا شد، جدول را فیلتر کن، وگرنه کل جدول را نشان بده
            if final_cols:
                df_show = df_emp[final_cols]
            else:
                df_show = df_emp
            
            st.dataframe(df_show, use_container_width=True, height=500, hide_index=True)
        
        else:
            st.warning("هنوز داده‌ای بارگذاری نشده است. لطفاً دکمه بارگذاری را بزنید.")
   # ---------------------------------------------------------
    # بخش 5: گزارش ماهانه (اصلاح شده برای مشکل آبان و حروف)
    # ---------------------------------------------------------
    elif st.session_state.hr_active_tab == "گزارش ماهانه":
        ensure_data_loaded("monthly")
        st.subheader("📊 گزارش کارکرد و وضعیت ماهانه")
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🔄 دریافت اطلاعات جدید", use_container_width=True, key="btn_reload_monthly"):
                fetch_and_clean_data.clear()
                with st.spinner("در حال دریافت اطلاعات..."):
                    load_monthlylist_data()
                st.rerun()

        if st.session_state.last_update_monthlylist:
            shamsi_date = jdatetime.datetime.fromgregorian(datetime=st.session_state.last_update_monthlylist)
            st.info(f"آخرین آپدیت: {shamsi_date.strftime('%Y/%m/%d - %H:%M:%S')}")

        if st.session_state.monthlylist_data is not None:
            df = st.session_state.monthlylist_data.copy()
            
            # 1. تمیزکاری نام ستون‌ها (حذف فاصله و اصلاح حروف)
            df.columns = [str(col).strip().replace('ي', 'ی').replace('ك', 'ک') for col in df.columns]

            # 2. تمیزکاری مقادیر سلول‌ها (حل مشکل آبان/ابان و فاصله‌ها)
            # این تابع تمام مشکلات تایپی رایج را حل می‌کند
            def clean_all_values(val):
                if pd.isna(val): return val
                val = str(val).strip().replace('ي', 'ی').replace('ك', 'ک')
                # حل مشکل آبان و آذر
                if val == "ابان": return "آبان"
                if val == "اذر": return "آذر"
                return val

            # اعمال تمیزکاری روی کل جدول
            for col in df.columns:
                df[col] = df[col].apply(clean_all_values)

            # --- فیلتر هوشمند ماه ---
            persian_months_order = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
            sorted_months = []
            default_index = 0
            
            if 'ماه' in df.columns:
                unique_months = df['ماه'].dropna().unique().tolist()
                valid_months = [m for m in unique_months if m in persian_months_order]
                sorted_months = sorted(valid_months, key=lambda x: persian_months_order.index(x))
                if sorted_months:
                    default_index = len(sorted_months) # انتخاب آخرین ماه

            # --- نمایش فیلترها ---
            st.markdown("### 🔍 فیلترهای گزارش")
            c1, c2, c3, c4, c5 = st.columns(5)
            with c1: f_family = st.text_input("نام خانوادگی", key="sm_fam")
            with c2: f_code = st.text_input("شماره پرسنلی", key="sm_cod")
            with c3: f_month = st.selectbox("انتخاب ماه", ['همه'] + sorted_months, index=default_index, key="sm_mon")
            with c4: 
                units = sorted(df['واحد'].dropna().unique().tolist()) if 'واحد' in df.columns else []
                f_unit = st.selectbox("واحد", ['همه'] + units, key="sm_unt")
            with c5:
                locs = sorted(df['محل خدمت'].dropna().unique().tolist()) if 'محل خدمت' in df.columns else []
                f_loc = st.selectbox("محل خدمت", ['همه'] + locs, key="sm_loc")

            # --- اعمال فیلتر ---
            df_show = df.copy()
            if f_family and 'نام خانوادگی' in df_show.columns: df_show = df_show[df_show['نام خانوادگی'].astype(str).str.contains(f_family, case=False, na=False)]
            if f_code and 'شماره پرسنلی' in df_show.columns: df_show = df_show[df_show['شماره پرسنلی'].astype(str).str.contains(f_code, na=False)]
            
            if f_month != "همه" and 'ماه' in df_show.columns: df_show = df_show[df_show['ماه'] == f_month]
            if f_unit != "همه" and 'واحد' in df_show.columns: df_show = df_show[df_show['واحد'] == f_unit]
            if f_loc != "همه" and 'محل خدمت' in df_show.columns: df_show = df_show[df_show['محل خدمت'] == f_loc]

            st.markdown(f"##### تعداد رکورد: {len(df_show)}")

            # =========================================================
            # ترتیب ستون‌ها
            # =========================================================
            target_columns = [
                "روز کارکرد",
                "علت ترک کار",
                "محل خدمت",
                "وضعیت",
                "ماه",
                "تاریخ استخدام",
                "واحد",
                "نام خانوادگی",
                "نام",
                "شماره پرسنلی"
            ]
            
            final_cols = [col for col in target_columns if col in df_show.columns]
            
            # چک کردن وجود ستون‌ها برای اطمینان
            if "ماه" not in df_show.columns:
                st.error("❌ ستون «ماه» در فایل اکسل پیدا نشد!")

            if final_cols:
                df_show = df_show[final_cols]

            st.dataframe(df_show, use_container_width=True, height=600, hide_index=True)
        else:
            st.info("👈 دکمه دریافت اطلاعات را بزنید.")

            # ==========================================
            # 🔍 بخش فیلترها (۵ ستون در یک ردیف)
            # ==========================================
            st.markdown("### 🔍 فیلترهای گزارش")
            # تغییر به 5 ستون برای جا شدن فیلتر محل خدمت
            c1, c2, c3, c4, c5 = st.columns(5)
            
            # فیلتر ۱: نام خانوادگی
            with c1:
                f_family = st.text_input("نام خانوادگی", key="search_family_monthly")
            
            # فیلتر ۲: شماره پرسنلی
            with c2:
                f_code = st.text_input("شماره پرسنلی", key="search_code_monthly")
            
            # فیلتر ۳: ماه (مرتب شده بر اساس تقویم)
            with c3:
                if 'ماه' in df.columns:
                    # پیدا کردن ماه‌های موجود در فایل
                    available_months = df['ماه'].unique().tolist()
                    # مرتب‌سازی ماه‌های موجود بر اساس لیست استاندارد شمسی
                    sorted_months = sorted(
                        available_months, 
                        key=lambda x: persian_months_order.index(x) if x in persian_months_order else 99
                    )
                    # معکوس می‌کنیم تا ماه آخر (مثلا آبان) اول لیست باشد
                    sorted_months.reverse()
                    
                    f_month = st.selectbox("انتخاب ماه", ['همه'] + sorted_months, key="filter_month_monthly")
                else:
                    f_month = "همه"
                    st.warning("⚠️ ستون 'ماه' یافت نشد.")

            # فیلتر ۴: واحد
            with c4:
                if 'واحد' in df.columns:
                    if f_month != 'همه' and 'ماه' in df.columns:
                        units = sorted(df[df['ماه'] == f_month]['واحد'].unique().tolist())
                    else:
                        units = sorted(df['واحد'].unique().tolist())
                    f_unit = st.selectbox("واحد سازمانی", ['همه'] + units, key="filter_unit_monthly")
                else:
                    f_unit = "همه"

            # فیلتر ۵: محل خدمت (اضافه شد ✅)
            with c5:
                if 'محل خدمت' in df.columns:
                    # فیلتر هوشمند بر اساس انتخاب‌های قبلی
                    temp_df = df.copy()
                    if f_month != 'همه' and 'ماه' in temp_df.columns:
                        temp_df = temp_df[temp_df['ماه'] == f_month]
                    if f_unit != 'همه' and 'واحد' in temp_df.columns:
                        temp_df = temp_df[temp_df['واحد'] == f_unit]
                        
                    locations = sorted(temp_df['محل خدمت'].unique().tolist())
                    f_location = st.selectbox("محل خدمت", ['همه'] + locations, key="filter_location_monthly")
                else:
                    f_location = "همه"
            
            # --- اعمال فیلترها روی جدول ---
            df_show = df.copy()
            
            if f_family and 'نام خانوادگی' in df_show.columns:
                df_show = df_show[df_show['نام خانوادگی'].str.contains(f_family, case=False, na=False)]
            
            if f_code and 'شماره پرسنلی' in df_show.columns:
                df_show = df_show[df_show['شماره پرسنلی'].astype(str).str.contains(f_code, na=False)]
            
            if f_month != "همه" and 'ماه' in df_show.columns:
                df_show = df_show[df_show['ماه'] == f_month]
            
            if f_unit != "همه" and 'واحد' in df_show.columns:
                df_show = df_show[df_show['واحد'] == f_unit]
                
            if f_location != "همه" and 'محل خدمت' in df_show.columns:
                df_show = df_show[df_show['محل خدمت'] == f_location]
            
            # --- چیدمان ستون‌ها (دقیقاً طبق درخواست شما) ---
            requested_order = [
                'روزهای کارکرد',
                 'محل خدمت',
                'تاریخ استخدام',
                'تاریخ ترک کار',
                'وضعیت',
                'واحد',
                'ماه',
                'نام خانوادگی',
                'نام',
                'شماره پرسنلی',
            ]
            
            # ۱. انتخاب ستون‌های موجود از لیست درخواستی
            final_columns = [c for c in requested_order if c in df_show.columns]
            
            # ۲. اضافه کردن ستون‌های باقیمانده (اگر ستونی در اکسل هست که در لیست بالا نیست)
            remaining_cols = [c for c in df_show.columns if c not in final_columns]
            
            # ۳. ترکیب نهایی
            df_final = df_show[final_columns + remaining_cols]

            st.markdown(f"##### تعداد رکورد یافت شده: {len(df_final)}")
            st.dataframe(df_final, use_container_width=True, height=600, hide_index=True)
            
    else:
            st.info("👈 برای مشاهده اطلاعات، دکمه «دریافت اطلاعات جدید» را بزنید.")
    # ---------------------------------------------------------
def show_production_content():
    st.markdown('<h1>🏭 مدیریت تولید</h1>', unsafe_allow_html=True)
    st.info("این بخش برای مدیریت خطوط تولید، کنترل کیفیت، و برنامه‌ریزی تولید است.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("تولید امروز", "450 واحد", "+12%")
    with col2:
        st.metric("راندمان", "87%", "+3%")
    with col3:
        st.metric("ضایعات", "2.3%", "-0.5%")

def show_sales_content():
    st.markdown('<h1>💰 مدیریت فروش</h1>', unsafe_allow_html=True)
    st.info("این بخش برای مدیریت فروش، مشتریان، و پیگیری سفارشات است.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📈 فروش ماه جاری")
        st.metric("مبلغ فروش", "₽2,500,000", "+15%")
    with col2:
        st.subheader("👥 مشتریان")
        st.metric("مشتریان فعال", "78", "+5")

def show_warehouse_content():
    st.markdown('<h1>📦 مدیریت انبار</h1>', unsafe_allow_html=True)
    st.info("این بخش برای مدیریت موجودی، ورود و خروج کالا، و انبارداری است.")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("موجودی کل", "567 قلم", "+23")
    with col2:
        st.metric("ورود امروز", "45 قلم", "+12")
    with col3:
        st.metric("خروج امروز", "32 قلم", "-5")

def show_after_sales_content():
    st.markdown('<h1>🔧 خدمات پس از فروش</h1>', unsafe_allow_html=True)
    st.info("این بخش برای مدیریت خدمات، پیگیری شکایات، و گارانتی است.")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("🎫 تیکت‌های باز")
        st.metric("تعداد", "23", "+3")
    with col2:
        st.subheader("⭐ رضایت مشتری")
        st.metric("امتیاز", "4.5/5", "+0.2")

def show_management_content():
    st.markdown('<h1>📊 داشبورد مدیریتی</h1>', unsafe_allow_html=True)
    st.info("این بخش برای گزارشات مدیریتی، تحلیل‌ها، و تصمیم‌گیری است.")
    tab1, tab2, tab3 = st.tabs(["گزارشات مالی", "تحلیل عملکرد", "پیش‌بینی"])
    with tab1:
        st.subheader("💵 گزارش مالی")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("درآمد", "₽5,000,000", "+20%")
        with col2:
            st.metric("هزینه", "₽3,200,000", "+10%")
        with col3:
            st.metric("سود", "₽1,800,000", "+35%")
    with tab2:
        st.subheader("📈 عملکرد واحدها")
        st.write("نمودارهای تحلیلی در اینجا قرار می‌گیرند")
    with tab3:
        st.subheader("🔮 پیش‌بینی‌ها")
        st.write("مدل‌های پیش‌بینی در اینجا قرار می‌گیرند")

def show_access_denied():
    current_user = st.query_params.get("user", "")
    st.markdown(f"""
    <div style="text-align: center; padding: 100px 20px;">
        <h1 style="color: #e74c3c; font-size: 4rem;">🚫</h1>
        <h2 style="color: #033270;">شما به محتویات این صفحه دسترسی ندارید</h2>
        <p style="color: #666; font-size: 1.1rem; margin-top: 20px;">
            لطفاً با مدیر سیستم تماس بگیرید یا به صفحه اصلی بازگردید.
        </p>
        <a href="?user={current_user}&page=home" style="display: inline-block; margin-top: 30px; padding: 12px 30px; 
           background-color: #033270; color: white; text-decoration: none; border-radius: 8px;
           transition: all 0.3s;">
            🏠 بازگشت به صفحه اصلی
        </a>
    </div>
     """, unsafe_allow_html=True)

def main():
    if not st.session_state.logged_in:
        login_page()
    else:
        if 'username' in st.session_state and 'user' not in st.query_params:
            st.query_params["user"] = st.session_state.username
        
        current_page = st.query_params.get("page", "home")
        
        load_dashboard_css()
        show_custom_navbar(current_page)
        
        if current_page == "home" or current_page == "":
            show_home_content()
        elif current_page == "hr":
            if has_access("hr"):
                show_hr_content()
            else:
                show_access_denied()
        elif current_page == "production":
            if has_access("production"):
                show_production_content()
            else:
                show_access_denied()
        elif current_page == "sales":
            if has_access("sales"):
                show_sales_content()
            else:
                show_access_denied()
        elif current_page == "warehouse":
            if has_access("warehouse"):
                show_warehouse_content()
            else:
                show_access_denied()
        elif current_page == "after_sales":
            if has_access("after_sales"):
                show_after_sales_content()
            else:
                show_access_denied()
        elif current_page == "management":
            if has_access("management"):
                show_management_content()
            else:
                show_access_denied()
        else:
            show_home_content()

if __name__ == "__main__":
    main()