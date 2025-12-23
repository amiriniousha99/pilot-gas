import streamlit as st
from datetime import datetime
import jdatetime

def load_login_css():
    """استایل‌های مخصوص صفحه ورود"""
    st.markdown("""
    <style>
        /* لود کردن فونت بی نازنین از سرور */
        @import url('https://cdn.jsdelivr.net/gh/rastikerdar/b-nazanin-font/dist/font-face.css');

        /* اعمال روی کل صفحه */
        html, body, .stApp {
            font-family: 'B Nazanin', Tahoma, sans-serif !important;
        }
        
        /* اعمال روی تمام متون، دکمه‌ها و ورودی‌ها */
        * {
            font-family: 'B Nazanin', Tahoma, sans-serif !important;
        }

        header[data-testid="stHeader"] {
            display: none;
        }
        
        .block-container {
            padding-top: 0;
            padding-bottom: 0;
            max-width: 100%;
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        
        [data-testid="InputInstructions"] {
            display: none !important;
        }
        
        [data-testid="stForm"] {
            background-color: #033270;
            padding: 3rem;
            border-radius: 20px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.3);
            border: none;
            width: 100%;
            max-width: 400px;
            margin: auto;
        }
        
        [data-testid="stForm"] h2 {
            color: white;
            text-align: center;
            font-size: 2rem;
            margin-right: 2rem;
            margin-bottom: 1.5rem;
            font-weight: 700;
        }
        
        .stTextInput label {
            color: white !important;
            margin-bottom: 8px;
            font-size: 1rem;
        }
        
        .stTextInput input {
            color: #333;
            background-color: white;
            border-radius: 8px;
            padding: 10px;
            text-align: center;
            font-size: 1.1rem;
        }
        
        [data-testid="stFormSubmitButton"] button {
            background-color: #2ecc71;
            color: white;
            border: none;
            padding: 10px 0;
            margin-top: 15px;
            font-size: 1.2rem;
            border-radius: 8px;
            width: 100%;
            transition: 0.3s;
        }
        
        [data-testid="stFormSubmitButton"] button:hover {
            background-color: #27ae60;
            box-shadow: 0 5px 15px rgba(46, 204, 113, 0.4);
        }
    </style>
    """, unsafe_allow_html=True)

def load_dashboard_css():
    """استایل‌های مخصوص صفحات داخلی (داشبورد)"""
    st.markdown("""
    <style>
        @import url('https://cdn.jsdelivr.net/gh/rastikerdar/b-nazanin-font/dist/font-face.css');
        @import url('https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css');

        html, body, .stApp {
        /* B Nazanin اضافه شد */
        font-family: 'B Nazanin', 'Vazirmatn', sans-serif !important; 
        direction: rtl;
        text-align: right;
        background-color: #ffffff;
        overflow: auto;
        color: #000000;
    }

        p, span, div, label {
            color: #000000;
        }
        
        h1, h2, h3, h4, h5, h6 {
            color: #000000;
            text-align: right;
            direction: rtl;
        }
        
        h1 {
            margin-top: 5px;
            padding-top: 5px;
            margin-bottom: 10px;
        }
        
        h2, h3, h4, h5, h6 {
            margin-top: 10px;
            padding-top: 5px;
        }

        .stMarkdown, .stText {
            color: #000000;
            text-align: right;
        }

        header[data-testid="stHeader"] {
            display: none;
        }

        .block-container {
            padding-top: 90px !important;
            padding-bottom: 2rem !important;
            max-width: 100% !important;
            padding-left: 2rem !important;
            padding-right: 2rem !important;
        }

        .custom-navbar {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 50px;
            background: linear-gradient(135deg, #033270 0%, #0455a8 100%);
            z-index: 999999;
            display: flex;
            align-items: center;
            justify-content: flex-start;
            padding: 0 80px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
        }

        .nav-right {
            display: flex;
            gap: 8px;
            align-items: center;
            flex-direction: row;
            width: 100%;
            justify-content: space-between;
        }
        
        .nav-items-left {
            display: flex;
            gap: 8px;
            align-items: center;
        }
        
        .nav-items-right {
            display: flex;
            gap: 8px;
            align-items: center;
        }

        .nav-item, .logout-item {
            color: white !important;
            padding: 8px 18px;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s ease;
            font-size: 0.95rem;
            font-weight: 500;
            text-decoration: none !important;
            background: transparent;
            white-space: nowrap;
            display: inline-block;
            border: 2px solid transparent;
        }
        
        .nav-item.disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .nav-item:hover:not(.disabled) {
            background: rgba(255,255,255,0.15);
            border: 2px solid rgba(255,255,255,0.3);
        }

        .nav-item.active {
            background: rgba(46,204,113,0.3);
            border: 2px solid #2ecc71;
        }

        .logout-item {
            background: rgba(231, 76, 60, 0.3);
            border: 2px solid rgba(231, 76, 60, 0.5);
        }

        .logout-item:hover {
            background: rgba(231, 76, 60, 0.5);
            border: 2px solid rgba(231, 76, 60, 0.8);
        }

        pre, code {
            display: none !important;
        }
        
        [data-testid="stCode"] {
            display: none !important;
        }

        .stButton button {
            background-color: #014fb5;
            color: white;
            border: none;
            border-radius: 8px;
            padding: 8px 20px;
            font-size: 0.9rem;
            transition: all 0.3s;
        }

        .stButton button:hover {
            background-color: #0455a8;
            box-shadow: 0 4px 12px rgba(3,50,112,0.3);
        }

        .dashboard-card {
            background: white;
            padding: 25px;
            border-radius: 12px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.08);
            margin-bottom: 20px;
            transition: transform 0.3s;
        }

        .dashboard-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.12);
        }

       /* ------------------------------------------------------- */
        /* استایل جدول (فقط تنظیم فونت - رنگ را به پایتون می‌سپاریم) */
        /* ------------------------------------------------------- */
        div[data-testid="stDataFrame"] {
            width: 100%;
            font-family: 'B Nazanin', Tahoma, sans-serif !important;
        }

        /* اجبار فونت روی هدر و سلول‌ها */
        div[data-testid="stDataFrame"] * {
            font-family: 'B Nazanin', Tahoma, sans-serif !important;
        }
        
        /* حذف بوردر پیش‌فرض */
        div[data-testid="stDataFrame"] > div {
            border: none !important;
        }
        
        div[data-testid="stElementToolbar"] {
            display: block !important;
            visibility: visible !important;
            opacity: 1 !important;
            background-color: #033270 !important;
            border-radius: 5px;
            padding: 4px;
        }
        
        div[data-testid="stElementToolbar"] button {
            color: white !important;
            background-color: transparent !important;
        }
        
        div[data-testid="stElementToolbar"] button:hover {
            background-color: rgba(255,255,255,0.1) !important;
        }

        div[data-testid="stElementToolbar"] button:nth-child(1),
        div[data-testid="stElementToolbar"] button:nth-child(2) {
            display: none !important;
        }
        
        div[data-testid="stElementToolbar"] button:nth-child(3) {
            display: block !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }

        .stTabs [data-baseweb="tab"] {
            background-color: #f0f0f0;
            border-radius: 8px 8px 0 0;
            padding: 10px 20px;
            color: #333;
        }
        /* 1. تب انتخاب شده (Selected): سرمه‌ای با متن سفید */
        .stTabs [aria-selected="true"] {
            background-color: #033270 !important;
            border-radius: 8px 8px 0 0 !important;
            border: none !important;
            box-shadow: 0 -2px 5px rgba(0,0,0,0.1);
        }
        /* سفید کردن متن داخل تب انتخاب شده */
        .stTabs [aria-selected="true"] p {
            color: #ffffff !important;
            font-weight: 900 !important;
        }

        /* 2. تب انتخاب نشده (Unselected): آبی روشن با متن سرمه‌ای */
        .stTabs [aria-selected="false"] {
            background-color: #E3F2FD !important; /* همان رنگ دکمه‌های ثانویه */
            border-radius: 8px 8px 0 0 !important;
            border: 1px solid #E2E8F0 !important;
            border-bottom: none !important;
            margin-left: 2px !important; /* فاصله ریز بین تب‌ها */
            transition: all 0.3s ease;
        }
        /* سرمه‌ای کردن متن داخل تب انتخاب نشده */
        .stTabs [aria-selected="false"] p {
            color: #033270 !important;
            font-weight: 600 !important;
        }

        /* 3. هاور روی تب انتخاب نشده (وقتی موس میره روش) */
        .stTabs [aria-selected="false"]:hover {
            background-color: #BFDBFE !important; /* آبی کمی تیره‌تر */
            color: #033270 !important;
        }
        .stTabs [aria-selected="false"]:hover p {
            color: #033270 !important;
        }
        
        /* حذف خط قرمز پیش‌فرض بالای تب‌های استریم‌لیت */
        .stTabs [data-baseweb="tab-highlight"] {
            background-color: transparent !important;
        }
        /* کاهش ارتفاع کارت‌های استخدام - با فونت درشت‌تر */
        .stat-card {
            padding: 15px !important;
            min-height: auto !important;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            border-radius: 12px;
            color: white;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
            transition: all 0.3s;
            text-align: center;
        }
        
        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(0,0,0,0.15);
        }
        
        /* عنوان کارت */
        .stat-card h3 {
            color: white !important;
            font-size: 1.1rem !important; /* افزایش سایز فونت عنوان */
            margin-bottom: 8px !important;
            font-weight: 700 !important;
        }
        
        /* عدد اصلی وسط کارت */
        .stat-card .stat-number {
            font-size: 2.2rem !important; /* افزایش سایز فونت عدد */
            font-weight: 800;
            margin: 8px 0 !important;
            line-height: 1.2 !important;
        }
        
        /* متن توضیحات پایین کارت */
        .stat-card .stat-label {
            color: #212529 !important; /* سفید یخی */
            font-size: 0.95rem !important; /* افزایش سایز فونت توضیحات */
            opacity: 1;
            font-weight: 500;
        }
        
        /* استایل فیلترهای پرسنل - باکس‌های نام خانوادگی و شماره پرسنلی */
        .stTextInput input {
            background-color: #ffffff !important;
            color: #212529 !important;
            border: 1px solid #ced4da !important;
            border-radius: 6px !important;
            padding: 8px 12px !important;
            font-size: 0.9rem !important;
            text-align: right !important;
        }
        
        .stTextInput input:focus {
            background-color: #ffffff !important;
            border-color: #033270 !important;
            outline: none !important;
            box-shadow: 0 0 0 0.2rem rgba(3, 50, 112, 0.15) !important;
        }
        
        .stTextInput input::placeholder {
            color: transparent !important;
        }
        
        .stTextInput label {
            color: #212529 !important;
            font-weight: 500 !important;
            font-size: 0.9rem !important;
            margin-bottom: 5px !important;
        }
        
        /* حذف پیام "Press Enter to apply" */
        [data-testid="InputInstructions"] {
            display: none !important;
        }
        
        /* استایل فیلترهای لیستی (واحد و زیرگروه) */
        .stSelectbox > div > div {
            background-color: #f8f9fa !important;
            color: #212529 !important;
            border: 1px solid #ced4da !important;
            border-radius: 6px !important;
            /* کاهش پدینگ برای نمایش متن بیشتر */
            padding: 0px 8px !important; 
            /* تنظیم ارتفاع ثابت برای هماهنگی با اینپوت‌های کناری */
            min-height: 42px !important; 
            display: flex !important;
            align-items: center !important;
        }
        
        /* تنظیم فونت و جلوگیری از شکستن متن */
        .stSelectbox [data-baseweb="select"] div {
            font-size: 0.8rem !important; /* فونت کمی ریزتر برای جا شدن متن طولانی */
            font-weight: 500 !important;
            white-space: nowrap !important;
            overflow: hidden !important;
            text-overflow: ellipsis !important;
            padding-left: 20px !important; /* جلوگیری از رفتن متن زیر فلش سمت چپ */
        }

        .stSelectbox label {
            color: #212529 !important;
            font-weight: 500 !important;
            font-size: 0.9rem !important;
            margin-bottom: 5px !important;
        }
        /* استایل منوی باز شده selectbox */
        [data-baseweb="popover"] {
            background-color: #f8f9fa !important;
        }
        
        [role="listbox"] {
            background-color: #f8f9fa !important;
            border: 1px solid #ced4da !important;
            border-radius: 6px !important;
        }
        
        [role="option"] {
            background-color: #f8f9fa !important;
            color: #212529 !important;
            padding: 10px 15px !important;
            font-size: 0.9rem !important;
        }
        
        [role="option"]:hover {
            background-color: #e9ecef !important;
            color: #033270 !important;
        }
        
        [role="option"][aria-selected="true"] {
            background-color: #dee2e6 !important;
            color: #033270 !important;
            font-weight: 600 !important;
        }
    </style>
    """, unsafe_allow_html=True)

def show_custom_navbar(current_page="home"):
    """نمایش نوار ناوبری سفارشی"""
    
    user_info = st.session_state.get('user_info', {})
    user_access = user_info.get('access', [])
    current_user = st.query_params.get("user", "")
    
    all_menus = [
        {'key': 'home', 'label': '🏠 خانه', 'access': True},
        {'key': 'hr', 'label': '👥 منابع انسانی', 'access': 'hr' in user_access},
        {'key': 'production', 'label': '🏭 تولید', 'access': 'production' in user_access},
        {'key': 'sales', 'label': '💰 فروش', 'access': 'sales' in user_access},
        {'key': 'warehouse', 'label': '📦 انبار', 'access': 'warehouse' in user_access},
        {'key': 'after_sales', 'label': '🛠️ خدمات پس از فروش', 'access': 'after_sales' in user_access},
        {'key': 'management', 'label': '💼 مدیریت', 'access': 'management' in user_access}
    ]
    
    menu_html_left = ""
    for menu in all_menus:
        active_class = 'active' if current_page == menu['key'] else ''
        disabled_class = '' if menu['access'] else 'disabled'
        menu_html_left += f'<a class="nav-item {active_class} {disabled_class}" href="?user={current_user}&page={menu["key"]}">{menu["label"]}</a>'
    
    menu_html_right = f'<a class="logout-item" href="?user={current_user}&action=logout"><i class="fas fa-sign-out-alt"></i> خروج</a>'
    
    st.markdown(f"""
    <div class="custom-navbar">
        <div class="nav-right">
            <div class="nav-items-left">
                {menu_html_left}
            </div>
            <div class="nav-items-right">
                {menu_html_right}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)