import streamlit as st
import pandas as pd
import psycopg2
import hashlib
import os
import calendar
import matplotlib.pyplot as plt
from datetime import date, datetime, timedelta
from pathlib import Path
ok, err = test_db_connection()
if ok:
    st.success("✅ Supabase 連線成功")
else:
    st.error("❌ Supabase 連線失敗")
    st.code(err)
    st.stop()
# ============================================================
# 基本設定
# ============================================================
DB_FILE = "expense_tracker_v2.db"

st.set_page_config(
    page_title="我的記帳 App",
    page_icon="💰",
    layout="wide"
)

st.markdown("""
<style>
@media (max-width: 768px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 1rem;
    }

    div[data-testid="stMetric"] {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 12px;
        border-radius: 16px;
    }

    button {
        width: 100%;
    }
}
</style>
""", unsafe_allow_html=True)


# ============================================================
# 分類、帳戶、Icon
# ============================================================
EXPENSE_CATEGORIES = [
    "餐飲", "交通", "娛樂", "購物", "居家", "醫療",
    "學習", "訂閱", "保險", "房租", "信用卡費", "其他"
]

INCOME_CATEGORIES = [
    "薪資", "獎金", "投資", "副業", "退款", "其他收入"
]

ACCOUNTS = [
    "現金", "銀行", "信用卡", "悠遊卡", "電子錢包"
]

CATEGORY_ICONS = {
    "餐飲": "🍔",
    "交通": "🚇",
    "娛樂": "🎬",
    "購物": "🛒",
    "居家": "🏠",
    "醫療": "🏥",
    "學習": "📚",
    "訂閱": "📺",
    "保險": "🛡️",
    "房租": "🏘️",
    "信用卡費": "💳",
    "其他": "📦",
    "薪資": "💼",
    "獎金": "🎁",
    "投資": "📈",
    "副業": "🧰",
    "退款": "↩️",
    "其他收入": "💰",
}


# ============================================================
# 資料庫：Supabase PostgreSQL
# ============================================================

# 保留這個名稱只是避免後面資料管理區塊引用 DB_FILE 時出錯。
# 這一版實際資料庫已經改用 Supabase，不再使用本機 .db 檔案。
DB_FILE = "Supabase PostgreSQL"


class PgCursorWrapper:
    """
    讓原本 SQLite 的 ? placeholder 可以繼續使用。
    PostgreSQL / psycopg2 原本需要 %s，這裡自動轉換。
    這樣就不用把整份程式所有 SQL 都重寫。
    """
    def __init__(self, cursor):
        self.cursor = cursor

    def execute(self, query, params=None):
        query = query.replace("?", "%s")
        return self.cursor.execute(query, params or ())

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    def close(self):
        return self.cursor.close()

    @property
    def description(self):
        return self.cursor.description

    def __iter__(self):
        return iter(self.cursor)


class PgConnectionWrapper:
    """
    包裝 psycopg2 connection，讓 pandas.read_sql_query
    和原本 conn.cursor() / conn.commit() / conn.close() 的寫法可繼續使用。
    """
    def __init__(self, connection):
        self.connection = connection

    def cursor(self):
        return PgCursorWrapper(self.connection.cursor())

    def commit(self):
        return self.connection.commit()

    def rollback(self):
        return self.connection.rollback()

    def close(self):
        return self.connection.close()


def get_connection():
    if "SUPABASE_DB_URL" not in st.secrets:
        st.error("找不到 SUPABASE_DB_URL，請到 Streamlit Cloud 的 Secrets 設定 Supabase 連線字串。")
        st.stop()

    conn = psycopg2.connect(st.secrets["SUPABASE_DB_URL"])
    return PgConnectionWrapper(conn)


#def init_db():
    conn = get_connection()
    def test_db_connection():
    try:
        conn = psycopg2.connect(
            st.secrets["SUPABASE_DB_URL"],
            connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute("SELECT 1;")
        cur.fetchone()
        cur.close()
        conn.close()
        return True, None
    except Exception as e:
        return False, str(e)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            account TEXT NOT NULL,
            amount NUMERIC NOT NULL,
            note TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            month TEXT NOT NULL,
            budget NUMERIC NOT NULL,
            UNIQUE(user_id, month)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            account TEXT NOT NULL,
            amount NUMERIC NOT NULL,
            day INTEGER NOT NULL,
            note TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account_balances (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            account TEXT NOT NULL,
            initial_balance NUMERIC NOT NULL,
            UNIQUE(user_id, account)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS credit_cards (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            card_name TEXT NOT NULL,
            closing_day INTEGER NOT NULL,
            payment_day INTEGER NOT NULL,
            UNIQUE(user_id, card_name)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_rules (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            keyword TEXT NOT NULL,
            transaction_type TEXT NOT NULL,
            category TEXT NOT NULL,
            account TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saved_items (
            id BIGSERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            account TEXT NOT NULL,
            icon TEXT NOT NULL,
            last_used TEXT NOT NULL,
            UNIQUE(user_id, type, title)
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ============================================================
# 密碼與登入
# ============================================================
def hash_password(password, salt=None):
    if salt is None:
        salt = os.urandom(16).hex()

    password_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return salt, password_hash


def create_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()

    salt, password_hash = hash_password(password)

    try:
        cursor.execute("""
            INSERT INTO users (username, salt, password_hash, created_at)
            VALUES (?, ?, ?, ?)
        """, (
            username,
            salt,
            password_hash,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))

        conn.commit()
        return True, "帳號建立成功"
    except psycopg2.IntegrityError:
        return False, "帳號已存在"
    finally:
        conn.close()


def verify_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, salt, password_hash
        FROM users
        WHERE username = ?
    """, (username,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    user_id, salt, stored_hash = row
    _, input_hash = hash_password(password, salt)

    if input_hash == stored_hash:
        return user_id

    return None


def login_page():
    st.title("💰 我的記帳 App")
    st.caption("請先登入或建立帳號")

    tab_login, tab_register = st.tabs(["登入", "建立帳號"])

    with tab_login:
        username = st.text_input("帳號", key="login_username")
        password = st.text_input("密碼", type="password", key="login_password")

        if st.button("登入"):
            user_id = verify_user(username.strip(), password)

            if user_id:
                st.session_state["user_id"] = user_id
                st.session_state["username"] = username.strip()
                st.success("登入成功")
                st.rerun()
            else:
                st.error("帳號或密碼錯誤")

    with tab_register:
        new_username = st.text_input("新帳號", key="register_username")
        new_password = st.text_input("新密碼", type="password", key="register_password")
        confirm_password = st.text_input("確認密碼", type="password", key="confirm_password")

        if st.button("建立帳號"):
            if not new_username.strip():
                st.error("請輸入帳號")
            elif len(new_password) < 4:
                st.error("密碼至少需要 4 個字元")
            elif new_password != confirm_password:
                st.error("兩次密碼不一致")
            else:
                success, message = create_user(new_username.strip(), new_password)
                if success:
                    st.success(message)
                else:
                    st.error(message)


if "user_id" not in st.session_state:
    login_page()
    st.stop()

USER_ID = st.session_state["user_id"]
USERNAME = st.session_state["username"]


# ============================================================
# 交易 CRUD
# ============================================================
def add_transaction(user_id, transaction_date, transaction_type, title, category, account, amount, note):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO transactions (user_id, date, type, title, category, account, amount, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        transaction_date,
        transaction_type,
        title,
        category,
        account,
        amount,
        note
    ))

    conn.commit()
    conn.close()


def update_transaction(user_id, transaction_id, transaction_date, transaction_type, title, category, account, amount, note):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE transactions
        SET date = ?, type = ?, title = ?, category = ?, account = ?, amount = ?, note = ?
        WHERE id = ? AND user_id = ?
    """, (
        transaction_date,
        transaction_type,
        title,
        category,
        account,
        amount,
        note,
        transaction_id,
        user_id
    ))

    conn.commit()
    conn.close()


def delete_transaction(user_id, transaction_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM transactions
        WHERE id = ? AND user_id = ?
    """, (transaction_id, user_id))

    conn.commit()
    conn.close()


def delete_all_transactions(user_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM transactions WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()


def load_transactions(user_id):
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT
            id,
            date AS 日期,
            type AS 類型,
            title AS 項目,
            category AS 分類,
            account AS 帳戶,
            amount AS 金額,
            note AS 備註
        FROM transactions
        WHERE user_id = ?
        ORDER BY date DESC, id DESC
    """, conn, params=(user_id,))

    conn.close()
    return df


# ============================================================
# 項目名稱選單：A / B / C
# A：收入支出分開
# B：icon
# C：最近使用排序
# ============================================================
def upsert_saved_item(user_id, transaction_type, title, category, account):
    icon = CATEGORY_ICONS.get(category, "📦")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO saved_items (
            user_id, type, title, category, account, icon, last_used
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, type, title)
        DO UPDATE SET
            category = excluded.category,
            account = excluded.account,
            icon = excluded.icon,
            last_used = excluded.last_used
    """, (
        user_id,
        transaction_type,
        title,
        category,
        account,
        icon,
        now
    ))

    conn.commit()
    conn.close()


def load_saved_items(user_id, transaction_type):
    conn = get_connection()

    saved_df = pd.read_sql_query("""
        SELECT
            title,
            category,
            account,
            icon,
            last_used
        FROM saved_items
        WHERE user_id = ? AND type = ?
    """, conn, params=(user_id, transaction_type))

    tx_df = pd.read_sql_query("""
        SELECT
            title,
            category,
            account,
            MAX(date) AS last_used
        FROM transactions
        WHERE user_id = ? AND type = ?
        GROUP BY title
    """, conn, params=(user_id, transaction_type))

    conn.close()

    items = {}

    for _, row in tx_df.iterrows():
        title = str(row["title"])
        category = str(row["category"])
        account = str(row["account"])
        items[title] = {
            "title": title,
            "category": category,
            "account": account,
            "icon": CATEGORY_ICONS.get(category, "📦"),
            "last_used": str(row["last_used"])
        }

    for _, row in saved_df.iterrows():
        title = str(row["title"])
        items[title] = {
            "title": title,
            "category": str(row["category"]),
            "account": str(row["account"]),
            "icon": str(row["icon"]),
            "last_used": str(row["last_used"])
        }

    result = list(items.values())
    result.sort(key=lambda x: x["last_used"], reverse=True)

    return result


# ============================================================
# 預算
# ============================================================
def set_budget(user_id, month, budget):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO budgets (user_id, month, budget)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, month) DO UPDATE SET budget = excluded.budget
    """, (user_id, month, budget))

    conn.commit()
    conn.close()


def get_budget(user_id, month):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT budget
        FROM budgets
        WHERE user_id = ? AND month = ?
    """, (user_id, month))

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else 0


def load_budgets(user_id):
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT month AS 月份, budget AS 預算
        FROM budgets
        WHERE user_id = ?
        ORDER BY month DESC
    """, conn, params=(user_id,))

    conn.close()
    return df


# ============================================================
# 帳戶初始餘額
# ============================================================
def set_account_balance(user_id, account, initial_balance):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO account_balances (user_id, account, initial_balance)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, account) DO UPDATE SET initial_balance = excluded.initial_balance
    """, (user_id, account, initial_balance))

    conn.commit()
    conn.close()


def load_account_balances(user_id):
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT account AS 帳戶, initial_balance AS 初始餘額
        FROM account_balances
        WHERE user_id = ?
        ORDER BY account
    """, conn, params=(user_id,))

    conn.close()
    return df


# ============================================================
# 信用卡
# ============================================================
def set_credit_card(user_id, card_name, closing_day, payment_day):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO credit_cards (user_id, card_name, closing_day, payment_day)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, card_name)
        DO UPDATE SET closing_day = excluded.closing_day, payment_day = excluded.payment_day
    """, (user_id, card_name, closing_day, payment_day))

    conn.commit()
    conn.close()


def load_credit_cards(user_id):
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT
            card_name AS 卡片名稱,
            closing_day AS 結帳日,
            payment_day AS 繳款日
        FROM credit_cards
        WHERE user_id = ?
        ORDER BY card_name
    """, conn, params=(user_id,))

    conn.close()
    return df


def safe_date(year, month, day):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def add_months(year, month, delta):
    month_index = month - 1 + delta
    new_year = year + month_index // 12
    new_month = month_index % 12 + 1
    return new_year, new_month


def get_credit_card_period(today, closing_day):
    if today.day <= closing_day:
        current_close = safe_date(today.year, today.month, closing_day)
        prev_year, prev_month = add_months(today.year, today.month, -1)
        prev_close = safe_date(prev_year, prev_month, closing_day)

        start_date = prev_close + timedelta(days=1)
        end_date = current_close
    else:
        current_close = safe_date(today.year, today.month, closing_day)
        next_year, next_month = add_months(today.year, today.month, 1)
        next_close = safe_date(next_year, next_month, closing_day)

        start_date = current_close + timedelta(days=1)
        end_date = next_close

    return start_date, end_date


# ============================================================
# 固定支出
# ============================================================
def add_recurring_expense(user_id, title, category, account, amount, day, note):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO recurring_expenses (user_id, title, category, account, amount, day, note)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        title,
        category,
        account,
        amount,
        day,
        note
    ))

    conn.commit()
    conn.close()


def load_recurring_expenses(user_id):
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT
            id,
            title AS 項目,
            category AS 分類,
            account AS 帳戶,
            amount AS 金額,
            day AS 每月日期,
            note AS 備註
        FROM recurring_expenses
        WHERE user_id = ?
        ORDER BY day ASC, id DESC
    """, conn, params=(user_id,))

    conn.close()
    return df


def delete_recurring_expense(user_id, recurring_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM recurring_expenses
        WHERE id = ? AND user_id = ?
    """, (recurring_id, user_id))

    conn.commit()
    conn.close()


# ============================================================
# 自動分類規則
# ============================================================
def add_category_rule(user_id, keyword, transaction_type, category, account):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO category_rules (user_id, keyword, transaction_type, category, account)
        VALUES (?, ?, ?, ?, ?)
    """, (
        user_id,
        keyword,
        transaction_type,
        category,
        account
    ))

    conn.commit()
    conn.close()


def load_category_rules(user_id):
    conn = get_connection()

    df = pd.read_sql_query("""
        SELECT
            id,
            keyword AS 關鍵字,
            transaction_type AS 類型,
            category AS 分類,
            account AS 帳戶
        FROM category_rules
        WHERE user_id = ?
        ORDER BY id DESC
    """, conn, params=(user_id,))

    conn.close()
    return df


def delete_category_rule(user_id, rule_id):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM category_rules
        WHERE id = ? AND user_id = ?
    """, (rule_id, user_id))

    conn.commit()
    conn.close()


def match_category_rule(user_id, title, transaction_type):
    rules_df = load_category_rules(user_id)

    if rules_df.empty:
        return None

    title_lower = title.lower()

    for _, row in rules_df.iterrows():
        keyword = str(row["關鍵字"]).lower()

        if row["類型"] == transaction_type and keyword in title_lower:
            return {
                "category": row["分類"],
                "account": row["帳戶"]
            }

    return None


# ============================================================
# 頁首
# ============================================================
st.title("💰 我的記帳 App")
st.caption("Python + Streamlit + Supabase 製作的個人記帳工具")

top_col1, top_col2 = st.columns([4, 1])

with top_col1:
    st.write(f"目前登入：**{USERNAME}**")

with top_col2:
    if st.button("登出"):
        st.session_state.clear()
        st.rerun()


# ============================================================
# 側邊欄：新增交易
# ============================================================
with st.sidebar:
    st.header("新增交易")

    transaction_date = st.date_input("日期", value=date.today())

    transaction_type = st.radio(
        "類型",
        ["支出", "收入"],
        horizontal=True
    )

    if transaction_type == "支出":
        category_options = EXPENSE_CATEGORIES
    else:
        category_options = INCOME_CATEGORIES

    saved_items = load_saved_items(USER_ID, transaction_type)

    item_labels = ["➕ 新增項目"]
    item_map = {}

    for item in saved_items:
        label = f"{item['icon']} {item['title']}"
        item_labels.append(label)
        item_map[label] = item

    selected_item_label = st.selectbox(
        "項目名稱",
        item_labels
    )

    auto_rule = st.checkbox("套用自動分類規則", value=True)

    if selected_item_label == "➕ 新增項目":
        new_item_title = st.text_input(
            "新增項目名稱",
            placeholder="例如：午餐、捷運、Netflix、薪資"
        )

        default_category = category_options[0]
        default_account = ACCOUNTS[0]

        if new_item_title.strip() and auto_rule:
            matched = match_category_rule(USER_ID, new_item_title.strip(), transaction_type)

            if matched:
                if matched["category"] in category_options:
                    default_category = matched["category"]

                if matched["account"] in ACCOUNTS:
                    default_account = matched["account"]

                st.info(f"已套用規則：{default_category} / {default_account}")

        selected_category = st.selectbox(
            "分類",
            category_options,
            index=category_options.index(default_category)
        )

        selected_account = st.selectbox(
            "帳戶",
            ACCOUNTS,
            index=ACCOUNTS.index(default_account)
        )

        title = new_item_title.strip()
        category = selected_category
        account = selected_account

    else:
        selected_item = item_map[selected_item_label]

        title = selected_item["title"]
        default_category = selected_item["category"]
        default_account = selected_item["account"]

        if auto_rule:
            matched = match_category_rule(USER_ID, title, transaction_type)

            if matched:
                if matched["category"] in category_options:
                    default_category = matched["category"]

                if matched["account"] in ACCOUNTS:
                    default_account = matched["account"]

                st.info(f"已套用規則：{default_category} / {default_account}")

        category_index = category_options.index(default_category) if default_category in category_options else 0
        account_index = ACCOUNTS.index(default_account) if default_account in ACCOUNTS else 0

        category = st.selectbox(
            "分類",
            category_options,
            index=category_index
        )

        account = st.selectbox(
            "帳戶",
            ACCOUNTS,
            index=account_index
        )

    st.markdown("**金額**")

    # 初始化金額
    if "add_amount" not in st.session_state:
        st.session_state["add_amount"] = 0

    # 如果上一輪要求清空金額，必須在 number_input 建立前清空
    if st.session_state.get("reset_add_amount_next_run", False):
        st.session_state["add_amount"] = 0
        st.session_state["reset_add_amount_next_run"] = False

    # 金額快速鍵
    col_a, col_b, col_c, col_d = st.columns(4)

    if col_a.button("+50"):
        st.session_state["add_amount"] += 50
        st.rerun()

    if col_b.button("+100"):
        st.session_state["add_amount"] += 100
        st.rerun()

    if col_c.button("+500"):
        st.session_state["add_amount"] += 500
        st.rerun()

    if col_d.button("+1000"):
        st.session_state["add_amount"] += 1000
        st.rerun()

    amount = st.number_input(
        "輸入金額",
        min_value=0,
        step=10,
        format="%d",
        key="add_amount"
    )

    note = st.text_area("備註", placeholder="可選填")

    col_submit, col_reset = st.columns(2)

    with col_submit:
        add_button = st.button("新增交易", use_container_width=True)

    with col_reset:
        reset_button = st.button("清除金額", use_container_width=True)

    if reset_button:
        st.session_state["reset_add_amount_next_run"] = True
        st.rerun()

    if add_button:
        if not title:
            st.error("請先選擇項目，或新增項目名稱")
        elif amount <= 0:
            st.error("金額必須大於 0")
        else:
            add_transaction(
                USER_ID,
                transaction_date.strftime("%Y-%m-%d"),
                transaction_type,
                title,
                category,
                account,
                amount,
                note.strip()
            )

            upsert_saved_item(
                USER_ID,
                transaction_type,
                title,
                category,
                account
            )

            # 不要直接改 add_amount，改成要求下一輪清空
            st.session_state["reset_add_amount_next_run"] = True

            st.success("交易已新增")
            st.rerun()


# ============================================================
# 載入資料
# ============================================================
df = load_transactions(USER_ID)

if not df.empty:
    df["日期"] = pd.to_datetime(df["日期"])
    df["月份"] = df["日期"].dt.strftime("%Y-%m")
else:
    df["月份"] = pd.Series(dtype="str")


# ============================================================
# 月份篩選
# ============================================================
st.subheader("月份篩選")

if df.empty:
    selected_month = datetime.today().strftime("%Y-%m")
    filtered_df = df.copy()
    st.info("目前還沒有交易資料。")
else:
    month_options = ["全部月份"] + sorted(df["月份"].unique().tolist(), reverse=True)

    selected_month = st.selectbox(
        "選擇月份",
        month_options
    )

    if selected_month == "全部月份":
        filtered_df = df.copy()
    else:
        filtered_df = df[df["月份"] == selected_month].copy()


# ============================================================
# 統計區
# ============================================================
if filtered_df.empty:
    total_income = 0
    total_expense = 0
else:
    total_income = filtered_df[filtered_df["類型"] == "收入"]["金額"].sum()
    total_expense = filtered_df[filtered_df["類型"] == "支出"]["金額"].sum()

balance = total_income - total_expense

budget_month = datetime.today().strftime("%Y-%m") if selected_month == "全部月份" else selected_month
monthly_budget = get_budget(USER_ID, budget_month)

if monthly_budget > 0:
    month_expense = df[(df["月份"] == budget_month) & (df["類型"] == "支出")]["金額"].sum()
    budget_used_percent = min((month_expense / monthly_budget) * 100, 999)
else:
    month_expense = 0
    budget_used_percent = 0

col1, col2, col3, col4 = st.columns(4)

col1.metric("收入", f"NT$ {total_income:,.0f}")
col2.metric("支出", f"NT$ {total_expense:,.0f}")
col3.metric("結餘", f"NT$ {balance:,.0f}")

if monthly_budget > 0:
    col4.metric(
        f"{budget_month} 預算使用",
        f"{budget_used_percent:.1f}%",
        f"預算 NT$ {monthly_budget:,.0f}"
    )
else:
    col4.metric(f"{budget_month} 預算", "尚未設定")

st.divider()


# ============================================================
# 分頁
# ============================================================
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12 = st.tabs([
    "交易紀錄",
    "分類統計",
    "趨勢圖",
    "帳戶統計",
    "初始餘額",
    "信用卡帳單",
    "預算設定",
    "固定支出",
    "自動分類",
    "編輯交易",
    "刪除交易",
    "資料管理"
])


# ============================================================
# Tab 1：交易紀錄
# ============================================================
with tab1:
    st.subheader("交易紀錄")

    if filtered_df.empty:
        st.info("目前沒有符合條件的交易。")
    else:
        search_keyword = st.text_input(
            "搜尋交易",
            placeholder="搜尋項目、分類、帳戶或備註"
        )

        display_df = filtered_df.copy()

        if search_keyword:
            keyword = search_keyword.strip()

            display_df = display_df[
                display_df["項目"].astype(str).str.contains(keyword, case=False, na=False) |
                display_df["分類"].astype(str).str.contains(keyword, case=False, na=False) |
                display_df["帳戶"].astype(str).str.contains(keyword, case=False, na=False) |
                display_df["備註"].astype(str).str.contains(keyword, case=False, na=False)
            ]

        table_df = display_df.drop(columns=["月份"])

        st.dataframe(
            table_df,
            use_container_width=True,
            hide_index=True
        )


# ============================================================
# Tab 2：分類統計
# ============================================================
with tab2:
    st.subheader("支出分類統計")

    expense_df = filtered_df[filtered_df["類型"] == "支出"].copy()

    if expense_df.empty:
        st.info("目前沒有支出資料，無法產生統計圖。")
    else:
        category_summary = (
            expense_df
            .groupby("分類", as_index=False)["金額"]
            .sum()
            .sort_values("金額", ascending=False)
        )

        col_chart1, col_chart2 = st.columns(2)

        with col_chart1:
            st.write("分類圓餅圖")

            fig, ax = plt.subplots()
            ax.pie(
                category_summary["金額"],
                labels=category_summary["分類"],
                autopct="%1.1f%%",
                startangle=90
            )
            ax.axis("equal")

            st.pyplot(fig)

        with col_chart2:
            st.write("分類金額明細")
            st.dataframe(category_summary, use_container_width=True, hide_index=True)
            st.bar_chart(category_summary, x="分類", y="金額")


# ============================================================
# Tab 3：趨勢圖
# ============================================================
with tab3:
    st.subheader("收入 / 支出趨勢圖")

    if df.empty:
        st.info("目前沒有資料，無法產生趨勢圖。")
    else:
        trend_df = df.copy()
        trend_df["月份"] = trend_df["日期"].dt.strftime("%Y-%m")

        trend_summary = (
            trend_df
            .groupby(["月份", "類型"], as_index=False)["金額"]
            .sum()
        )

        trend_pivot = trend_summary.pivot(
            index="月份",
            columns="類型",
            values="金額"
        ).fillna(0)

        for col in ["收入", "支出"]:
            if col not in trend_pivot.columns:
                trend_pivot[col] = 0

        trend_pivot["結餘"] = trend_pivot["收入"] - trend_pivot["支出"]

        st.line_chart(trend_pivot[["收入", "支出", "結餘"]])
        st.dataframe(trend_pivot.reset_index(), use_container_width=True, hide_index=True)


# ============================================================
# Tab 4：帳戶統計
# ============================================================
with tab4:
    st.subheader("帳戶統計")

    balances_df = load_account_balances(USER_ID)

    if df.empty:
        transaction_account_summary = pd.DataFrame(columns=["帳戶", "收入金額", "支出金額"])
    else:
        account_df = df.copy()
        account_df["收入金額"] = account_df.apply(
            lambda row: row["金額"] if row["類型"] == "收入" else 0,
            axis=1
        )
        account_df["支出金額"] = account_df.apply(
            lambda row: row["金額"] if row["類型"] == "支出" else 0,
            axis=1
        )

        transaction_account_summary = (
            account_df
            .groupby("帳戶", as_index=False)
            .agg({
                "收入金額": "sum",
                "支出金額": "sum"
            })
        )

    all_accounts_df = pd.DataFrame({"帳戶": ACCOUNTS})

    account_summary = all_accounts_df.merge(
        balances_df,
        on="帳戶",
        how="left"
    ).merge(
        transaction_account_summary,
        on="帳戶",
        how="left"
    )

    account_summary = account_summary.fillna(0)

    account_summary["目前估算餘額"] = (
        account_summary["初始餘額"]
        + account_summary["收入金額"]
        - account_summary["支出金額"]
    )

    st.dataframe(account_summary, use_container_width=True, hide_index=True)
    st.bar_chart(account_summary, x="帳戶", y="目前估算餘額")

    st.caption("提醒：這是根據初始餘額加上 App 內交易估算，不一定等於真實銀行餘額。")


# ============================================================
# Tab 5：初始餘額
# ============================================================
with tab5:
    st.subheader("初始帳戶餘額")

    selected_account_balance = st.selectbox("選擇帳戶", ACCOUNTS, key="balance_account")
    initial_balance = st.number_input("初始餘額", value=0.0, step=100.0)

    if st.button("儲存初始餘額"):
        set_account_balance(USER_ID, selected_account_balance, initial_balance)
        st.success("初始餘額已儲存")
        st.rerun()

    balances_df = load_account_balances(USER_ID)

    if balances_df.empty:
        st.info("尚未設定初始餘額。")
    else:
        st.dataframe(balances_df, use_container_width=True, hide_index=True)


# ============================================================
# Tab 6：信用卡帳單
# ============================================================
with tab6:
    st.subheader("信用卡帳單週期")

    with st.expander("設定信用卡"):
        card_name = st.text_input("信用卡帳戶名稱", value="信用卡")
        closing_day = st.number_input("每月結帳日", min_value=1, max_value=31, value=20, step=1)
        payment_day = st.number_input("每月繳款日", min_value=1, max_value=31, value=5, step=1)

        if st.button("儲存信用卡設定"):
            if not card_name.strip():
                st.error("請輸入信用卡帳戶名稱")
            else:
                set_credit_card(USER_ID, card_name.strip(), int(closing_day), int(payment_day))
                st.success("信用卡設定已儲存")
                st.rerun()

    cards_df = load_credit_cards(USER_ID)

    if cards_df.empty:
        st.info("尚未設定信用卡。")
    else:
        st.dataframe(cards_df, use_container_width=True, hide_index=True)

        today = date.today()

        for _, card in cards_df.iterrows():
            card_name = card["卡片名稱"]
            close_day = int(card["結帳日"])
            pay_day = int(card["繳款日"])

            period_start, period_end = get_credit_card_period(today, close_day)

            st.markdown(f"### {card_name}")
            st.write(f"本期帳單期間：**{period_start} ～ {period_end}**")
            st.write(f"繳款日：每月 **{pay_day}** 號")

            if df.empty:
                card_expenses = pd.DataFrame()
            else:
                card_expenses = df[
                    (df["類型"] == "支出") &
                    (df["帳戶"] == card_name) &
                    (df["日期"].dt.date >= period_start) &
                    (df["日期"].dt.date <= period_end)
                ].copy()

            if card_expenses.empty:
                st.info("本期沒有信用卡支出。")
            else:
                total_card_bill = card_expenses["金額"].sum()
                st.metric("本期信用卡估算帳單", f"NT$ {total_card_bill:,.0f}")
                st.dataframe(
                    card_expenses.drop(columns=["月份"]),
                    use_container_width=True,
                    hide_index=True
                )


# ============================================================
# Tab 7：預算設定
# ============================================================
with tab7:
    st.subheader("每月預算設定")

    current_month = datetime.today().strftime("%Y-%m")

    budget_input_month = st.text_input(
        "預算月份",
        value=budget_month if budget_month != "全部月份" else current_month,
        placeholder="格式：2026-05"
    )

    current_budget = get_budget(USER_ID, budget_input_month)

    budget_amount = st.number_input(
        "每月支出預算",
        min_value=0.0,
        value=float(current_budget),
        step=100.0
    )

    if st.button("儲存預算"):
        if not budget_input_month.strip():
            st.error("請輸入月份，例如：2026-05")
        else:
            set_budget(USER_ID, budget_input_month.strip(), budget_amount)
            st.success("預算已儲存")
            st.rerun()

    budgets_df = load_budgets(USER_ID)

    if budgets_df.empty:
        st.info("尚未設定任何預算。")
    else:
        st.dataframe(budgets_df, use_container_width=True, hide_index=True)


# ============================================================
# Tab 8：固定支出
# ============================================================
with tab8:
    st.subheader("固定支出提醒")

    with st.expander("新增固定支出"):
        recurring_title = st.text_input("固定支出項目", placeholder="例如：房租、保險、Netflix")
        recurring_category = st.selectbox("固定支出分類", EXPENSE_CATEGORIES, key="recurring_category")
        recurring_account = st.selectbox("付款帳戶", ACCOUNTS, key="recurring_account")
        recurring_amount = st.number_input("固定支出金額", min_value=0.0, step=10.0)
        recurring_day = st.number_input("每月幾號提醒", min_value=1, max_value=31, value=1, step=1)
        recurring_note = st.text_area("固定支出備註")

        if st.button("新增固定支出"):
            if not recurring_title.strip():
                st.error("請輸入固定支出項目")
            elif recurring_amount <= 0:
                st.error("金額必須大於 0")
            else:
                add_recurring_expense(
                    USER_ID,
                    recurring_title.strip(),
                    recurring_category,
                    recurring_account,
                    recurring_amount,
                    int(recurring_day),
                    recurring_note.strip()
                )

                upsert_saved_item(
                    USER_ID,
                    "支出",
                    recurring_title.strip(),
                    recurring_category,
                    recurring_account
                )

                st.success("固定支出已新增")
                st.rerun()

    recurring_df = load_recurring_expenses(USER_ID)

    if recurring_df.empty:
        st.info("目前沒有固定支出提醒。")
    else:
        today_day = date.today().day

        upcoming_df = recurring_df[
            (recurring_df["每月日期"] >= today_day) &
            (recurring_df["每月日期"] <= today_day + 7)
        ]

        if not upcoming_df.empty:
            st.warning("未來 7 天內有固定支出需要注意：")
            st.dataframe(upcoming_df, use_container_width=True, hide_index=True)

        st.write("所有固定支出")
        st.dataframe(recurring_df, use_container_width=True, hide_index=True)

        recurring_df["顯示名稱"] = (
            recurring_df["id"].astype(str)
            + "｜每月"
            + recurring_df["每月日期"].astype(str)
            + "號｜"
            + recurring_df["項目"]
            + "｜NT$ "
            + recurring_df["金額"].map(lambda x: f"{x:,.0f}")
        )

        selected_recurring = st.selectbox(
            "選擇要刪除的固定支出",
            recurring_df["顯示名稱"].tolist()
        )

        recurring_id = int(selected_recurring.split("｜")[0])

        if st.button("刪除固定支出"):
            delete_recurring_expense(USER_ID, recurring_id)
            st.success("固定支出已刪除")
            st.rerun()


# ============================================================
# Tab 9：自動分類規則
# ============================================================
with tab9:
    st.subheader("自動分類規則")

    st.caption("例如：關鍵字輸入 Netflix，類型選支出，分類選訂閱，帳戶選信用卡。之後新增項目名稱包含 Netflix 時會自動套用。")

    with st.expander("新增自動分類規則"):
        rule_keyword = st.text_input("關鍵字", placeholder="例如：Netflix、Uber、全聯、薪資")
        rule_type = st.radio("類型", ["支出", "收入"], horizontal=True, key="rule_type")

        if rule_type == "支出":
            rule_category_options = EXPENSE_CATEGORIES
        else:
            rule_category_options = INCOME_CATEGORIES

        rule_category = st.selectbox("分類", rule_category_options, key="rule_category")
        rule_account = st.selectbox("帳戶", ACCOUNTS, key="rule_account")

        if st.button("新增規則"):
            if not rule_keyword.strip():
                st.error("請輸入關鍵字")
            else:
                add_category_rule(
                    USER_ID,
                    rule_keyword.strip(),
                    rule_type,
                    rule_category,
                    rule_account
                )
                st.success("自動分類規則已新增")
                st.rerun()

    rules_df = load_category_rules(USER_ID)

    if rules_df.empty:
        st.info("目前沒有自動分類規則。")
    else:
        st.dataframe(rules_df, use_container_width=True, hide_index=True)

        rules_df["顯示名稱"] = (
            rules_df["id"].astype(str)
            + "｜"
            + rules_df["關鍵字"]
            + "｜"
            + rules_df["類型"]
            + "｜"
            + rules_df["分類"]
            + "｜"
            + rules_df["帳戶"]
        )

        selected_rule = st.selectbox("選擇要刪除的規則", rules_df["顯示名稱"].tolist())
        rule_id = int(selected_rule.split("｜")[0])

        if st.button("刪除規則"):
            delete_category_rule(USER_ID, rule_id)
            st.success("規則已刪除")
            st.rerun()


# ============================================================
# Tab 10：編輯交易
# ============================================================
with tab10:
    st.subheader("編輯單筆交易")

    if filtered_df.empty:
        st.info("目前沒有可編輯的交易。")
    else:
        edit_df = filtered_df.copy()

        edit_df["顯示名稱"] = (
            edit_df["id"].astype(str)
            + "｜"
            + edit_df["日期"].dt.strftime("%Y-%m-%d")
            + "｜"
            + edit_df["類型"]
            + "｜"
            + edit_df["項目"]
            + "｜NT$ "
            + edit_df["金額"].map(lambda x: f"{x:,.0f}")
        )

        selected_edit_item = st.selectbox("選擇要編輯的交易", edit_df["顯示名稱"].tolist())

        selected_id = int(selected_edit_item.split("｜")[0])
        selected_row = edit_df[edit_df["id"] == selected_id].iloc[0]

        edit_date = st.date_input("日期", value=selected_row["日期"].date(), key="edit_date")

        edit_type = st.radio(
            "類型",
            ["支出", "收入"],
            index=0 if selected_row["類型"] == "支出" else 1,
            horizontal=True,
            key="edit_type"
        )

        edit_title = st.text_input("項目名稱", value=selected_row["項目"], key="edit_title")

        edit_category_options = EXPENSE_CATEGORIES if edit_type == "支出" else INCOME_CATEGORIES
        category_index = edit_category_options.index(selected_row["分類"]) if selected_row["分類"] in edit_category_options else 0

        edit_category = st.selectbox("分類", edit_category_options, index=category_index, key="edit_category")

        account_index = ACCOUNTS.index(selected_row["帳戶"]) if selected_row["帳戶"] in ACCOUNTS else 0
        edit_account = st.selectbox("帳戶", ACCOUNTS, index=account_index, key="edit_account")

        edit_amount = st.number_input(
            "金額",
            min_value=0.0,
            value=float(selected_row["金額"]),
            step=10.0,
            format="%.0f",
            key="edit_amount"
        )

        edit_note = st.text_area(
            "備註",
            value="" if pd.isna(selected_row["備註"]) else str(selected_row["備註"]),
            key="edit_note"
        )

        if st.button("儲存修改"):
            if not edit_title.strip():
                st.error("請輸入項目名稱")
            elif edit_amount <= 0:
                st.error("金額必須大於 0")
            else:
                update_transaction(
                    USER_ID,
                    selected_id,
                    edit_date.strftime("%Y-%m-%d"),
                    edit_type,
                    edit_title.strip(),
                    edit_category,
                    edit_account,
                    edit_amount,
                    edit_note.strip()
                )

                upsert_saved_item(
                    USER_ID,
                    edit_type,
                    edit_title.strip(),
                    edit_category,
                    edit_account
                )

                st.success("交易已更新")
                st.rerun()


# ============================================================
# Tab 11：刪除交易
# ============================================================
with tab11:
    st.subheader("刪除單筆交易")

    if filtered_df.empty:
        st.info("目前沒有可刪除的交易。")
    else:
        delete_df = filtered_df.copy()

        delete_df["顯示名稱"] = (
            delete_df["id"].astype(str)
            + "｜"
            + delete_df["日期"].dt.strftime("%Y-%m-%d")
            + "｜"
            + delete_df["類型"]
            + "｜"
            + delete_df["項目"]
            + "｜NT$ "
            + delete_df["金額"].map(lambda x: f"{x:,.0f}")
        )

        selected_delete_item = st.selectbox("選擇要刪除的交易", delete_df["顯示名稱"].tolist())
        selected_delete_id = int(selected_delete_item.split("｜")[0])

        st.warning("刪除後無法復原，請確認你選的是正確交易。")
        confirm_delete = st.checkbox("我確認要刪除這筆交易")

        if st.button("刪除選取交易", type="primary"):
            if confirm_delete:
                delete_transaction(USER_ID, selected_delete_id)
                st.success("交易已刪除")
                st.rerun()
            else:
                st.error("請先勾選確認刪除")


# ============================================================
# Tab 12：資料管理
# ============================================================
with tab12:
    st.subheader("資料管理")

    st.write("### CSV 匯出")

    if df.empty:
        st.info("目前沒有交易資料可匯出。")
    else:
        export_df = df.drop(columns=["月份"])
        export_df["日期"] = export_df["日期"].dt.strftime("%Y-%m-%d")

        csv_data = export_df.to_csv(index=False).encode("utf-8-sig")

        st.download_button(
            label="下載交易 CSV",
            data=csv_data,
            file_name="transactions_backup.csv",
            mime="text/csv",
            use_container_width=True
        )

    st.divider()

    st.divider()

    st.write("### Supabase 資料備份說明")

    st.info(
        "目前資料已儲存在 Supabase 雲端資料庫。"
        "若要備份交易資料，請使用上方的「下載交易 CSV」。"
        "若要完整備份整個資料庫，可到 Supabase Dashboard 匯出資料。"
    )

    st.divider()

    st.write("### 匯入 CSV")

    uploaded_file = st.file_uploader("選擇 CSV 檔案", type=["csv"], key="import_csv")

    st.caption("CSV 欄位需要包含：日期、類型、項目、分類、帳戶、金額、備註。")

    if uploaded_file is not None:
        try:
            import_df = pd.read_csv(uploaded_file)

            required_columns = ["日期", "類型", "項目", "分類", "帳戶", "金額", "備註"]

            missing_columns = [
                col for col in required_columns
                if col not in import_df.columns
            ]

            if missing_columns:
                st.error(f"CSV 缺少欄位：{', '.join(missing_columns)}")
            else:
                st.write("預覽匯入資料")
                st.dataframe(import_df.head(10), use_container_width=True, hide_index=True)

                if st.button("確認匯入 CSV"):
                    success_count = 0

                    for _, row in import_df.iterrows():
                        try:
                            import_date = pd.to_datetime(row["日期"]).strftime("%Y-%m-%d")
                            import_type = str(row["類型"])
                            import_title = str(row["項目"])
                            import_category = str(row["分類"])
                            import_account = str(row["帳戶"])
                            import_amount = float(row["金額"])
                            import_note = "" if pd.isna(row["備註"]) else str(row["備註"])

                            if import_type in ["收入", "支出"] and import_amount > 0 and import_title.strip():
                                add_transaction(
                                    USER_ID,
                                    import_date,
                                    import_type,
                                    import_title,
                                    import_category,
                                    import_account,
                                    import_amount,
                                    import_note
                                )

                                upsert_saved_item(
                                    USER_ID,
                                    import_type,
                                    import_title,
                                    import_category,
                                    import_account
                                )

                                success_count += 1
                        except Exception:
                            pass

                    st.success(f"CSV 匯入完成，共匯入 {success_count} 筆資料")
                    st.rerun()

        except Exception as e:
            st.error(f"CSV 讀取失敗：{e}")

    st.divider()

    st.write("### 清除交易資料")

    st.warning("清除所有交易資料後無法復原，建議先下載備份。")

    confirm_clear = st.checkbox("我確認要清除所有交易資料")

    if st.button("清除所有交易資料"):
        if confirm_clear:
            delete_all_transactions(USER_ID)
            st.success("所有交易資料已清除")
            st.rerun()
        else:
            st.error("請先勾選確認清除")
