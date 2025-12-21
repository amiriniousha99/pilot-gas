import hashlib
import streamlit as st

# لیست کاربران با نام فارسی و دسترسی‌ها
USERS = {
    "admin": {
        "password": hashlib.sha256("admin".encode()).hexdigest(),
        "role": "admin",
        "full_name": "مدیر سیستم",
        "access": ["hr", "production", "sales", "warehouse", "after_sales", "management"]
    },
    "manager": {
        "password": hashlib.sha256("manager".encode()).hexdigest(),
        "role": "manager",
        "full_name": "مدیر فروش",
        "access": ["sales", "warehouse", "after_sales", "management"]
    },
    "viewer": {
        "password": hashlib.sha256("viewer".encode()).hexdigest(),
        "role": "viewer",
        "full_name": "کاربر مشاهده‌گر",
        "access": ["sales", "warehouse"]
    },
    "hr_manager": {
        "password": hashlib.sha256("hr123".encode()).hexdigest(),
        "role": "hr_manager",
        "full_name": "مدیر منابع انسانی",
        "access": ["hr", "management"]
    },
    "production_manager": {
        "password": hashlib.sha256("prod123".encode()).hexdigest(),
        "role": "production_manager",
        "full_name": "مدیر تولید",
        "access": ["production", "warehouse", "management"]
    },
    "sales_manager": {
        "password": hashlib.sha256("sales123".encode()).hexdigest(),
        "role": "sales_manager",
        "full_name": "مدیر فروش",
        "access": ["sales", "warehouse", "after_sales"]
    },
    "warehouse_manager": {
        "password": hashlib.sha256("warehouse123".encode()).hexdigest(),
        "role": "warehouse_manager",
        "full_name": "مدیر انبار",
        "access": ["warehouse", "production"]
    },
    "after_sales_manager": {
        "password": hashlib.sha256("after123".encode()).hexdigest(),
        "role": "after_sales_manager",
        "full_name": "مدیر خدمات پس از فروش",
        "access": ["after_sales", "sales"]
    },
    "accountant": {
        "password": hashlib.sha256("acc123".encode()).hexdigest(),
        "role": "accountant",
        "full_name": "حسابدار",
        "access": ["management", "sales"]
    },
    "operator": {
        "password": hashlib.sha256("op123".encode()).hexdigest(),
        "role": "operator",
        "full_name": "اپراتور",
        "access": ["production", "warehouse"]
    }
}

def authenticate_user(username, password):
    """بررسی صحت نام کاربری و رمز عبور"""
    if username in USERS:
        hashed_input = hashlib.sha256(password.encode()).hexdigest()
        if USERS[username]["password"] == hashed_input:
            return USERS[username]
    return None

def has_access(page_key):
    """بررسی دسترسی کاربر به صفحه"""
    if 'user_info' in st.session_state and st.session_state.user_info:
        return page_key in st.session_state.user_info.get('access', [])
    return False