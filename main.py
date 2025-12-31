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

# رنگ جداول گوگل شیت
def style_dataframe(df):
    return df.style.set_properties(**{
        'background-color': '#F0F8FF',     # آبی ملیح برای سلول‌ها
        'color': '#000000',
        'font-family': 'B Nazanin',
        'border-color': '#ffffff',
        'text-align': 'right',
        'font-size': '15px'
    }).set_table_styles([
        {'selector': 'th', 'props': [
            ('background-color', '#2E86C1'), # ✅ آبی روشن (دیگر مشکی نیست)
            ('color', 'white'),
            ('font-family', 'B Nazanin'),
            ('font-size', '16px'),
            ('text-align', 'center'),
            ('font-weight', 'bold')
        ]}
    ])
    
#بالای سایت 
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
    
if 'last_update_hr_global' not in st.session_state:
    st.session_state.last_update_hr_global = None

target_user = st.query_params.get("user")
if target_user and target_user in USERS:
    st.session_state.logged_in = True
    st.session_state.user_info = USERS[target_user]

# این بخش را جایگزین کد قبلی خروج کنید (حدود خط ۶۰)
if st.query_params.get("action") == "logout":
    st.session_state.clear()       # 1. پاک کردن کل حافظه موقت (کش)
    st.session_state.logged_in = False  # 2. تنظیم وضعیت به خارج شده
    st.query_params.clear()        # 3. پاک کردن آدرس بار
    st.rerun()                     # 4. رفرش صفحه
#ادرس گوگل شیت
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
df = fetch_and_clean_data("personnel")
if df is not None:
        st.session_state.personnel_data = df
        st.session_state.last_update_personnel = datetime.now()
        st.session_state.last_update_hr_global = datetime.now()
def load_employee_data():
    df = fetch_and_clean_data("employment")
    if df is not None:
        st.session_state.employee_data = df
        st.session_state.last_update_employee = datetime.now()
        st.session_state.last_update_hr_global = datetime.now()

def load_monthlylist_data():
    df = fetch_and_clean_data("monthlylist")
    if df is not None:
        st.session_state.monthlylist_data = df
        st.session_state.last_update_monthlylist = datetime.now()
        st.session_state.last_update_hr_global = datetime.now() 
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
    # ==========================================
    # 💎 استایل سراسری فونت بی نازنین (برای کل سامانه)
    # ==========================================
    st.markdown("""
        <style>
            /* 1. تعریف فونت (اگر روی سیستم نصب باشد یا از CDN) */
            @font-face {
                font-family: 'B Nazanin';
                src: local('B Nazanin'), local('B_Nazanin');
            }

            /* 2. اعمال فونت روی تمام اجزای HTML بصورت اجباری */
            html, body, [class*="css"] {
                font-family: 'B Nazanin', 'Tahoma', sans-serif !important;
            }

            /* 3. اصلاح دقیق‌تر برای اجزای خاص استریم‌لیت */
            .stTextInput, .stNumberInput, .stSelectbox, .stDateInput, 
            .stTimeInput, .stTextArea, .stButton, .stCheckbox, .stRadio,
            .stExpander, .stTabs, .stDataFrame, .stTable, .stMetric {
                font-family: 'B Nazanin', 'Tahoma', sans-serif !important;
            }

            /* 4. متن‌های داخل دکمه‌ها، لیبل‌ها و ورودی‌ها */
            button, input, textarea, select, label, p, span, div {
                font-family: 'B Nazanin', 'Tahoma', sans-serif !important;
            }

            /* 5. تیترها */
            h1, h2, h3, h4, h5, h6 {
                font-family: 'B Nazanin', 'Tahoma', sans-serif !important;
                font-weight: 900 !important; /* ضخیم کردن تیترها */
            }

            /* 6. اعداد داخل جداول و دیتافریم‌ها */
            .stDataFrame div, .stDataFrame span {
                font-family: 'B Nazanin', 'Tahoma', sans-serif !important;
                font-size: 15px !important;
            }
            
            /* 7. اصلاح فونت تولتیپ‌های نمودارهای Plotly */
            .js-plotly-plot .plotly, .js-plotly-plot .plotly text, 
            .js-plotly-plot .plotly .hovertext text {
                font-family: 'B Nazanin', 'Tahoma', sans-serif !important;
            }
        </style>
    """, unsafe_allow_html=True)
    # ==========================================
    # 🎨 تنظیمات: اسلایدر با ارتفاع کمتر (350 پیکسل)
    # ==========================================
    st.markdown("""
        <style>
            /* تنظیم فاصله کانتینر اصلی (همان تنظیماتی که برای هماهنگی با دکمه‌ها داشتید) */
            [data-testid="block-container"] {
                padding-left: 60px !important;   /* این عدد را طبق آخرین تغییرتان نگه دارید */
                padding-right: 60px !important;  
                padding-top: 90px !important;
                max-width: 100% !important;
            }

            iframe {
                width: 100% !important;
                border: none !important;
                display: block !important;
            }
            
            div[data-testid="stVerticalBlock"] {
                gap: 0 !important;
            }
        </style>
    """, unsafe_allow_html=True)
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
 # ---------------------------------------------------------
    # بخش کارت‌های صفحه اصلی (Home) - اصلاح شده
    # ---------------------------------------------------------
    
    st.subheader("📊 خلاصه وضعیت سیستم")
    
    # ✅ 1. ایجاد فاصله بین تیتر و کارت‌ها
    st.markdown("<div style='margin-bottom: 30px;'></div>", unsafe_allow_html=True)
    
    # ✅ 2. استایل CSS مخصوص کارت‌های واتر‌مارک‌دار (مشابه جذب)
    st.markdown("""
        <style>
            .home-stat-card {
                border-radius: 16px;
                padding: 15px;
                height: 160px;
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                position: relative;
                overflow: hidden; /* برای اینکه استیکر بیرون نزند */
                box-shadow: 0 4px 15px rgba(0,0,0,0.1);
                transition: transform 0.3s ease;
                border: 1px solid rgba(255,255,255,0.3);
            }
            .home-stat-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 8px 25px rgba(0,0,0,0.15);
            }
            
            /* استایل استیکر پس‌زمینه (واترمارک) */
            .card-watermark {
                position: absolute;
                top: -15px;
                left: -15px;
                font-size: 80px;
                opacity: 0.15; /* شفافیت کم */
                pointer-events: none;
                transform: rotate(15deg);
                z-index: 0;
            }
            
            /* محتوای روی کارت */
            .card-content-home {
                position: relative;
                z-index: 1;
                text-align: center;
                width: 100%;
            }
            
            .home-card-title {
                font-size: 18px !important;
                font-weight: 900 !important;
                margin-bottom: 10px !important;
                color: #000 !important;
            }
            .home-card-value {
                font-size: 32px !important;
                font-weight: 900 !important;
                margin: 5px 0 !important;
                color: #000 !important;
                text-shadow: none !important;
            }
            .home-card-sub {
                font-size: 14px !important;
                font-weight: bold !important;
                opacity: 0.8;
                color: #333 !important;
            }
        </style>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)
    
    # کارت ۱: منابع انسانی
    with col1:
        st.markdown(f'''
        <div class="home-stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
            <div class="card-watermark">👥</div> <div class="card-content-home">
                <div class="home-card-title">منابع انسانی</div>
                <div class="home-card-value">150</div>
                <div class="home-card-sub">تعداد کارکنان</div>
            </div>
        </div>
        ''', unsafe_allow_html=True)

    # کارت ۲: تولید
    with col2:
        st.markdown(f'''
        <div class="home-stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
            <div class="card-watermark">🏭</div> <div class="card-content-home">
                <div class="home-card-title">تولید</div>
                <div class="home-card-value">1,234</div>
                <div class="home-card-sub">واحد تولید شده</div>
            </div>
        </div>
        ''', unsafe_allow_html=True)

    # کارت ۳: فروش
    with col3:
        st.markdown(f'''
        <div class="home-stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
            <div class="card-watermark">💰</div> <div class="card-content-home">
                <div class="home-card-title">فروش</div>
                <div class="home-card-value">2.5M</div>
                <div class="home-card-sub">فروش ماهانه</div>
            </div>
        </div>
        ''', unsafe_allow_html=True)

    # کارت ۴: انبار
    with col4:
        st.markdown(f'''
        <div class="home-stat-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
            <div class="card-watermark">📦</div> <div class="card-content-home">
                <div class="home-card-title">انبار</div>
                <div class="home-card-value">567</div>
                <div class="home-card-sub">اقلام موجود</div>
            </div>
        </div>
        ''', unsafe_allow_html=True)
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
            with st.spinner("⏳ در حال دریافت بانک اطلاعات سرمایه ..."):
                load_personnel_data()
                
    elif data_type == "employee":
        if st.session_state.employee_data is None or should_update_data(st.session_state.last_update_employee):
            with st.spinner("⏳ در حال دریافت اطلاعات جذب و استخدام..."):
                load_employee_data()
                
    elif data_type == "monthly":
        if st.session_state.monthlylist_data is None or should_update_data(st.session_state.last_update_monthlylist):
            with st.spinner("⏳ در حال دریافت گزارش کارکرد ماهیانه..."):
                load_monthlylist_data()
def show_hr_content():
   # محاسبه تاریخ و زمان فعلی
    now = datetime.now()
    shamsi_now = jdatetime.datetime.fromgregorian(datetime=now)
    today_date = shamsi_now.strftime('%Y/%m/%d')
    now_time = shamsi_now.strftime('%H:%M')
    
    # ==========================================
    # 🎨 استایل CSS مدرن برای هدر و دکمه آپدیت
    # ==========================================
    st.markdown("""
        <style>
        div[data-testid="stVerticalBlock"] {
            gap: 0.5rem !important;
        }
        
        .block-container {
            padding-top: 3rem !important;
            padding-bottom: 2rem !important;
        }
        
        /* استایل باکس تیتر مدرن - ارتفاع کاهش یافته */
        .header-box {
            position: relative;
            background: linear-gradient(120deg, #ffffff 0%, #f0f7ff 100%);
            width: 100%;
            padding: 18px 30px;
            border-radius: 16px;
            border: 1px solid #eef2f6;
            border-right: 6px solid #033270;
            box-shadow: 0 10px 30px -10px rgba(3, 50, 112, 0.1);
            margin-bottom: 25px;
            direction: rtl;
            text-align: right;
            display: flex;
            justify-content: space-between;
            align-items: center;
            overflow: hidden;
            transition: transform 0.3s ease;
            min-height: 70px;
        }
        
        .header-box:hover {
            transform: translateY(-2px);
            box-shadow: 0 15px 35px -10px rgba(3, 50, 112, 0.15);
        }

        .header-watermark {
            position: absolute;
            left: -10px;
            bottom: -15px;
            font-size: 90px;
            opacity: 0.04;
            color: #033270;
            transform: rotate(15deg);
            pointer-events: none;
            z-index: 0;
        }

        .header-content {
            position: relative;
            z-index: 1;
            flex: 1;
        }
        
        .header-title {
            color: #033270;
            margin: 0;
            font-size: 28px;
            font-weight: 900;
            font-family: 'B Nazanin', 'Tahoma', sans-serif;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        /* 🔥 استایل دکمه آپدیت جدید - داخل باکس */
        .update-button-box {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 10px 18px;
            border-radius: 12px;
            text-align: center;
            border: 2px solid rgba(255,255,255,0.3);
            z-index: 1;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
            min-width: 180px;
        }
        
        .update-button-box:hover {
            transform: translateY(-3px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
        }
        
        .update-icon {
            color: white;
            font-weight: 900;
            font-size: 16px;
            margin: 0;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        
        .update-time {
            color: rgba(255,255,255,0.95);
            font-size: 11px;
            margin: 3px 0 0 0;
            font-weight: 600;
        }

        .compact-separator {
            margin-top: -20px !important;
            margin-bottom: -20px !important;
            border-bottom: 1px solid #E2E8F0;
            width: 100%;
            display: block;
        }
        
        /* استایل دکمه‌های تب */
        div.stButton > button[kind="primary"] {
            background: linear-gradient(135deg, #034870 0%, #164e96 100%) !important;
            border: none !important;
            border-radius: 12px !important;
            padding: 10px 20px !important;
            box-shadow: 0 4px 10px rgba(3, 50, 112, 0.3) !important;
            transition: all 0.3s ease !important;
        }
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
            background-color: #f8fafc !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 12px !important;
            padding: 10px 20px !important;
            box-shadow: 0 2px 5px rgba(0,0,0,0.02) !important;
            transition: all 0.3s ease !important;
        }
        div.stButton > button[kind="secondary"] p {
            color: #475569 !important;
            font-weight: 700 !important;
        }
        div.stButton > button[kind="secondary"] * { color: #475569 !important; }

        div.stButton > button[kind="secondary"]:hover {
            background-color: #e2e8f0 !important;
            border-color: #cbd5e1 !important;
            color: #033270 !important;
            transform: translateY(-2px) !important;
        }
        div.stButton > button[kind="secondary"]:hover p {
             color: #033270 !important;
        }

        </style>
        """, unsafe_allow_html=True)
    
    # محاسبه تاریخ آخرین آپدیت
    if st.session_state.last_update_hr_global:
        shamsi_update = jdatetime.datetime.fromgregorian(datetime=st.session_state.last_update_hr_global)
        last_update_text = shamsi_update.strftime('%Y/%m/%d - %H:%M')
    else:
        last_update_text = "هنوز بروزرسانی نشده"
    
# ---------------------------------------------------------
    # 👇👇👇 اصلاح نهایی: جابجایی آیکون به سمت راست دکمه 👇👇👇
    # ---------------------------------------------------------
    
    st.markdown("""
        <style>
        @keyframes shine {
            0% { left: -100%; opacity: 0; }
            5% { left: -100%; opacity: 0.3; }
            20% { left: 100%; opacity: 0.3; }
            100% { left: 100%; opacity: 0; }
        }

        @keyframes floatIcon {
            0% { transform: rotate(15deg) translateY(0px); }
            50% { transform: rotate(10deg) translateY(-10px); }
            100% { transform: rotate(15deg) translateY(0px); }
        }

        .header-box {
            position: relative;
            /* رنگ آبی ملیح */
            background: linear-gradient(135deg, #e6f2ff 0%, #cfe5ff 100%);
            border-right: 6px solid #033270;
            border-radius: 16px;
            box-shadow: 0 8px 20px rgba(3, 50, 112, 0.15);
            overflow: hidden;
            border: 1px solid #bbdefb;
            transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        }

        .header-box:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 30px rgba(3, 50, 112, 0.3);
            border-color: #64b5f6;
        }

        .header-box::after {
            content: '';
            position: absolute;
            top: 0;
            left: -100%;
            width: 50%;
            height: 100%;
            background: linear-gradient(to right, 
                rgba(255,255,255,0) 0%, 
                rgba(255,255,255,0.6) 50%, 
                rgba(255,255,255,0) 100%);
            transform: skewX(-25deg);
            animation: shine 6s infinite;
            pointer-events: none;
        }

        .header-watermark {
            position: absolute;
            /* ✅✅✅ تغییر مکان آیکون: */
            left: 250px;  /* قبلا 20px بود، الان 180px شد تا از زیر دکمه بیاید بیرون */
            bottom: -20px;
            font-size: 100px;
            opacity: 0.08;
            color: #033270;
            z-index: 0;
            animation: floatIcon 6s ease-in-out infinite;
        }
        </style>
    """, unsafe_allow_html=True)

    # 1. رسم باکس پس‌زمینه (لایه زیرین)
    # ارتفاع 90 پیکسل برای فضای کافی جهت وسط‌چین کردن
    st.markdown(f"""
    <div class="header-box" style="margin-bottom: -85px; height: 90px; z-index: 0;">
        <div class="header-watermark"><i class="fas fa-users"></i></div>
    </div>
    """, unsafe_allow_html=True)
    
    # 2. ایجاد ستون‌ها روی باکس (لایه رویی)
    # ساختار ستون‌ها در حالت فارسی (RTL):
    # [متن (راست)] --- [دکمه (چپ)] --- [فاصله خالی (لبه چپ)]
    # نسبت‌ها: 6 واحد متن | 1.3 واحد دکمه | 0.3 واحد فاصله خالی (برای هل دادن دکمه به داخل)
    c_text, c_btn, c_spacer = st.columns([6, 1.3, 0.3])
    
    with c_text:
        # متن تیتر (سمت راست)
        # padding-top: 25px باعث می‌شود متن دقیقاً وسط باکس 90 پیکسلی قرار گیرد
        st.markdown("""
        <div style="padding-right: 20px; padding-top: 10px;">
            <div class="header-title">👥 مدیریت منابع انسانی</div>
        </div>
        """, unsafe_allow_html=True)
        
    with c_btn:
        # دکمه (سمت چپ)
        # فاصله از بالا برای تراز عمودی با باکس
        st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True) 
        
        if st.button("🔄 بروزرسانی", use_container_width=True, key="header_update_btn"):
            fetch_and_clean_data.clear()
            st.session_state.last_update_personnel = None
            st.session_state.last_update_employee = None
            st.session_state.last_update_monthlylist = None
            st.session_state.last_update_hr_global = datetime.now()
            st.rerun()
            
        # نمایش تاریخ زیر دکمه (بزرگتر و خواناتر)
        st.markdown(f"""
        <div style='text-align:center; font-size:13px; font-weight:bold; color:#555; margin-top: -9px; text-shadow: 0 1px 0 rgba(255,255,255,0.8);'>
            {last_update_text} 📅
        </div>
        """, unsafe_allow_html=True)

    # ستون سوم (c_spacer) خالی می‌ماند تا دکمه به سمت راست (داخل باکس) متمایل شود

    # یک فاصله خالی پایین باکس برای جلوگیری از تداخل
    st.markdown("<div style='margin-bottom: 50px;'></div>", unsafe_allow_html=True)



    # 3. مدیریت وضعیت تب فعال
    if 'hr_active_tab' not in st.session_state:
        st.session_state.hr_active_tab = "رویدادها"
    
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
        type_ = "primary" if st.session_state.hr_active_tab == "بانک اطلاعات سرمایه انسانی" else "secondary"
        if st.button(" بانک اطلاعات سرمایه انسانی🗂️", use_container_width=True, type=type_):
            st.session_state.hr_active_tab = "بانک اطلاعات سرمایه انسانی"
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
    # ---------------------------------------------------------
    # بخش ۵: داشبورد تحلیل (شامل تمام نمودارها و تحلیل‌ها)
    # ---------------------------------------------------------
    if st.session_state.hr_active_tab == "داشبورد تحلیلی":
        # ✅✅✅ این خط جدید را حتماً اضافه کنید:
        ensure_data_loaded("monthly") 
        
        # خطوط قبلی که بودند:
        ensure_data_loaded("employee")
        ensure_data_loaded("personnel")
        
        # تب‌های فرعی...
        sub_tab1, sub_tab2 = st.tabs(["👥 تحلیل پرسنل", "📝 تحلیل جذب و استخدام"])
        
        with sub_tab1:
            st.markdown("#### 📊 داشبورد جامع تحلیل سرمایه انسانی")
            
            # اطمینان از لود بودن داده‌ها
            if st.session_state.monthlylist_data is not None and st.session_state.personnel_data is not None:
                
                # 1. آماده‌سازی داده‌ها
                df_main = st.session_state.monthlylist_data.copy()
                df_gender_source = st.session_state.personnel_data.copy()
                
                # تمیزکاری اولیه نام ستون‌ها
                df_main.columns = [str(col).strip().replace('ي', 'ی').replace('ك', 'ک') for col in df_main.columns]
                df_gender_source.columns = [str(col).strip().replace('ي', 'ی').replace('ك', 'ک') for col in df_gender_source.columns]

                # ✅✅✅ بخش جدید: استانداردسازی نام ماه‌ها (حل مشکل ابان/آبان)
                if 'ماه' in df_main.columns:
                    def normalize_month(m):
                        if pd.isna(m): return m
                        m = str(m).strip().replace('ي', 'ی').replace('ك', 'ک')
                        if m == "ابان": return "آبان"
                        if m == "اذر": return "آذر"
                        return m
                    df_main['ماه'] = df_main['ماه'].apply(normalize_month)

                # ادغام برای افزودن جنسیت به گزارش ماهانه
                if 'شماره پرسنلی' in df_main.columns and 'شماره پرسنلی' in df_gender_source.columns and 'جنسیت' in df_gender_source.columns:
                    df_main['شماره پرسنلی'] = df_main['شماره پرسنلی'].astype(str).str.strip()
                    df_gender_source['شماره پرسنلی'] = df_gender_source['شماره پرسنلی'].astype(str).str.strip()
                    
                    # حذف تکراری‌ها در فایل پرسنلی
                    gender_map = df_gender_source.drop_duplicates('شماره پرسنلی')[['شماره پرسنلی', 'جنسیت']]
                    
                    # ادغام
                    df_merged = pd.merge(df_main, gender_map, on='شماره پرسنلی', how='left')
                    df_merged['جنسیت'] = df_merged['جنسیت'].fillna('نامشخص')
                else:
                    df_merged = df_main.copy()
                    df_merged['جنسیت'] = 'نامشخص'

                # 2. چیدمان فیلترها
                persian_months_order = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]
                
                # پیدا کردن ماه‌های موجود
                available_months = df_merged['ماه'].unique().tolist() if 'ماه' in df_merged.columns else []
                # مرتب‌سازی ماه‌ها
                sorted_months = sorted([m for m in available_months if m in persian_months_order], key=lambda x: persian_months_order.index(x))
                
                # کانتینر فیلترها
                st.markdown('<div style="background-color: white; padding: 15px; border-radius: 10px; border: 1px solid #eee; box-shadow: 0 2px 5px rgba(0,0,0,0.05); margin-bottom: 20px;">', unsafe_allow_html=True)
                f_col1, f_col2, f_col3 = st.columns([1.5, 1, 1])
                
                with f_col1:
                    selected_gender = st.radio(
                        "تفکیک جنسیتی:",
                        ["👥 همه", "👨 آقایان", "👩 خانم‌ها"],
                        horizontal=True,
                        key="dash_gender_filter_new"
                    )
                
                with f_col2:
                    # انتخاب پیش‌فرض: آخرین ماه لیست (که الان باید آبان یا آذر باشد)
                    default_idx = len(sorted_months) - 1 if sorted_months else 0
                    selected_month = st.selectbox("📅 انتخاب ماه:", sorted_months, index=default_idx, key="dash_month_filter_new")
                
                with f_col3:
                    units_list = ['همه'] + sorted(df_merged['واحد'].dropna().unique().tolist()) if 'واحد' in df_merged.columns else ['همه']
                    selected_unit = st.selectbox("🏭 انتخاب واحد:", units_list, key="dash_unit_filter_new")
                
                st.markdown('</div>', unsafe_allow_html=True)

                # 3. فیلتر کردن داده‌ها
                df_month_filtered = df_merged[df_merged['ماه'] == selected_month].copy()
                
                if selected_unit != "همه":
                    df_month_filtered = df_month_filtered[df_month_filtered['واحد'] == selected_unit]
                
                if selected_gender == "👨 آقایان":
                    df_month_filtered = df_month_filtered[df_month_filtered['جنسیت'] == "مرد"]
                elif selected_gender == "👩 خانم‌ها":
                    df_month_filtered = df_month_filtered[df_month_filtered['جنسیت'] == "زن"]

                # 4. محاسبات کارت‌ها
                
                # A: تعداد کل پرسنل فعال (کسانی که وضعیتشان ترک کار نیست)
                if 'وضعیت' in df_month_filtered.columns:
                    active_df = df_month_filtered[~df_month_filtered['وضعیت'].astype(str).str.contains('ترک کار|قطع همکاری', case=False, na=False)]
                    total_active_count = len(active_df)
                else:
                    total_active_count = len(df_month_filtered)

                # تابع کمکی تاریخ
                month_map = {name: str(i+1).zfill(2) for i, name in enumerate(persian_months_order)}
                target_month_num = month_map.get(selected_month, "00")

                def check_date_in_month(date_val, m_num):
                    try:
                        s = str(date_val).strip()
                        if pd.isna(s) or s == 'nan' or s == 'None': return False
                        parts = s.split('/')
                        if len(parts) >= 2:
                            return parts[1] == m_num
                        return False
                    except: return False

                # B: جذب جدید
                new_hires_count = 0
                if 'تاریخ استخدام' in df_month_filtered.columns:
                    new_hires_df = df_month_filtered[df_month_filtered['تاریخ استخدام'].apply(lambda x: check_date_in_month(x, target_month_num))]
                    new_hires_count = len(new_hires_df)

                # C: نرخ ریزش
                churn_count = 0
                if 'تاریخ ترک کار' in df_month_filtered.columns:
                    churn_df = df_month_filtered[df_month_filtered['تاریخ ترک کار'].apply(lambda x: check_date_in_month(x, target_month_num))]
                    churn_count = len(churn_df)
                elif 'علت ترک کار' in df_month_filtered.columns:
                     churn_count = len(df_month_filtered[df_month_filtered['علت ترک کار'].notna() & (df_month_filtered['علت ترک کار'] != "نامشخص")])

                churn_rate = round((churn_count / len(df_month_filtered) * 100), 1) if len(df_month_filtered) > 0 else 0

                # 5. نمایش کارت‌ها
                st.markdown("""
                <style>
                    .gradient-card {
                        border-radius: 16px;
                        padding: 15px !important;
                        height: 160px !important;
                        display: flex; flex-direction: column; justify-content: space-between;
                        position: relative; overflow: hidden;
                        border: 1px solid rgba(255,255,255,0.5);
                        font-family: 'B Nazanin', Tahoma, sans-serif !important;
                        transition: transform 0.3s;
                    }
                    .gradient-card:hover { transform: translateY(-5px); box-shadow: 0 10px 20px rgba(0,0,0,0.1); }
                    .watermark-icon {
                        position: absolute; top: -15px; left: -15px;
                        font-size: 80px; opacity: 0.1; pointer-events: none; transform: rotate(15deg);
                    }
                    .card-content { position: relative; z-index: 2; }
                    .g-title { font-size: 16px !important; font-weight: 800; color: rgba(0,0,0,0.6); margin: 0; }
                    .g-value { font-size: 42px !important; font-weight: 900; color: #333; margin: 5px 0; text-shadow: 1px 1px 0px rgba(255,255,255,0.5); }
                    .g-sub { font-size: 14px !important; color: rgba(0,0,0,0.7); font-weight: 700; }
                </style>
                """, unsafe_allow_html=True)

                c1, c2, c3 = st.columns(3)
                
                with c1:
                    st.markdown(f"""
                    <div class="gradient-card" style="background: linear-gradient(135deg, #e3f2fd 0%, #90caf9 100%);">
                        <div class="watermark-icon">👥</div>
                        <div class="card-content">
                            <div class="g-title">پرسنل فعال</div>
                            <div class="g-value">{total_active_count}</div>
                            <div class="g-sub">تعداد نفرات در {selected_month}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with c2:
                    bg_color = "linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%)" if churn_rate > 5 else "linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%)"
                    st.markdown(f"""
                    <div class="gradient-card" style="background: {bg_color};">
                        <div class="watermark-icon">📉</div>
                        <div class="card-content">
                            <div class="g-title">نرخ ریزش ماهانه</div>
                            <div class="g-value">{churn_rate}%</div>
                            <div class="g-sub">{churn_count} نفر خروج در {selected_month}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

                with c3:
                    st.markdown(f"""
                    <div class="gradient-card" style="background: linear-gradient(135deg, #e8f5e9 0%, #a5d6a7 100%);">
                        <div class="watermark-icon">🚀</div>
                        <div class="card-content">
                            <div class="g-title">جذب جدید</div>
                            <div class="g-value">{new_hires_count}</div>
                            <div class="g-sub">استخدام شده در {selected_month}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.markdown("<hr style='margin: 30px 0; opacity: 0.2;'>", unsafe_allow_html=True)
                
            else:
                st.warning("⚠️ داده‌های گزارش ماهانه یا پرسنلی بارگذاری نشده‌اند.")
        with sub_tab2:

                        st.markdown("### 📊 سامانه هوشمند تحلیل جذب")
                        
                        if st.session_state.employee_data is not None:
                            df_emp = st.session_state.employee_data.copy()
                            
                            # فیلتر جنسیت
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
                                    if selected_gender == "👨 آقایان":
                                        df_emp = df_emp[df_emp['جنسیت'] == 'مرد']
                                    elif selected_gender == "👩 خانم‌ها":
                                        df_emp = df_emp[df_emp['جنسیت'] == 'زن']

                            # =========================================================
                            # 1. محاسبات (بدون تغییر)
                            # =========================================================
                            total_candidates = len(df_emp)
                            if 'وضعیت نهایی' in df_emp.columns:
                                total_hired = len(df_emp[df_emp['وضعیت نهایی'] == 'استخدام شد'])
                                total_rejected = len(df_emp[df_emp['وضعیت نهایی'] == 'رد شد'])
                                total_withdrawal = len(df_emp[df_emp['وضعیت نهایی'] == 'انصراف داد'])
                                known_statuses = ['استخدام شد', 'رد شد', 'انصراف داد']
                                total_unknown = len(df_emp[~df_emp['وضعیت نهایی'].isin(known_statuses)])
                            else:
                                total_hired = 0; total_rejected = 0; total_withdrawal = 0; total_unknown = 0
                            
                            conversion_rate = (total_hired / total_candidates * 100) if total_candidates > 0 else 0
                            rejection_rate = (total_rejected / total_candidates * 100) if total_candidates > 0 else 0
                            withdrawal_rate = (total_withdrawal / total_candidates * 100) if total_candidates > 0 else 0
                            selection_ratio = f"1:{int(total_candidates/total_hired)}" if total_hired > 0 else "0"
                            
                            health_score = 100
                            if withdrawal_rate > 20: health_score -= 30
                            if conversion_rate < 5: health_score -= 20
                            if conversion_rate > 50: health_score -= 10

                            if 'واحد' in df_emp.columns and not df_emp.empty:
                                top_interview_unit = df_emp['واحد'].value_counts().idxmax()
                                top_interview_count = df_emp['واحد'].value_counts().max()
                            else:
                                top_interview_unit = "---"; top_interview_count = 0

                            hired_df_only = df_emp[df_emp['وضعیت نهایی'] == 'استخدام شد']
                            if 'واحد' in hired_df_only.columns and not hired_df_only.empty:
                                top_hired_unit = hired_df_only['واحد'].value_counts().idxmax()
                                top_hired_count = hired_df_only['واحد'].value_counts().max()
                                
                                unit_specific = hired_df_only[hired_df_only['واحد'] == top_hired_unit]
                                if 'جنسیت' in unit_specific.columns:
                                    m_c = len(unit_specific[unit_specific['جنسیت'] == 'مرد'])
                                    f_c = len(unit_specific[unit_specific['جنسیت'] == 'زن'])
                                    tot = len(unit_specific)
                                    m_p = int((m_c/tot)*100) if tot>0 else 0
                                    f_p = int((f_c/tot)*100) if tot>0 else 0
                                    # 👇 این خط قدیمی را پاک کنید 👇
                                    # 👇👇👇 کد کاملاً اصلاح شده (دقیقاً مشابه کارت‌های دیگر) 👇👇👇
                                    gender_html_top_unit = f"""<div style="background: rgba(255, 255, 255, 0.6); border-radius: 8px; padding: 6px 10px; display: flex; justify-content: space-between; align-items: center; margin-top: auto; font-size: 14px; color: #444; font-weight: 600; font-family: 'B Nazanin', Tahoma, sans-serif !important;"><div style="display:flex; align-items:center;">👨 {m_c} <span style="font-size:11px; opacity:0.7; margin-right:2px;">({m_p}%)</span></div><div style="width:1px; height:12px; background:#ccc; margin:0 5px;"></div><div style="display:flex; align-items:center;">👩 {f_c} <span style="font-size:11px; opacity:0.7; margin-right:2px;">({f_p}%)</span></div></div>"""
                                else: gender_html_top_unit = ""
                            else:
                                top_hired_unit = "---"; top_hired_count = 0; gender_html_top_unit = ""

                            if total_hired > 0:
                                effort_text = f"1 : {round(total_candidates / total_hired, 1)}"
                            else:
                                effort_text = "---"

                            # توابع کمکی HTML برای کارت‌ها
                            def get_gender_glass_html(df_subset, color_code):
                                if df_subset.empty or 'جنسیت' not in df_subset.columns:
                                    return '<div style="height: 25px;"></div>'
                                total = len(df_subset)
                                m_count = len(df_subset[df_subset['جنسیت'] == 'مرد'])
                                f_count = len(df_subset[df_subset['جنسیت'] == 'زن'])
                                m_pct = int((m_count / total) * 100) if total > 0 else 0
                                f_pct = int((f_count / total) * 100) if total > 0 else 0
                                return f"""
                                <div style="background: rgba(255, 255, 255, 0.6); border-radius: 8px; padding: 6px 10px; display: flex; justify-content: space-between; align-items: center; margin-top: auto; font-size: 14px; color: #444; font-weight: 600; backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.4);">
                                    <div style="display:flex; align-items:center;">👨 {m_count} <span style="font-size:11px; opacity:0.7; margin-right:2px;">({m_pct}%)</span></div>
                                    <div style="width:1px; height:12px; background:#ccc; margin:0 5px;"></div>
                                    <div style="display:flex; align-items:center;">👩 {f_count} <span style="font-size:11px; opacity:0.7; margin-right:2px;">({f_pct}%)</span></div>
                                </div>
                                """

                            gender_html_total = get_gender_glass_html(df_emp, "#3498db")
                            unknown_df = df_emp[~df_emp['وضعیت نهایی'].isin(known_statuses)]
                            gender_html_unknown = get_gender_glass_html(unknown_df, "#7f8c8d")
                            
                            if 'واحد' in df_emp.columns and not df_emp.empty:
                                interview_unit_df = df_emp[df_emp['واحد'] == top_interview_unit]
                                gender_html_interview = get_gender_glass_html(interview_unit_df, "#9b59b6")
                            else: gender_html_interview = ""

                            rejected_df = df_emp[df_emp['وضعیت نهایی'] == 'رد شد']
                            gender_html_rejected = get_gender_glass_html(rejected_df, "#c0392b")
                            
                            withdrawal_df = df_emp[df_emp['وضعیت نهایی'] == 'انصراف داد']
                            gender_html_withdrawal = get_gender_glass_html(withdrawal_df, "#e67e22")

                            hired_df_only = df_emp[df_emp['وضعیت نهایی'] == 'استخدام شد']
                            gender_html_hired = get_gender_glass_html(hired_df_only, "#2ecc71")

                            # =========================================================
                            # 2. نمایش کارت‌های رنگی (۸ کارت کامل)
                            # =========================================================
                            st.markdown("""
                            <style>
                                .gradient-card {
                                    border-radius: 16px;
                                    padding: 10px 14px !important; 
                                    height: 170px !important;      
                                    display: flex;
                                    flex-direction: column;
                                    justify-content: space-between;
                                    position: relative;
                                    overflow: hidden;
                                    border: 1px solid rgba(255,255,255,0.5);
                                    font-family: 'B Nazanin', Tahoma, sans-serif !important;
                                }
                                .gradient-card:hover {
                                    transform: translateY(-5px);
                                    box-shadow: 0 10px 20px rgba(0,0,0,0.1);
                                }
                                .watermark-icon {
                                    position: absolute;
                                    top: -15px;
                                    left: -15px;
                                    font-size: 80px;
                                    opacity: 0.08;
                                    pointer-events: none;
                                    transform: rotate(15deg);
                                }
                                .card-content {
                                    position: relative;
                                    z-index: 2;
                                    display: flex;
                                    flex-direction: column;
                                    height: 100%;
                                    font-family: 'B Nazanin', Tahoma, sans-serif !important;
                                }
                                .g-title {
                                    font-size: 15px !important;
                                    font-weight: 800;
                                    color: rgba(0,0,0,0.6);
                                    margin: 0 !important;
                                    font-family: 'B Nazanin', Tahoma, sans-serif !important;
                                }
                                .g-value {
                                    font-size: 36px !important;
                                    font-weight: 900;
                                    color: #333;
                                    margin: 0 !important;
                                    line-height: 1.2 !important;
                                    text-shadow: 1px 1px 0px rgba(255,255,255,0.5);
                                    font-family: 'B Nazanin', Tahoma, sans-serif !important;
                                }
                                .g-sub {
                                    font-size: 13px !important;
                                    color: rgba(0,0,0,0.6);
                                    font-weight: 700;
                                    margin-bottom: auto !important;
                                    font-family: 'B Nazanin', Tahoma, sans-serif !important;
                                }
                            </style>
                            """, unsafe_allow_html=True)

                            r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
                            with r1_c1: 
                                st.markdown(f"""<div class="gradient-card" style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);"><div class="watermark-icon">📂</div><div class="card-content"><div class="g-title">کل متقاضیان</div><div class="g-value">{total_candidates}</div><div class="g-sub">رزومه‌های دریافتی</div>{gender_html_total}</div></div>""", unsafe_allow_html=True)
                            with r1_c2:
                                st.markdown(f"""<div class="gradient-card" style="background: linear-gradient(135deg, #f5f5f5 0%, #e0e0e0 100%);"><div class="watermark-icon">❓</div><div class="card-content"><div class="g-title">وضعیت نامشخص</div><div class="g-value">{total_unknown}</div><div class="g-sub">در انتظار بررسی</div>{gender_html_unknown}</div></div>""", unsafe_allow_html=True)
                            with r1_c3:
                                st.markdown(f"""<div class="gradient-card" style="background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%);"><div class="watermark-icon">📥</div><div class="card-content"><div class="g-title">واحد با بیشترین حجم مصاحبه</div><div class="g-value">{top_interview_count}</div><div class="g-sub">{top_interview_unit}</div>{gender_html_interview}</div></div>""", unsafe_allow_html=True)
                            with r1_c4:
                                st.markdown(f"""<div class="gradient-card" style="background: linear-gradient(135deg, #ffebee 0%, #ffcdd2 100%);"><div class="watermark-icon">🛡️</div><div class="card-content"><div class="g-title">غربالگری اولیه</div><div class="g-value">{total_rejected}</div><div class="g-sub">در مرحله غربالگری</div>{gender_html_rejected}</div></div>""", unsafe_allow_html=True)
                            
                            st.markdown("<div style='margin-bottom: 15px;'></div>", unsafe_allow_html=True)
                            
                            r2_c1, r2_c2, r2_c3, r2_c4 = st.columns(4)
                            with r2_c1:
                                st.markdown(f"""<div class="gradient-card" style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%);"><div class="watermark-icon">🏃</div><div class="card-content"><div class="g-title">انصراف داوطلب</div><div class="g-value">{total_withdrawal}</div><div class="g-sub">خروج از فرآیند</div>{gender_html_withdrawal}</div></div>""", unsafe_allow_html=True)
                            with r2_c2:
                                st.markdown(f"""<div class="gradient-card" style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);"><div class="watermark-icon">🤝</div><div class="card-content"><div class="g-title">جذب موفق</div><div class="g-value">{total_hired}</div><div class="g-sub">جذب موفق</div>{gender_html_hired}</div></div>""", unsafe_allow_html=True)
                            with r2_c3:
                                st.markdown(f"""<div class="gradient-card" style="background: linear-gradient(135deg, #e0f2f1 0%, #b2dfdb 100%);"><div class="watermark-icon">🏆</div><div class="card-content"><div class="g-title">بیشترین تعداد استخدام موفق</div><div class="g-value">{top_hired_count}</div><div class="g-sub">{top_hired_unit}</div>{gender_html_top_unit}</div></div>""", unsafe_allow_html=True)
                            with r2_c4:

                                # 1. تابع محلی تبدیل اعداد به فارسی
                                def to_persian_num(num_str):
                                    eng = "0123456789"
                                    per = "۰۱۲۳۴۵۶۷۸۹"
                                    tr = str.maketrans(eng, per)
                                    return str(num_str).translate(tr)

                                # 2. محاسبه مجدد متغیرها (برای جلوگیری از خطای NameError)
                                # استفاده از متغیرهای محلی برای اطمینان از وجود داده
                                candidates_local = len(df_emp)
                                hired_df_local = df_emp[df_emp['وضعیت نهایی'] == 'استخدام شد']
                                hired_count_local = len(hired_df_local)

                                # 3. محاسبه عدد اصلی کارت (شاخص کل) به فارسی
                                if hired_count_local > 0:
                                    raw_main = round(candidates_local / hired_count_local, 1)
                                    effort_text_persian = f"۱ : {to_persian_num(raw_main)}"
                                else:
                                    effort_text_persian = "---"

                                # 4. محاسبه تفکیک جنسیتی (مرد و زن)
                                m_cand = len(df_emp[df_emp['جنسیت'] == 'مرد'])
                                f_cand = len(df_emp[df_emp['جنسیت'] == 'زن'])
                                
                                m_hired_c = len(hired_df_local[hired_df_local['جنسیت'] == 'مرد'])
                                f_hired_c = len(hired_df_local[hired_df_local['جنسیت'] == 'زن'])

                                if m_hired_c > 0:
                                    raw_m = int(m_cand/m_hired_c)
                                    m_eff_text = f"۱:{to_persian_num(raw_m)}" 
                                else: m_eff_text = "-"
                                    
                                if f_hired_c > 0:
                                    raw_f = int(f_cand/f_hired_c)
                                    f_eff_text = f"۱:{to_persian_num(raw_f)}"
                                else: f_eff_text = "-"

                                # 5. ساخت استایل شیشه‌ای (دقیقاً مشابه بقیه کارت‌ها)
                                gender_html_efficiency = f"""
                                <div style="background: rgba(255, 255, 255, 0.6); border-radius: 8px; padding: 6px 10px; display: flex; justify-content: space-between; align-items: center; margin-top: auto; font-size: 14px; color: #444; font-weight: 600; backdrop-filter: blur(4px); border: 1px solid rgba(255,255,255,0.4); font-family: 'B Nazanin', Tahoma, sans-serif !important;">
                                    <div style="display:flex; align-items:center;">👨 {m_eff_text}</div>
                                    <div style="width:1px; height:12px; background:#ccc; margin:0 5px;"></div>
                                    <div style="display:flex; align-items:center;">👩 {f_eff_text}</div>
                                </div>
                                """
                                
                                # 6. نمایش نهایی کارت
                                st.markdown(f"""
                                <div class="gradient-card" style="background: linear-gradient(135deg, #eceff1 0%, #cfd8dc 100%);">
                                    <div class="watermark-icon">⚖️</div>
                                    <div class="card-content">
                                        <div class="g-title">شاخص بازدهی جذب</div>
                                        <div class="g-value">{effort_text_persian}</div>
                                        <div class="g-sub" style="font-size: 11px !important; margin-bottom: 5px;">بررسی به ازای ۱ استخدام</div>
                                        {gender_html_efficiency}
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                            st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)

                            # =========================================================
                            # 🧠 بخش اتاق فکر (استایل آبی، همیشه باز، متن درشت)
                            # =========================================================
                            if withdrawal_rate > rejection_rate:
                                main_insight = "⚠️ **چالش برند کارفرمایی:** نرخ انصراف بیشتر از نرخ رد شدن است. سازمان در «جذب» مشکل ندارد اما در «متقاعدسازی و نگهداشت» کاندیداها چالش دارد."
                                action_item = "بررسی رقابتی بودن حقوق و مزایا."
                                sentiment_color = "#fff3cd"
                            elif rejection_rate > 70:
                                main_insight = "⚠️ **چالش کانال‌های ورودی:** نرخ رد شدن بسیار بالاست (بیش از ۷۰٪). زمان زیادی صرف مصاحبه با افراد نامرتبط می‌شود."
                                action_item = "اصلاح شرح شغل در آگهی‌ها + استفاده از فیلترهای اولیه دقیق‌تر."
                                sentiment_color = "#f8d7da"
                            else:
                                main_insight = "✅ **تعادل پایدار:** نسبت‌های جذب، رد و انصراف در وضعیت نرمال و سالمی قرار دارند."
                                action_item = "حفظ رویه فعلی و تمرکز بر کاهش زمان استخدام."
                                sentiment_color = "#d4edda"

                            st.markdown("""
                            <style>
                                div[data-testid="stExpander"] details > summary {
                                    background-color: #033270 !important;
                                    color: white !important;
                                    border-radius: 10px !important;
                                    padding: 12px 15px !important;
                                    border: 1px solid #033270 !important;
                                    margin-bottom: 0px !important;
                                }
                                div[data-testid="stExpander"] details > summary span, 
                                div[data-testid="stExpander"] details > summary p, 
                                div[data-testid="stExpander"] details > summary svg {
                                    color: white !important;
                                    fill: white !important;
                                    font-weight: 900 !important;
                                    font-size: 16px !important;
                                }
                                div[data-testid="stExpander"] details > div {
                                    background-color: #ffffff !important;
                                    border: 2px solid #033270 !important;
                                    border-radius: 0 0 10px 10px !important;
                                    border-top: none !important;
                                    margin-top: -5px !important;
                                    padding-top: 15px !important;
                                }
                                div[data-testid="stExpander"] details[open] > summary {
                                    border-bottom-left-radius: 0 !important;
                                    border-bottom-right-radius: 0 !important;
                                    border-bottom: 1px solid #033270 !important;
                                }
                            </style>
                            """, unsafe_allow_html=True)

                            with st.expander("🧠اتاق فکر و بینش", expanded=True):
                                ac1, ac2, ac3 = st.columns([1.5, 1.5, 1])
                                
                                with ac1:
                                    st.markdown(f"""
                                    <div style="direction: rtl; text-align: right; height: 100%;">
                                        <h5 style="color: #033270; border-bottom: 2px solid #eee; padding-bottom: 8px; font-weight: 900; font-size: 16px;">📊 تفسیر قیف جذب</h5>
                                        <ul style="font-size: 14px; line-height: 2.4; color: #222; font-weight: bold; margin-top: 10px;">
                                            <li>کارایی سیستم: برای هر استخدام نهایی، <b style="color:#033270; font-size: 15px;">{selection_ratio.split(':')[1] if ':' in selection_ratio else 0}</b> مصاحبه انجام شده است.</li>
                                            <li>کیفیت ورودی: <b style="color:#c0392b; font-size: 15px;">{rejection_rate:.1f}٪</b> از متقاضیان رد شدند.</li>
                                            <li>جذابیت سازمان: <b style="color:#f39c12; font-size: 15px;">{withdrawal_rate:.1f}٪</b> از افراد تایید شده، انصراف دادند.</li>
                                        </ul>
                                    </div>""", unsafe_allow_html=True)
                                
                                with ac2:
                                    st.markdown(f"""
                                    <div style="direction: rtl; text-align: right; height: 100%;">
                                        <h5 style="color: #033270; border-bottom: 2px solid #eee; padding-bottom: 8px; font-weight: 900; font-size: 16px;">💡 تجویز مدیریتی</h5>
                                        <div style="background-color: {sentiment_color}; padding: 12px; border-radius: 8px; font-size: 14px; line-height: 1.8; color: #000; font-weight: bold;">
                                            {main_insight}
                                        </div>
                                        <div style="margin-top: 12px; font-size: 14px; font-weight: 900; color: #033270;">
                                            🚀 اقدام پیشنهادی:<br>
                                            <span style="font-weight: bold; color: #333; font-size: 14px;">{action_item}</span>
                                        </div>
                                    </div>""", unsafe_allow_html=True)
                                
                                with ac3:
                                    st.markdown(f"""
                                    <div style="text-align: center; display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding-top: 5px;">
                                        <div style="font-size: 14px; color: #222; margin-bottom: 8px; font-weight: 900;">شاخص کیفیت جذب</div>
                                        <div style="width: 85px; height: 85px; border-radius: 50%; background: conic-gradient(#2ecc71 {health_score}%, #eee 0); display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(0,0,0,0.1);">
                                            <div style="width: 70px; height: 70px; background: white; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: 900; font-size: 22px; color: #2ecc71;">{health_score}</div>
                                        </div>
                                        <div style="font-size: 13px; color: #555; margin-top: 8px; font-weight: bold;">از 100</div>
                                    </div>""", unsafe_allow_html=True)

                            st.markdown("<hr style='margin: 30px 0; opacity: 0.2;'>", unsafe_allow_html=True)

                            # =========================================================
                            # 4. نمودارها (با استایل باکس کارتی سایه‌دار)
                            # =========================================================

                            # ✅ استایل باکس‌ها بازگشت به حالت کارتی سایه‌دار و خط جداکننده
                            st.markdown("""
                            <style>
                                .analysis-box {
                                    background-color: #ffffff;
                                    border: 1px solid #cfd8dc;
                                    border-radius: 16px;
                                    padding: 20px 20px;
                                    height: 480px !important;
                                    overflow-y: auto;
                                    direction: rtl;
                                    text-align: right;
                                    /* 👇 سایه و استایل کارتی */
                                    box-shadow: 0 10px 25px rgba(0,0,0,0.08); 
                                    border-right: 6px solid #033270;
                                }
                                .analysis-title {
                                    color: #033270;
                                    font-weight: 900;
                                    font-size: 1.25rem;
                                    margin-bottom: 15px;
                                    /* 👇 خط جداکننده زیر تیتر */
                                    border-bottom: 2px solid #e0e0e0;
                                    padding-bottom: 10px;
                                    font-family: 'B Nazanin';
                                }
                                .analysis-content {
                                    font-size: 16px !important;
                                    line-height: 1.8 !important;
                                    color: #333; /* رنگ متن */
                                    font-family: 'B Nazanin';
                                    text-align: justify;
                                }
                                .analysis-content ul {
                                    margin-top: 5px; margin-bottom: 5px; padding-right: 20px;
                                }
                            </style>
                            """, unsafe_allow_html=True)

                            # --- ردیف ۱: قیف جذب ---
                            df_chart_all = pd.DataFrame()
                            avg_conversion = 0; iph = 0; best_unit = None; worst_unit = None
                            
                            if 'واحد' in df_emp.columns:
                                interview_counts = df_emp['واحد'].value_counts()
                                if 'تاریخ شروع بکار' in df_emp.columns:
                                    hired_mask = (df_emp['تاریخ شروع بکار'].notna()) & \
                                                (~df_emp['تاریخ شروع بکار'].astype(str).str.contains('عدم استخدام|نامشخص', case=False, na=False))
                                    hired_counts = df_emp.loc[hired_mask, 'واحد'].value_counts()
                                else: hired_counts = pd.Series()
                                df_chart_all = pd.DataFrame({'Interview': interview_counts, 'Hired': hired_counts}).fillna(0)
                                df_chart_all['Hired'] = df_chart_all['Hired'].astype(int)
                                df_chart_all['Rate'] = (df_chart_all['Hired'] / df_chart_all['Interview'] * 100).fillna(0).round(1)
                                total_int = df_chart_all['Interview'].sum(); total_h = df_chart_all['Hired'].sum()
                                avg_conversion = (total_h / total_int * 100) if total_int > 0 else 0
                                iph = (total_int / total_h) if total_h > 0 else total_int
                                if not df_chart_all.empty:
                                    q_df = df_chart_all[df_chart_all['Interview'] >= 3]
                                    if not q_df.empty:
                                        best_unit = q_df.sort_values('Rate', ascending=False).iloc[0]
                                        worst_unit = q_df.sort_values('Rate', ascending=True).iloc[0]

                            c1_right, c1_left = st.columns([2.2, 1])
                            
                            with c1_right:
                                if not df_chart_all.empty:
                                    df_plot = df_chart_all.sort_values('Interview', ascending=False)
                                    fig_ov = go.Figure()
                                    fig_ov.add_trace(go.Bar(
                                        x=df_plot.index, y=df_plot['Interview'], name='کل متقاضیان',
                                        marker_color='rgba(189, 195, 199, 0.5)', width=0.75, marker_line_width=0,
                                        hovertemplate='<span style="color:black; font-family:B Nazanin; font-size:14px;"><b>کل متقاضیان</b>: %{y} نفر</span><br><span style="color:black; font-family:B Nazanin; font-size:14px;"><b>واحد</b>: %{x}</span><extra></extra>'
                                    ))
                                    fig_ov.add_trace(go.Bar(
                                        x=df_plot.index, y=df_plot['Hired'], name='جذب موفق',
                                        marker_color='#033270', width=0.35, text=df_plot['Hired'], textposition='outside',
                                        textfont=dict(color='black', size=14, weight='bold'), marker_line_width=0,
                                        hovertemplate='<span style="color:black; font-family:B Nazanin; font-size:14px;"><b>جذب موفق</b>: %{y} نفر</span><br><span style="color:black; font-family:B Nazanin; font-size:14px;"><b>نرخ تبدیل</b>: %{customdata}%</span><extra></extra>',
                                        customdata=df_plot['Rate']
                                    ))
                                    fig_ov.update_layout(
                                        title={'text': '📊 کارنامه جذب واحدها', 'y': 0.95, 'x': 1, 'xanchor': 'right', 'xref': 'paper'},
                                        title_font=dict(size=22, family="B Nazanin", color="black", weight="bold"),
                                        font=dict(family="B Nazanin", color="black"),
                                        plot_bgcolor='white', paper_bgcolor='white',
                                        height=480, barmode='overlay',
                                        hoverlabel=dict(bgcolor="#E3F2FD", bordercolor="#2E86C1", font=dict(color="black", family="B Nazanin", size=14)),
                                        xaxis=dict(tickangle=-45, showline=False, showgrid=False, tickfont=dict(color='black', size=14)),
                                        yaxis=dict(showline=False, showgrid=True, gridcolor='#eee', tickfont=dict(color='black', size=14)),
                                        legend=dict(orientation="h", y=1.1, x=0, font=dict(color='black', size=14)),
                                        margin=dict(t=60, b=80, l=40, r=20)
                                    )
                                    st.plotly_chart(fig_ov, use_container_width=True)
                                else: st.info("داده موجود نیست")

                            with c1_left:
                                if best_unit is not None:
                                    gap = best_unit['Rate'] - avg_conversion
                                    eff_status = "مطلوب" if iph < 6 else ("نیازمند بهبود" if iph < 12 else "بحرانی")
                                    html_1 = f"""
                                    <div class="analysis-title">🎯 تحلیل نرخ تبدیل مصاحبه به استخدام</div>
                                    <div class="analysis-content">
                                        <ul style="list-style-type:none; padding:0; margin:0 0 10px 0;">
                                            <li><b>میانگین تبدیل:</b> <span style="color:#000000; font-weight:bold;">{avg_conversion:.1f}%</span></li>
                                            <li><b>شاخص تلاش:</b> <span style="color:#000000; font-weight:bold;">{iph:.1f}</span></li>
                                        </ul>
                                        <p>وضعیت غربالگری در حالت <b>«{eff_status}»</b> است. یعنی برای ۱ استخدام، {int(iph)} مصاحبه انجام شده است.</p>
                                        <div style="background:#e8f5e9; padding:8px; border-radius:8px; margin-top:8px; color:black;">
                                            🌟 <b>ستاره جذب:</b><br> واحد <b>{best_unit.name}</b> با نرخ {best_unit['Rate']}% عملکردی درخشان داشته است.
                                        </div>
                                        <div style="background:#fff3e0; padding:8px; border-radius:8px; margin-top:8px; color:black;">
                                            ⚠️ <b>نیاز به بازنگری:</b><br> واحد <b>{worst_unit.name if worst_unit is not None else '-'}</b> بیشترین هدررفت زمان مصاحبه را دارد.
                                        </div>
                                    </div>
                                    """
                                    st.markdown(f'<div class="analysis-box">{html_1}</div>', unsafe_allow_html=True)
                                else: st.markdown(f'<div class="analysis-box">داده کافی نیست.</div>', unsafe_allow_html=True)

                            st.markdown("<hr style='margin: 30px 0; opacity: 0.2;'>", unsafe_allow_html=True)

                            # --- ردیف ۲: کانال‌های جذب ---
                            ref_df = pd.DataFrame()
                            if 'معرف' in df_emp.columns:
                                df_emp['معرف'] = df_emp['معرف'].fillna('نامشخص').astype(str)
                                referrer_total = df_emp['معرف'].value_counts()
                                if 'تاریخ شروع بکار' in df_emp.columns:
                                    hired_ref = df_emp[
                                        (df_emp['تاریخ شروع بکار'].notna()) & 
                                        (~df_emp['تاریخ شروع بکار'].astype(str).str.contains('عدم استخدام|نامشخص', case=False, na=False))
                                    ]['معرف'].value_counts()
                                else: hired_ref = pd.Series()
                                ref_df = pd.DataFrame({'کل معرفی': referrer_total}).reset_index()
                                ref_df.columns = ['معرف', 'کل معرفی']
                                ref_df['جذب شده'] = ref_df['معرف'].map(hired_ref).fillna(0)
                                ref_df['نرخ تبدیل'] = (ref_df['جذب شده'] / ref_df['کل معرفی'] * 100).fillna(0)

                            c2_right, c2_left = st.columns([2.2, 1])

                            with c2_right:
                                if not ref_df.empty:
                                    plot_df = ref_df[ref_df['کل معرفی'] > 0].sort_values('جذب شده', ascending=False).head(8)
                                    fig_ref = go.Figure()
                                    fig_ref.add_trace(go.Bar(
                                        x=plot_df['معرف'], y=plot_df['کل معرفی'], name='تعداد ورودی', 
                                        marker_color='#4FC3F7', text=plot_df['کل معرفی'], textposition='outside',
                                        textfont=dict(color='black', size=14, weight='bold'), marker_line_width=0,
                                        hovertemplate='<span style="color:black; font-family:B Nazanin; font-size:14px;"><b>تعداد ورودی</b>: %{y} نفر</span><br><span style="color:black; font-family:B Nazanin; font-size:14px;"><b>کانال</b>: %{x}</span><extra></extra>'
                                    ))
                                    fig_ref.add_trace(go.Scatter(
                                        x=plot_df['معرف'], y=plot_df['جذب شده'], name='استخدام موفق', 
                                        mode='lines+markers+text', text=plot_df['جذب شده'], textposition='top center',
                                        line=dict(color='#0D47A1', width=3), textfont=dict(color='black', size=14, weight='bold'),
                                        hovertemplate='<span style="color:black; font-family:B Nazanin; font-size:14px;"><b>استخدام موفق</b>: %{y} نفر</span><br><span style="color:black; font-family:B Nazanin; font-size:14px;"><b>کانال</b>: %{x}</span><extra></extra>'
                                    ))
                                    fig_ref.update_layout(
                                        title={'text': '💎 عملکرد کانال‌های جذب نیرو', 'y': 0.95, 'x': 1, 'xanchor': 'right', 'xref': 'paper'},
                                        title_font=dict(size=22, family="B Nazanin", color="black", weight="bold"),
                                        font=dict(family="B Nazanin", color="black"),
                                        plot_bgcolor='white', paper_bgcolor='white',
                                        height=480,
                                        hoverlabel=dict(bgcolor="#E3F2FD", bordercolor="#2E86C1", font=dict(color="black", family="B Nazanin", size=14)),
                                        xaxis=dict(showline=False, showgrid=False, tickfont=dict(color='black', size=14)),
                                        yaxis=dict(showline=False, showgrid=True, gridcolor='#eee', tickfont=dict(color='black', size=14)),
                                        legend=dict(orientation="h", y=1.1, x=0, font=dict(color='black', size=14)),
                                        margin=dict(t=60, b=50, l=40, r=40)
                                    )
                                    st.plotly_chart(fig_ref, use_container_width=True)
                                else: st.info("داده کانال موجود نیست")

                            with c2_left:
                                if not ref_df.empty:
                                    top_vol = ref_df.sort_values('کل معرفی', ascending=False).iloc[0]
                                    top_qual = ref_df[ref_df['کل معرفی'] >= 3].sort_values('نرخ تبدیل', ascending=False).iloc[0] if len(ref_df[ref_df['کل معرفی'] >= 3])>0 else top_vol
                                    top5 = ref_df[['معرف', 'نرخ تبدیل']].sort_values('نرخ تبدیل', ascending=False).head(5)
                                    top5_html = "".join([f"<li style='display:flex; justify-content:space-between; border-bottom:1px solid #eee; padding:2px 0;'><span>{r['معرف']}</span><b>{r['نرخ تبدیل']:.0f}%</b></li>" for _,r in top5.iterrows()])
                                    html_2 = f"""
                                    <div class="analysis-title">📊 تحلیل کانال‌های ورودی</div>
                                    <div class="analysis-content">
                                        <ul style="list-style-type:none; padding:0; margin:0;">
                                            <li>🔹 <b>منبع حجمی:</b> کانال <b>«{top_vol['معرف']}»</b> با {int(top_vol['کل معرفی'])} رزومه.</li>
                                            <li>🔸 <b>منبع کیفی:</b> کانال <b>«{top_qual['معرف']}»</b> با نرخ <b>{top_qual['نرخ تبدیل']:.1f}%</b>.</li>
                                        </ul>
                                        <div style="background:#f8f9fa; padding:10px; border-radius:8px; margin-top:10px; color:black;">
                                            <b>🏆 رده‌بندی کیفیت:</b>
                                            <ul style="list-style-type:none; padding:0; margin:5px 0 0 0;">{top5_html}</ul>
                                        </div>
                                    </div>
                                    """
                                    st.markdown(f'<div class="analysis-box">{html_2}</div>', unsafe_allow_html=True)
                                else: st.markdown(f'<div class="analysis-box">داده کافی نیست.</div>', unsafe_allow_html=True)

                            st.markdown("<hr style='margin: 30px 0; opacity: 0.2;'>", unsafe_allow_html=True)

                            # =========================================================
                            # داده‌های ریزش (مشترک ردیف ۳ و ۴)
                            # =========================================================
                            status_col = df_emp['وضعیت نهایی'] if 'وضعیت نهایی' in df_emp.columns else pd.Series()
                            churn_mask = status_col.astype(str).str.strip().isin(['رد شد', 'انصراف داد'])
                            churn_df = df_emp[churn_mask].copy()

                            if len(churn_df) > 0:
                                if 'علت نپذیرفتن' in churn_df.columns:
                                    churn_df['علت نپذیرفتن'] = churn_df['علت نپذیرفتن'].fillna('نامشخص')
                                    churn_df['علت_دسته_بندی_شده'] = churn_df['علت نپذیرفتن'].apply(categorize_rejection_reason)
                                else: churn_df['علت_دسته_بندی_شده'] = 'نامشخص'

                                # ---------------------------------------------------------
                                # ردیف ۳: نقشه حرارتی (Heatmap)
                                # ---------------------------------------------------------
                                c3_right, c3_left = st.columns([2.2, 1])

                                with c3_right:
                                    f_col, t_col = st.columns([1, 2])
                                    with t_col: 
                                        st.markdown("<h5 style='color:#033270; margin:0;'>توزیع دلایل رد و انصراف در واحدها 🗺️</h5>", unsafe_allow_html=True)
                                    
                                    with f_col: 
                                        selected_view = st.selectbox(
                                            "سطح نمایش:", 
                                            ["👁️ نمای کلان (وضعیت)", "📂 علل دسته‌بندی شده", "📝 علل دقیق (با جزئیات)"], 
                                            key="lvl_select", 
                                            label_visibility="collapsed"
                                        )
                                    
                                    import textwrap
                                    if "نمای کلان" in selected_view:
                                        # رنگ‌ها از گرادینت‌های کارت‌ها گرفته شده‌اند (صورتی/قرمز برای رد، نارنجی/زرد برای انصراف)
                                        plot_df = churn_df.copy(); y_col = 'وضعیت نهایی'; color_col = 'وضعیت نهایی'; color_scale = None; 
                                        color_map = {'رد شد': '#f5576c', 'انصراف داد': '#fb8c00'} 
                                    elif "دسته‌بندی" in selected_view:
                                        # تغییر رنگ قرمز به بنفش (هماهنگ با کارت‌های بنفش)
                                        plot_df = churn_df.copy(); y_col = 'علت_دسته_بندی_شده'; color_col = 'تعداد'; color_scale = 'Blues'; color_map = None
                                    else:
                                        # تغییر رنگ نارنجی به آبی (هماهنگ با تم اصلی)
                                        plot_df = churn_df.copy(); y_col = 'علت نپذیرفتن'; color_col = 'تعداد'; color_scale = 'Blues'; color_map = None 

                                    if y_col not in plot_df.columns: plot_df[y_col] = "نامشخص"
                                    
                                    chart_data = plot_df.groupby([y_col, 'واحد']).size().reset_index(name='تعداد')
                                    chart_data['نمایش_محور'] = chart_data[y_col].apply(lambda x: '<br>'.join(textwrap.wrap(str(x), width=35)))
                                    
                                    fig_heat = px.scatter(
                                        chart_data, x='واحد', y='نمایش_محور', size='تعداد', 
                                        color=color_col, color_continuous_scale=color_scale, color_discrete_map=color_map,
                                        size_max=45, text='تعداد',
                                        custom_data=[chart_data[y_col]]
                                    )
                                    
                                    fig_heat.update_traces(
                                        textposition='top center', cliponaxis=False,
                                        textfont=dict(family="B Nazanin", size=14, weight="bold", color="black"),
                                        marker=dict(line=dict(width=0)),
                                        hovertemplate='<span style="color:black; font-family:B Nazanin; font-size:14px;"><b>تعداد</b>: %{text} نفر</span><br><span style="color:black; font-family:B Nazanin; font-size:14px;"><b>واحد</b>: %{x}</span><br><span style="color:black; font-family:B Nazanin; font-size:14px;"><b>علت</b>: %{customdata[0]}</span><extra></extra>'
                                    )
                                    
                                    fig_heat.update_layout(
                                        font=dict(family="B Nazanin", color="black"),
                                        plot_bgcolor='white', paper_bgcolor='white',
                                        height=480,
                                        hoverlabel=dict(bgcolor="#E3F2FD", bordercolor="#2E86C1", font=dict(color="black", family="B Nazanin", size=14)),
                                        xaxis=dict(tickangle=-45, showline=False, showgrid=True, gridcolor='#f0f0f0', tickfont=dict(color='black', size=14)),
                                        yaxis=dict(showline=False, showgrid=True, gridcolor='#f0f0f0', tickfont=dict(color='black', size=16, weight="bold")),
                                        legend=dict(orientation="h", y=1.1, font=dict(color='black', size=14)),
                                        margin=dict(t=50, b=80, l=150, r=20)
                                    )
                                    st.plotly_chart(fig_heat, use_container_width=True)

                                with c3_left:
                                    status_str = churn_df['وضعیت نهایی'].astype(str)
                                    rej_c = len(churn_df[status_str.str.contains('رد', case=False)])
                                    wdr_c = len(churn_df[status_str.str.contains('انصراف', case=False)])
                                    tot_c = len(churn_df)
                                    rr = int((rej_c/tot_c)*100) if tot_c>0 else 0
                                    wr = int((wdr_c/tot_c)*100) if tot_c>0 else 0
                                    top_churn_unit = churn_df['واحد'].value_counts().idxmax() if not churn_df.empty else "-"

                                    if wr > rr:
                                        state_t = "چالش جذابیت"; icon = "⚠️"; color = "#ef6c00"; msg = "انصراف بالاست. شرایط کاری جذاب نیست."
                                    elif rr > wr:
                                        state_t = "ورودی نامناسب"; icon = "🚫"; color = "#c62828"; msg = "رد شدن بالاست. فیلتر ورودی دقیق نیست."
                                    else:
                                        state_t = "وضعیت متعادل"; icon = "⚖️"; color = "#2e7d32"; msg = "توزیع نرمال است."

                                    html_3 = f"""
                                    <div class="analysis-title">⚖️ مقایسه سهم رد صلاحیت و انصراف داوطلب</div>
                                    <div class="analysis-content">
                                        <div style="display:flex; justify-content:space-between; margin-bottom:10px; text-align:center;">
                                            <div style="background:#fff3e0; padding:8px; border-radius:8px; width:48%;">
                                                <span style="font-size:12px;">انصراف</span><br><b style="font-size:20px; color:#ef6c00;">{wr}%</b>
                                            </div>
                                            <div style="background:#ffebee; padding:8px; border-radius:8px; width:48%;">
                                                <span style="font-size:12px;">رد شده</span><br><b style="font-size:20px; color:#c62828;">{rr}%</b>
                                            </div>
                                        </div>
                                        <div style="background:#f9f9f9; padding:10px; border-radius:6px; border-right:4px solid {color}; margin-bottom:10px;">
                                            <b style="color:{color}; font-size:16px;">{icon} {state_t}</b><br>{msg}
                                        </div>
                                        <div style="font-size:14px; color:#666;">
                                            🏭 <b>واحد پرچالش:</b><br> واحد «{top_churn_unit}» بیشترین ریزش را دارد.
                                        </div>
                                    </div>
                                    """
                                    st.markdown(f'<div class="analysis-box">{html_3}</div>', unsafe_allow_html=True)

                                st.markdown("<hr style='margin: 30px 0; opacity: 0.2;'>", unsafe_allow_html=True)

                                # ---------------------------------------------------------
                                # ردیف ۴: پارتو (Pareto)
                                # ---------------------------------------------------------
                                c4_right, c4_left = st.columns([2.2, 1])

                                with c4_right:
                                    pareto_df = churn_df['علت_دسته_بندی_شده'].value_counts().head(5).reset_index()
                                    pareto_df.columns = ['علت', 'تعداد']
                                    pareto_df['درصد'] = ((pareto_df['تعداد'] / tot_c) * 100).round(1)
                                    max_val = pareto_df['تعداد'].max() if not pareto_df.empty else 10

                                    # تعریف طیف رنگی سفارشی: از آبی آسمانی (#90caf9) تا سرمه‌ای سازمانی (#033270)
                                    fig_par = px.bar(
                                        pareto_df, 
                                        x='علت', 
                                        y='تعداد', 
                                        text='تعداد', 
                                        color='تعداد', 
                                        color_continuous_scale=[(0, "#90caf9"), (1, "#033270")]
                                    )
                                    fig_par.update_traces(
                                        textposition='outside', marker_cornerradius=6, cliponaxis=False,
                                        textfont=dict(color='black', size=14, weight='bold'),
                                        marker_line_width=0,
                                        customdata=pareto_df['درصد'],
                                        hovertemplate='<span style="color:black; font-family:B Nazanin; font-size:14px;"><b>تعداد</b>: %{y} نفر</span><br><span style="color:black; font-family:B Nazanin; font-size:14px;"><b>علت</b>: %{x}</span><br><span style="color:black; font-family:B Nazanin; font-size:14px;"><b>سهم</b>: %{customdata}%</span><extra></extra>'
                                    )
                                    # افزایش رنج محور عمودی برای جلوگیری از بریدن اعداد بالا
                                    fig_par.update_layout(
                                        title={'text': '🛑 فراوانی دلایل شکست در استخدام', 'y': 0.95, 'x': 1, 'xanchor': 'right', 'xref': 'paper'},
                                        title_font=dict(size=22, family="B Nazanin", color="black", weight="bold"),
                                        font=dict(family="B Nazanin", color="black"),
                                        plot_bgcolor='white', paper_bgcolor='white',
                                        height=480,
                                        hoverlabel=dict(bgcolor="#E3F2FD", bordercolor="#2E86C1", font=dict(color="black", family="B Nazanin", size=14)),
                                        xaxis=dict(tickangle=-45, showline=False, tickfont=dict(color='black', size=14)),
                                        yaxis=dict(showline=False, showgrid=False, range=[0, max_val * 1.35], tickfont=dict(color='black', size=14)),
                                        coloraxis_showscale=False,
                                        margin=dict(t=60, b=100, l=50, r=20)
                                    )
                                    st.plotly_chart(fig_par, use_container_width=True)

                                with c4_left:
                                    if not pareto_df.empty:
                                        top_cause = pareto_df.iloc[0]
                                        cause_n = top_cause['علت']; cause_p = top_cause['درصد']
                                        s_map = {
                                            'حقوق': "بازنگری پکیج جبران خدمات", 'مسیر': "راه‌اندازی سرویس", 
                                            'فنی': "سخت‌گیری در غربالگری اولیه", 'ساعت': "شفاف‌سازی شیفت کاری", 
                                            'محیط': "بهبود برند کارفرمایی", 'عدم تایید': "دقت در انطباق رزومه با JD"
                                        }
                                        sol = "مصاحبه خروج دقیق"
                                        for k,v in s_map.items(): 
                                            if k in str(cause_n): sol=v; break
                                        
                                        html_4 = f"""
                                        <div class="analysis-title">🩺 عارضه‌یابی ریشه‌ای</div>
                                        <div class="analysis-content">
                                            <div style="background:#fff5f5; border:1px solid #ffcccc; color:#990000; padding:10px; border-radius:8px; margin-bottom:10px;">
                                                🚫 <b>عامل اصلی شکست:</b><br>
                                                علت <b>«{cause_n}»</b> به تنهایی مسئول <b>{cause_p}%</b> از کل موارد ریزش است.
                                            </div>
                                            <div style="margin-bottom:10px;">
                                                💊 <b>تجویز راهبردی:</b><br>
                                                <span style="color:#033270; font-weight:bold;">{sol}</span>
                                            </div>
                                            <p style="font-size:14px; color:#666; margin-top:10px; border-top:1px dashed #ccc; padding-top:8px;">
                                                طبق اصل پارتو، رفع همین یک گلوگاه نیمی از مشکلات را حل می‌کند.
                                            </p>
                                        </div>
                                        """
                                        st.markdown(f'<div class="analysis-box">{html_4}</div>', unsafe_allow_html=True)
                                    else: st.markdown(f'<div class="analysis-box">داده موجود نیست.</div>', unsafe_allow_html=True)

                            else: st.success("✨ داده‌ای برای تحلیل ریزش موجود نیست.")
                        else:
                            st.warning("هنوز داده‌ای بارگذاری نشده است. لطفاً دکمه بارگذاری را بزنید.")
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
    # بخش 3: بانک اطلاعات سرمایه انسانی (با ترتیب ستون‌های درخواستی)
    # ---------------------------------------------------------

    elif st.session_state.hr_active_tab == "بانک اطلاعات سرمایه انسانی":
        ensure_data_loaded("personnel")
        
        # تیتر
        st.markdown("""
            <div style="margin-top: -500px !important; padding-bottom: 10px !important;">
                <h3 style="color: #033270; font-family: 'B Nazanin'; font-size: 2rem;">
                    🗂️ بانک اطلاعات سرمایه انسانی
                </h3>
            </div>
        """, unsafe_allow_html=True)
        
        # ✅ شرط اصلی: بررسی وجود داده
        if st.session_state.personnel_data is not None:
            df = st.session_state.personnel_data.copy()
            
            # 1. تمیزکاری نام ستون‌ها
            df.columns = [str(col).strip().replace('ي', 'ی').replace('ك', 'ک') for col in df.columns]

            # 2. فیلترها (با فونت بی نازنین)
            st.markdown("""
                <div style="margin-bottom: 10px; margin-top: 40px;">
                    <span style="font-family: 'B Nazanin'; font-size: 1.1rem; font-weight: bold; color: #033270; border-bottom: 2px solid #eee; display: inline-block; width: 100%;">
                        🔍 فیلترها
                    </span>
                </div>
            """, unsafe_allow_html=True)
            
            col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4, gap="small")
            
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
            
            # 4. انتخاب ستون‌ها
            target_columns_personnel = [
                "محل خدمت", "میانگین حقوق", "رشته تحصیلی", "وضعیت نظام وظیفه", 
                "تعداد فرزند", "وضعیت تاهل", "جنسیت", "میزان تحصیلات", "آدرس", 
                "تاریخ تولد", "نوع قرارداد", "وضعیت کار", "تاریخ ترک کار", 
                "مدت آخرین قرارداد(ماه)", "تاریخ آخرین قرارداد", "تاریخ استخدام", 
                "زیر گروه", "واحد", "نام خانوادگی", "نام", "شماره پرسنلی"
            ]
            
            final_cols = [col for col in target_columns_personnel if col in filtered_df.columns]
            
            if final_cols:
                filtered_df = filtered_df[final_cols]

            # 5. نمایش نهایی (داخل if)
            st.dataframe(
                style_dataframe(filtered_df),  # ✅ اعمال استایل آبی ملیح
                use_container_width=True,
                height=600,
                hide_index=True
            )
        else:
            st.warning("هنوز داده‌ای بارگذاری نشده است.")
   # ---------------------------------------------------------
    # بخش 4: جذب و استخدام (اصلاح نهایی و قطعی)
    # ---------------------------------------------------------

    elif st.session_state.hr_active_tab == "جذب و استخدام":
        ensure_data_loaded("employee")
        
            # تیتر
        st.markdown("""
            <div style="margin-top: -700px !important; padding-bottom: 10px !important;">
                <h3 style="color: #033270; font-family: 'B Nazanin'; font-size: 2rem;">
                    📝 جذب و استخدام
                </h3>
            </div>
        """, unsafe_allow_html=True)
        
        # ✅ شرط اصلی: بررسی وجود داده
        if st.session_state.employee_data is not None:
            # 1. کپی داده‌ها
            df_emp = st.session_state.employee_data.copy()
            
            # 2. محاسبات آماری (داخل شرط)
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
            
            # 3. نمایش کارت‌های آمار
        
            # 3. نمایش کارت‌های آمار (با فونت مشکی)
            col1, col2, col3, col4, col5 = st.columns(5)
            # تعریف استایل مشکی اجباری برای همه اجزا
            black_style = "color: #000000 !important; text-shadow: none !important;"
            
            with col1: 
                st.markdown(f'''
                <div class="stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); {black_style}">
                    <h3 style="{black_style}">👥 نفرات مصاحبه شده</h3>
                    <div class="stat-number" style="{black_style}">{total_interviewed}</div>
                    <div class="stat-label" style="{black_style}">نفر</div>
                </div>
                ''', unsafe_allow_html=True)
            
            with col2: 
                st.markdown(f'''
                <div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); {black_style}">
                    <h3 style="{black_style}">🎯 بیشترین مصاحبه</h3>
                    <div class="stat-number" style="{black_style}">{most_interviewed_count}</div>
                    <div class="stat-label" style="{black_style}">{most_interviewed_unit} ({most_interviewed_percentage}%)</div>
                </div>
                ''', unsafe_allow_html=True)
            
            with col3: 
                st.markdown(f'''
                <div class="stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); {black_style}">
                    <h3 style="{black_style}">✅ استخدام شدگان</h3>
                    <div class="stat-number" style="{black_style}">{hired_count}</div>
                    <div class="stat-label" style="{black_style}">{hired_percentage}% از {total_interviewed} نفر</div>
                </div>
                ''', unsafe_allow_html=True)
            
            with col4: 
                st.markdown(f'''
                <div class="stat-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); {black_style}">
                    <h3 style="{black_style}">🏆 بیشترین استخدام</h3>
                    <div class="stat-number" style="{black_style}">{most_hired_unit}</div>
                    <div class="stat-label" style="{black_style}">مرد: {gender_percentages.get("مرد", 0)}% | زن: {gender_percentages.get("زن", 0)}%</div>
                </div>
                ''', unsafe_allow_html=True)
            
            with col5: 
                st.markdown(f'''
                <div class="stat-card" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%); {black_style}">
                    <h3 style="{black_style}">❓ نامشخص</h3>
                    <div class="stat-number" style="{black_style}">{undecided_count}</div>
                    <div class="stat-label" style="{black_style}">{undecided_percentage}% از {total_interviewed} نفر</div>
                </div>
                ''', unsafe_allow_html=True)
            
            # 4. آماده‌سازی جدول
            st.subheader("📊 لیست مصاحبه‌شوندگان")
            
            desired_columns = [
                "ماه", "وضعیت نهایی", "علت_دسته_بندی_شده", "علت نپذیرفتن", 
                "تاریخ شروع بکار", "معرف", "جنسیت", "واحد", "نام و نام خانوادگی"
            ]
            # لیست ستون‌ها به ترتیب دلخواه شما (دقت کنید کاماها فراموش نشوند)
            desired_columns = [
                "ماه",
                "وضعیت نهایی",
                "علت_دسته_بندی_شده",
                "علت نپذیرفتن",
                "تاریخ شروع بکار",
                "معرف",
                "جنسیت",
                "واحد",
                "نام و نام خانوادگی"
            ]
            # انتخاب ستون‌های موجود
            final_cols = [col for col in desired_columns if col in df_emp.columns]
            
            # ساخت df_show (این متغیر اینجا ساخته می‌شود)
            if final_cols:
                df_show = df_emp[final_cols]
            else:
                df_show = df_emp
            
            # 5. نمایش جدول (حتما داخل if باشد تا df_show شناخته شود)
            st.dataframe(
                style_dataframe(df_show),  # ✅ اعمال استایل آبی
                use_container_width=True,
                height=500,
                hide_index=True
            )
        
        else:
            # اگر داده نبود، این پیام نمایش داده می‌شود
            st.warning("هنوز داده‌ای بارگذاری نشده است. لطفاً دکمه بارگذاری را بزنید.")
 # ---------------------------------------------------------
    # بخش 5: گزارش ماهانه (اصلاح نهایی: استایل آبی + ترتیب ستون‌ها)
    # ---------------------------------------------------------
    elif st.session_state.hr_active_tab == "گزارش ماهانه":
        ensure_data_loaded("monthly")
        
        # تیتر
        st.markdown("""
            <div style="margin-top: -500px !important; padding-bottom: 10px !important;">
                <h3 style="color: #033270; font-family: 'B Nazanin'; font-size: 2rem;">
                    📊 گزارش ماهانه
                </h3>
            </div>
        """, unsafe_allow_html=True)

        if st.session_state.monthlylist_data is not None:
            df = st.session_state.monthlylist_data.copy()
            
            # 1. تمیزکاری نام ستون‌ها
            df.columns = [str(col).strip().replace('ي', 'ی').replace('ك', 'ک') for col in df.columns]

            # 2. تمیزکاری مقادیر سلول‌ها
            def clean_all_values(val):
                if pd.isna(val): return val
                val = str(val).strip().replace('ي', 'ی').replace('ك', 'ک')
                if val == "ابان": return "آبان"
                if val == "اذر": return "آذر"
                return val

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
                    default_index = len(sorted_months)

            # 3. فیلترها
            st.markdown("""
                <div style="margin-bottom: 10px; margin-top: 40px;"> <span style="
                        font-family: 'B Nazanin', Tahoma, sans-serif !important;
                        font-size: 1.1rem;
                        font-weight: bold;
                        color: #033270;
                        border-bottom: 2px solid #eee;
                        padding-bottom: 5px;
                        display: inline-block;
                        width: 100%;
                    ">
                        🔍 فیلترها
                    </span>
                </div>
            """, unsafe_allow_html=True)
            
            col_filter1, col_filter2, col_filter3, col_filter4 = st.columns(4, gap="small")
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
            
            # =========================================================
            # ✅✅✅ اعمال ترتیب ستون‌ها قبل از نمایش
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
            
            # فقط ستون‌هایی که وجود دارند را انتخاب می‌کنیم
            final_cols = [col for col in target_columns if col in df_show.columns]
            
            if final_cols:
                df_show = df_show[final_cols]


            st.markdown(f"##### تعداد رکورد: {len(df_show)}")
            # 5. نمایش جدول (با استایل آبی و ستون‌های مرتب شده)
            st.dataframe(
                style_dataframe(df_show), 
                use_container_width=True,
                height=500,
                hide_index=True
            )


        else:
            st.info("👈 دکمه دریافت اطلاعات را بزنید.")
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