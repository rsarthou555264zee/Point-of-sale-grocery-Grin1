import json
import datetime
import sys
from decimal import Decimal, getcontext

import pymysql
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit,
    QVBoxLayout, QHBoxLayout, QPushButton, QTableWidget,
    QTableWidgetItem, QSpinBox, QDoubleSpinBox, QMessageBox,
    QHeaderView, QDialog, QButtonGroup, QRadioButton,
    QDialogButtonBox, QSizePolicy, QGridLayout, QComboBox,
    QCompleter, QFrame, QStackedWidget, QAbstractItemView, QDateEdit, QInputDialog, QTabWidget,
    QCheckBox  # ADDED: For refund checkboxes
)
from PyQt6.QtCore import Qt, QStringListModel, QTimer
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QPixmap, QColor, QBrush, QDoubleValidator, QIntValidator  # ADDED: Validators
from calendar import monthrange
from PyQt6.QtGui import QPainter, QColor, QFont, QPen
from PyQt6.QtCore import QRectF, QPointF
import math

# ----------  MySQL  ----------
DB = dict(host='localhost', user='root', password='', database='pos_db', autocommit=True)


def get_connection():
    return pymysql.connect(**DB)


def validate_user(username: str, password: str) -> bool:
    sql = "SELECT 1 FROM users WHERE username=%s AND password=SHA2(%s, 256)"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (username, password))
            return cur.fetchone() is not None


def get_items_from_db():
    """Fetch all items from the database"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, price, stock FROM items WHERE stock > 0 ORDER BY name")
                items = cur.fetchall()
                return items
    except Exception as e:
        print(f"Error fetching items: {e}")
        return []


# ----------  Helper Function for SQL Sum  ----------
def sql_sum(where, params):
    """Helper function to calculate sum from sales table"""
    sql = f"SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE {where}"
    print(f"DEBUG: Executing SQL: {sql} with params: {params}")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = float(cur.fetchone()[0])
            print(f"DEBUG: SQL result: {result}")
            return result


# ==========================================================
#  SMALL WIDGETS
# ==========================================================
class RectWidget(QFrame):
    def __init__(self, color="#2ecc71", title="", value=""):
        super().__init__()
        self.setFixedSize(260, 60)
        lighter = QColor(color).lighter(150)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {lighter.name()};
                border-radius: 10px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(2)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("font-size: 14px; color: #333; font-weight: bold;")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.value_label = QLabel(value)
        self.value_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333;")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)

    def set_value(self, txt):
        self.value_label.setText(txt)


# ==========================================================
#  DASHBOARD PAGE
# ==========================================================
class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 2, 0)
        layout.setSpacing(10)

        # auto-refresh top-cashier notification
        self._last_top = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_top_cashier)
        self._timer.start(30000)

        # KPI fetch
        self.kpi = self._fetch_kpi()
        data = [
            {"title": "Today sales", "value": f"₱{self.kpi['daily']:,.2f}"},
            {"title": "Top Cashier", "value": self.kpi['top_cashier']},
            {"title": "Cancel sales", "value": "0%"},
            {"title": "New Products", "value": f"Item ({self.kpi['new_products']})"},
            {"title": "Daily Profit", "value": f"₱{self.kpi['daily'] * 0.25:,.2f}"},
            {"title": "Weekly Profit", "value": f"₱{self.kpi['weekly']:,.2f}"},
            {"title": "Current Month", "value": f"Profit ₱{self.kpi['month']:,.2f}"},
            {"title": "Current Year", "value": f"profit ₱{self.kpi['year']:,.2f}"}
        ]
        colors = ["#2ecc71", "#2ecc71", "#f1c40f", "#3498db",
                  "#2ecc71", "#2ecc71", "#2ecc71", "#2ecc71"]

        # 4×2 grid
        grid_container = QWidget()
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setSpacing(0)
        grid_layout.setContentsMargins(4, 3, 3, 4)

        self.rect_widgets = []
        idx = 0
        for r in range(2):
            row_widget = QWidget()
            h = QHBoxLayout(row_widget)
            h.setSpacing(-40)
            h.setContentsMargins(-30, 0, 0, -30)
            for c in range(4):
                rect = RectWidget(colors[idx], data[idx]["title"], data[idx]["value"])
                self.rect_widgets.append(rect)
                h.addWidget(rect)
                idx += 1
            grid_layout.addWidget(row_widget)

        layout.addWidget(grid_container, alignment=Qt.AlignmentFlag.AlignTop)
        self._build_user_card()
        layout.addStretch()

    def set_username(self, name):
        self.name_lbl.setText(name)

    def _check_top_cashier(self):
        today = datetime.date.today()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT cashier, SUM(total_amount)
                               FROM sales
                               WHERE DATE(sale_time) = %s
                               GROUP BY cashier
                               ORDER BY SUM(total_amount) DESC
                               LIMIT 1""", (today,))
                row = cur.fetchone()
        if not row:
            return
        top_name, top_sales = row
        if top_name != self._last_top:
            self._last_top = top_name
            QMessageBox.information(self, "Notification",
                                    f"Top cashier today: {top_name}  (₱{top_sales:,.2f})")

    def _build_user_card(self):
        user_card = QWidget()
        user_card.setFixedHeight(80)
        user_card.setStyleSheet("""
            background-color: #ffffff;
            border: 1px solid #dcdcdc;
            border-radius: 10px;
        """)
        h_user = QHBoxLayout(user_card)
        h_user.setContentsMargins(15, 10, 15, 10)

        avatar = QLabel()
        avatar.setFixedSize(60, 60)
        avatar.setStyleSheet("background-color: #e0e0e0; border-radius: 30px;")
        h_user.addWidget(avatar)

        v_info = QVBoxLayout()
        v_info.setSpacing(2)
        self.name_lbl = QLabel("Username")
        self.name_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #333;")
        notif_lbl = QLabel("Notifications: 0")
        notif_lbl.setStyleSheet("font-size: 14px; color: #666;")
        v_info.addWidget(self.name_lbl)
        v_info.addWidget(notif_lbl)
        h_user.addLayout(v_info)
        h_user.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedSize(70, 30)
        refresh_btn.setStyleSheet("""
            QPushButton{
                background-color: #1976d2;
                color: white;
                border: none;
                border-radius: 5px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover{background-color: #1565c0;}
        """)
        refresh_btn.clicked.connect(self.refresh_values)
        h_user.addWidget(refresh_btn)
        self.layout().addWidget(user_card)

    def _fetch_kpi(self):
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday())
        month_start = today.replace(day=1)
        year_start = today.replace(month=1, day=1)

        daily = sql_sum("DATE(sale_time) = %s", (today,))
        weekly = sql_sum("sale_time >= %s", (week_start,))
        month = sql_sum("sale_time >= %s", (month_start,))
        year = sql_sum("sale_time >= %s", (year_start,))

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT cashier, SUM(total_amount)
                               FROM sales
                               WHERE DATE(sale_time) = %s
                               GROUP BY cashier
                               ORDER BY SUM(total_amount) DESC
                               LIMIT 1""", (today,))
                row = cur.fetchone()
                top = f"{row[0]}  (₱{row[1]:,.2f})" if row else "-"
        new_products = 0  # placeholder
        return {"daily": daily, "weekly": weekly, "month": month,
                "year": year, "top_cashier": top, "new_products": new_products}

    def refresh_values(self):
        self.kpi = self._fetch_kpi()
        keys = ["daily", "top_cashier", "cancel", "new_products",
                "daily", "weekly", "month", "year"]
        for idx, key in enumerate(keys):
            if key == "daily":
                self.rect_widgets[idx].set_value(f"₱{self.kpi['daily']:,.2f}")
            elif key == "top_cashier":
                self.rect_widgets[idx].set_value(self.kpi['top_cashier'])
            elif key == "new_products":
                self.rect_widgets[idx].set_value(f"Item ({self.kpi['new_products']})")
            elif key == "weekly":
                self.rect_widgets[idx].set_value(f"₱{self.kpi['weekly']:,.2f}")
            elif key == "month":
                self.rect_widgets[idx].set_value(f"Profit ₱{self.kpi['month']:,.2f}")
            elif key == "year":
                self.rect_widgets[idx].set_value(f"profit ₱{self.kpi['year']:,.2f}")


# ==========================================================
#  PROCESS-SALES PAGE
# ==========================================================
class ProcessSalesPage(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 9, 9, 9)

        # ----------  top bar  ----------
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 6)

        self.search_le = QLineEdit()
        self.search_le.setFixedWidth(200)
        self.search_le.setPlaceholderText("Search…")
        self.search_le.setStyleSheet("background-color:#219ebc; border:1px solid #999;")
        top_bar.addWidget(self.search_le)

        self.filter_cb = QComboBox()
        self.filter_cb.setFixedWidth(150)
        self.filter_cb.addItems(["All", "Cash", "Card"])
        self.filter_cb.setStyleSheet("background-color:#219ebc; border:1px solid #999;")
        top_bar.addWidget(self.filter_cb)

        self.date_pick = QDateEdit()
        self.date_pick.setDate(datetime.date.today())
        self.date_pick.setCalendarPopup(True)
        self.date_pick.setDisplayFormat("yyyy-MM-dd")
        self.date_pick.setStyleSheet("""
            QDateEdit { color:#fff; background:#333; border:1px solid #555; padding:3px; }
        """)
        top_bar.addWidget(self.date_pick)

        top_bar.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedSize(80, 30)
        refresh_btn.setStyleSheet("""
            QPushButton{ background:#1976d2; color:white; border:none; border-radius:4px; font-weight:bold; }
            QPushButton:hover{ background:#1565c0; }
        """)
        refresh_btn.clicked.connect(self.load_sales)
        top_bar.addWidget(refresh_btn)
        outer.addLayout(top_bar)

        # ----------  table  ----------
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Cashier", "Date / time", "Transaction ID", "Sub-total", "Grand total", "Payment method"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setStyleSheet("""
            QHeaderView::section{ background:#000; color:#fff; }
            QTableWidget{ color:#000; }
        """)
        outer.addWidget(self.table)

        # ----------  signals  ----------
        refresh_btn.clicked.connect(self.load_sales)
        self.filter_cb.currentTextChanged.connect(self.load_sales)
        self.search_le.textChanged.connect(self.load_sales)
        self.date_pick.dateChanged.connect(self.load_sales)

        # auto-refresh every 30 s
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.load_sales)
        self.timer.start(30000)

        self.load_sales()

    def load_sales(self):
        search = self.search_le.text().strip().lower()
        pay_filter = self.filter_cb.currentText()
        selected_date = self.date_pick.date().toPyDate()
        self.table.setRowCount(0)

        sql = """
            SELECT cashier, sale_time, id, total_amount, payment_method
            FROM sales
            WHERE DATE(sale_time) = %s
              AND (cashier LIKE %s OR id LIKE %s)
        """
        params = [selected_date, f"%{search}%", f"%{search}%"]
        if pay_filter != "All":
            sql += " AND payment_method = %s"
            params.append(pay_filter)
        sql += " ORDER BY sale_time DESC LIMIT 200"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                for cashier, ts, tx_id, total, pay in cur.fetchall():
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    self.table.setItem(row, 0, QTableWidgetItem(cashier))
                    self.table.setItem(row, 1, QTableWidgetItem(ts.strftime("%Y-%m-%d %H:%M")))
                    self.table.setItem(row, 2, QTableWidgetItem(str(tx_id)))
                    self.table.setItem(row, 3, QTableWidgetItem(""))
                    self.table.setItem(row, 4, QTableWidgetItem(f"{total:,.2f}"))
                    self.table.setItem(row, 5, QTableWidgetItem(pay))


# ==========================================================
#  SALE-REPORT PAGE (Fixed Event Handling & Styling)
# ==========================================================
class SaleReportPage(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)

        # Set light gray background for the entire page
        self.setStyleSheet("background-color: #f5f5f5;")

        title = QLabel("Sale Report")
        title.setStyleSheet("font-size:20px; font-weight:bold; color:#333; padding:10px;")
        v.addWidget(title)

        # Refresh button
        refresh_btn = QPushButton("Refresh Data")
        refresh_btn.setFixedSize(120, 35)
        refresh_btn.setStyleSheet("""
            QPushButton{
                background:#1976d2; 
                color:white; 
                border:none; 
                border-radius:5px; 
                font-weight:bold;
            }
            QPushButton:hover{background:#1565c0;}
        """)
        refresh_btn.clicked.connect(self._load_data)
        v.addWidget(refresh_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { 
                border: 1px solid #C2C7CB; 
                background-color: white;
                border-radius: 5px;
            }
            QTabBar::tab { 
                background: #E0E0E0; 
                padding: 8px 16px; 
                margin-right: 2px;
                border-top-left-radius: 5px;
                border-top-right-radius: 5px;
                font-weight: bold;
            }
            QTabBar::tab:selected { 
                background: #1976d2; 
                color: white; 
            }
            QTabBar::tab:hover {
                background: #D0D0D0;
            }
        """)
        v.addWidget(self.tab_widget)

        # Tab 1: KPI Cards
        self.kpi_tab = QWidget()
        self.kpi_tab.setStyleSheet("background-color: #f5f5f5;")
        kpi_layout = QVBoxLayout(self.kpi_tab)
        self._setup_kpi_cards(kpi_layout)
        self.tab_widget.addTab(self.kpi_tab, "📊 Key Metrics")

        # Tab 2: Charts
        self.charts_tab = QWidget()
        self.charts_tab.setStyleSheet("background-color: #f5f5f5;")
        charts_layout = QVBoxLayout(self.charts_tab)
        self._setup_qt_charts(charts_layout)
        self.tab_widget.addTab(self.charts_tab, "📈 Charts")

    def _setup_kpi_cards(self, layout):
        """Setup the KPI cards in a grid layout"""

        def _card(caption, value):
            frm = QFrame()
            frm.setFixedSize(220, 90)
            frm.setStyleSheet("""
                QFrame{ 
                    background: white; 
                    border: 2px solid #dcdcdc; 
                    border-radius: 10px; 
                    padding: 10px;
                }
                QLabel{ 
                    background: transparent; 
                    color: #333333;
                }
            """)
            lay = QVBoxLayout(frm)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap_lbl = QLabel(caption)
            cap_lbl.setStyleSheet("font-size: 14px; color: #666666; font-weight: bold;")
            cap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl = QLabel(value)
            val_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #1976d2;")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(cap_lbl)
            lay.addWidget(val_lbl)
            frm.value_lbl = val_lbl
            return frm

        # Create KPI cards
        self.top_cashier_card = _card("Top Cashier", "-")
        self.total_sales_card = _card("Total Sales", "-")
        self.pay_split_card = _card("Payment Split", "-")
        self.daily_sales_card = _card("Daily Sales", "-")
        self.daily_profit_card = _card("Daily Profit", "-")
        self.weekly_profit_card = _card("Weekly Profit", "-")
        self.month_profit_card = _card("Current Month Profit", "-")
        self.year_profit_card = _card("Current Year Profit", "-")

        # Arrange cards in grid
        rows = QVBoxLayout()
        rows.setSpacing(20)

        # Row 1
        row1 = QHBoxLayout()
        row1.addWidget(self.top_cashier_card)
        row1.addWidget(self.total_sales_card)
        row1.addWidget(self.pay_split_card)
        row1.addStretch()
        rows.addLayout(row1)

        # Row 2
        row2 = QHBoxLayout()
        row2.addWidget(self.daily_sales_card)
        row2.addWidget(self.daily_profit_card)
        row2.addWidget(self.weekly_profit_card)
        row2.addStretch()
        rows.addLayout(row2)

        # Row 3
        row3 = QHBoxLayout()
        row3.addWidget(self.month_profit_card)
        row3.addWidget(self.year_profit_card)
        row3.addStretch()
        rows.addLayout(row3)

        layout.addLayout(rows)

    def _setup_qt_charts(self, layout):
        """Setup PyQt6-based charts without matplotlib - FIXED VERSION"""
        # Create a horizontal layout for two charts side by side
        charts_container = QWidget()
        charts_container.setStyleSheet("background-color: #f5f5f5;")
        charts_layout = QHBoxLayout(charts_container)
        charts_layout.setSpacing(20)

        # Profit Comparison Chart - FIXED: Now properly added to layout
        profit_widget = QWidget()
        profit_widget.setStyleSheet("background-color: #f5f5f5;")
        profit_layout = QVBoxLayout(profit_widget)
        profit_title = QLabel("Daily Profit Comparison")
        profit_title.setStyleSheet("""
            font-size: 16px; 
            font-weight: bold; 
            color: #333333; 
            text-align: center; 
            margin: 10px;
            background-color: #f5f5f5;
        """)
        profit_layout.addWidget(profit_title)

        self.profit_chart = SimpleBarChart()
        self.profit_chart.setMinimumSize(380, 280)
        profit_layout.addWidget(self.profit_chart, alignment=Qt.AlignmentFlag.AlignCenter)
        charts_layout.addWidget(profit_widget)

        # Payment Methods Chart
        payment_widget = QWidget()
        payment_widget.setStyleSheet("background-color: #f5f5f5;")
        payment_layout = QVBoxLayout(payment_widget)
        payment_title = QLabel("Payment Methods – Today")
        payment_title.setStyleSheet("""
            font-size: 16px; font-weight: bold; color: #333;
            text-align: center; margin: 10px;
            background-color: #f5f5f5;
        """)
        payment_layout.addWidget(payment_title)

        self.payment_chart = SimpleBarChart()
        self.payment_chart.setMinimumSize(380, 280)
        payment_layout.addWidget(self.payment_chart, alignment=Qt.AlignmentFlag.AlignCenter)
        charts_layout.addWidget(payment_widget)

        layout.addWidget(charts_container)

    def _load_data(self):
        """Load all data including KPI and charts"""
        try:
            print("DEBUG: Starting _load_data")  # Debug print

            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            week_start = today - datetime.timedelta(days=today.weekday())
            month_start = today.replace(day=1)
            year_start = today.replace(month=1, day=1)

            print(f"DEBUG: Date ranges - Today: {today}, Week: {week_start}, Month: {month_start}, Year: {year_start}")

            # Fetch sales data with error handling
            daily_sales = sql_sum("DATE(sale_time) = %s", (today,)) or 0.0
            yesterday_sales = sql_sum("DATE(sale_time) = %s", (yesterday,)) or 0.0
            cash_today = sql_sum("payment_method = 'Cash' AND DATE(sale_time) = %s", (today,)) or 0.0
            card_today = sql_sum("payment_method = 'Card' AND DATE(sale_time) = %s", (today,)) or 0.0
            weekly_sales = sql_sum("sale_time >= %s", (week_start,)) or 0.0
            month_sales = sql_sum("sale_time >= %s", (month_start,)) or 0.0
            year_sales = sql_sum("sale_time >= %s", (year_start,)) or 0.0

            print(
                f"DEBUG: Sales data - Daily: {daily_sales}, Weekly: {weekly_sales}, Monthly: {month_sales}, Yearly: {year_sales}")

            # Calculate profits (assuming 25% profit margin)
            daily_profit = daily_sales * 0.25
            yesterday_profit = yesterday_sales * 0.25
            weekly_profit_amount = weekly_sales * 0.25
            month_profit_amount = month_sales * 0.25
            year_profit_amount = year_sales * 0.25

            print(f"DEBUG: Profit data - Daily: {daily_profit}, Weekly: {weekly_profit_amount}")

            # Update top cashier card
            top_cashier_text = "No sales today"
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""SELECT cashier, SUM(total_amount)
                                       FROM sales
                                       WHERE DATE(sale_time) = %s
                                       GROUP BY cashier
                                       ORDER BY SUM(total_amount) DESC
                                       LIMIT 1""", (today,))
                        row = cur.fetchone()
                        if row and row[0] and row[1]:
                            top_cashier, top_amount = row
                            top_cashier_text = f"{top_cashier}\n₱{top_amount:,.2f}"
                            print(f"DEBUG: Top cashier found: {top_cashier} with {top_amount}")
                        else:
                            print("DEBUG: No top cashier data found")
            except Exception as e:
                print(f"DEBUG: Error fetching top cashier: {e}")
                top_cashier_text = "Error fetching data"

            # Update all KPI cards with proper formatting
            print("DEBUG: Updating KPI cards")
            self.top_cashier_card.value_lbl.setText(top_cashier_text)
            self.daily_sales_card.value_lbl.setText(f"₱{daily_sales:,.2f}")
            self.daily_profit_card.value_lbl.setText(f"₱{daily_profit:,.2f}")
            self.weekly_profit_card.value_lbl.setText(f"₱{weekly_profit_amount:,.2f}")
            self.month_profit_card.value_lbl.setText(f"₱{month_profit_amount:,.2f}")
            self.year_profit_card.value_lbl.setText(f"₱{year_profit_amount:,.2f}")
            self.total_sales_card.value_lbl.setText(f"₱{daily_sales:,.2f}")

            # Payment split with safe percentage calculation
            total_today = cash_today + card_today
            payment_text = "No sales today"
            if total_today > 0:
                cash_percent = (cash_today / total_today) * 100
                card_percent = (card_today / total_today) * 100
                payment_text = f"Cash: {cash_percent:.1f}%\nCard: {card_percent:.1f}%"
                print(f"DEBUG: Payment split - Cash: {cash_percent:.1f}%, Card: {card_percent:.1f}%")
            else:
                print("DEBUG: No payment data available")

            self.pay_split_card.value_lbl.setText(payment_text)

            # Update charts
            print("DEBUG: Updating charts")
            self._update_profit_chart(daily_profit, yesterday_profit)
            self._update_payment_chart(cash_today, card_today)

            print("DEBUG: _load_data completed successfully")

        except Exception as e:
            print(f"DEBUG: Error in _load_data: {e}")
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "Data Error", f"Could not load report data: {str(e)}")

    def showEvent(self, event):
        """Override showEvent to load data when the page becomes visible"""
        super().showEvent(event)
        self._load_data()

    def _update_profit_chart(self, today_profit, yesterday_profit):
        data = {'Yesterday': yesterday_profit, 'Today': today_profit}
        self.profit_chart.setData(data, "Daily Profit Comparison")
        self.profit_chart.update()

    def _update_payment_chart(self, cash_amount, card_amount):
        data = {'Cash': cash_amount, 'Card': card_amount}
        self.payment_chart.setData(data, "Payment Methods – Today")
        self.payment_chart.update()


# ==========================================================
#  SIMPLE BAR CHART (Fixed Event Handling & Styling)
# ==========================================================
class SimpleBarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {}
        self.title = ""
        self.setMinimumSize(380, 280)

    def setTitle(self, t):
        self.title = t

    def setData(self, data, title):
        self.data = data
        self.title = title

    def mousePressEvent(self, event):
        """Override mouse press event to prevent propagation"""
        event.accept()

    def mouseReleaseEvent(self, event):
        """Override mouse release event to prevent propagation"""
        event.accept()

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            width = self.width()
            height = self.height()

            # Draw white background with border
            painter.fillRect(0, 0, width, height, QColor(255, 255, 255))
            painter.setPen(QPen(QColor(200, 200, 200), 2))
            painter.drawRect(1, 1, width - 2, height - 2)

            if not self.data:
                # Draw "No data" message
                painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                painter.setPen(QColor(100, 100, 100))
                painter.drawText(QRectF(0, height / 2 - 15, width, 30), Qt.AlignmentFlag.AlignCenter,
                                 "No data available")
                return

            # Draw title
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(QRectF(0, 15, width, 25), Qt.AlignmentFlag.AlignCenter, self.title)

            # Calculate chart area
            chart_margin = 60
            chart_width = width - 2 * chart_margin
            chart_height = height - 100
            chart_bottom = height - 40

            # Find maximum value for scaling
            max_value = max(self.data.values()) if self.data else 1
            if max_value == 0:
                max_value = 1

            # Draw bars
            bar_width = chart_width / (len(self.data) * 2)
            spacing = bar_width / 2

            # Colors for bars
            colors = [QColor(255, 153, 153), QColor(102, 179, 255)]  # Red, Blue

            for i, (label, value) in enumerate(self.data.items()):
                # Calculate bar dimensions
                bar_height = (value / max_value) * chart_height
                x = chart_margin + i * (bar_width + spacing)
                y = chart_bottom - bar_height

                # Draw bar
                color = colors[i % len(colors)]
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawRect(QRectF(x, y, bar_width, bar_height))

                # Draw value on top of bar
                if value > 0:
                    painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                    painter.setPen(QColor(0, 0, 0))
                    value_text = f"₱{value:,.0f}"
                    painter.drawText(QRectF(x, y - 20, bar_width, 20), Qt.AlignmentFlag.AlignCenter, value_text)

                # Draw label below bar
                painter.setFont(QFont("Arial", 10, QFont.Weight.Normal))
                painter.setPen(QColor(0, 0, 0))
                painter.drawText(QRectF(x, chart_bottom + 5, bar_width, 20), Qt.AlignmentFlag.AlignCenter, label)

            # Draw Y-axis labels
            painter.setFont(QFont("Arial", 8))
            painter.setPen(QColor(100, 100, 100))
            for i in range(5):
                y_value = chart_bottom - (i * chart_height / 4)
                value = (i * max_value / 4)
                value_text = f"₱{value:,.0f}"
                painter.drawText(QRectF(5, y_value - 10, chart_margin - 10, 20),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value_text)

            # Draw grid lines
            painter.setPen(QPen(QColor(220, 220, 220), 1))
            for i in range(1, 5):
                y = chart_bottom - (i * chart_height / 4)
                painter.drawLine(chart_margin, y, width - chart_margin, y)

        except Exception as e:
            print(f"Error painting bar chart: {e}")


# ==========================================================
#  SIMPLE PIE CHART (Fixed Event Handling & Styling)
# ==========================================================
class SimplePieChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {}
        self.title = ""
        self.setMinimumSize(380, 280)

    def setData(self, data, title):
        self.data = {k: v for k, v in data.items() if v > 0}  # Filter out zero values
        self.title = title

    def mousePressEvent(self, event):
        """Override mouse press event to prevent propagation"""
        event.accept()  # Accept the event to prevent it from propagating

    def mouseReleaseEvent(self, event):
        """Override mouse release event to prevent propagation"""
        event.accept()  # Accept the event to prevent it from propagating

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)

            width = self.width()
            height = self.height()

            # Draw white background with border
            painter.fillRect(0, 0, width, height, QColor(255, 255, 255))
            painter.setPen(QPen(QColor(200, 200, 200), 2))
            painter.drawRect(1, 1, width - 2, height - 2)

            if not self.data:
                # Draw "No data" message
                painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                painter.setPen(QColor(100, 100, 100))
                painter.drawText(QRectF(0, height / 2 - 15, width, 30), Qt.AlignmentFlag.AlignCenter, "No payment data")
                return

            # Draw title
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(QRectF(0, 15, width, 25), Qt.AlignmentFlag.AlignCenter, self.title)

            # Calculate total
            total = sum(self.data.values())

            # Pie chart dimensions
            pie_diameter = min(width - 100, height - 100)
            pie_radius = pie_diameter / 2
            center_x = width / 2
            center_y = height / 2 + 10

            # Colors for segments
            colors = [QColor(255, 153, 153), QColor(102, 179, 255)]  # Red, Blue

            # Draw pie segments
            start_angle = 0
            for i, (label, value) in enumerate(self.data.items()):
                # Calculate angle for this segment
                angle = (value / total) * 360 * 16  # Qt uses 1/16th degrees

                # Draw segment
                color = colors[i % len(colors)]
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawPie(QRectF(center_x - pie_radius, center_y - pie_radius,
                                       pie_diameter, pie_diameter), start_angle, angle)

                # Calculate label position (outside the pie)
                mid_angle = start_angle + angle / 2
                mid_angle_rad = math.radians(mid_angle / 16)

                label_radius = pie_radius + 25
                label_x = center_x + label_radius * math.cos(mid_angle_rad)
                label_y = center_y - label_radius * math.sin(mid_angle_rad)

                # Draw percentage label
                percentage = (value / total) * 100
                label_text = f"{label}\n{percentage:.1f}%"

                painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                painter.setPen(QColor(0, 0, 0))
                text_rect = QRectF(label_x - 40, label_y - 20, 80, 40)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label_text)

                start_angle += angle

            # Draw total in center
            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            painter.setPen(QColor(0, 0, 0))
            total_text = f"Total:\n₱{total:,.0f}"
            painter.drawText(QRectF(center_x - 40, center_y - 20, 80, 40),
                             Qt.AlignmentFlag.AlignCenter, total_text)

        except Exception as e:
            print(f"Error painting pie chart: {e}")


# ==========================================================
#  SALE-HISTORY PAGE (Simplified - removed matplotlib for now)
# ==========================================================
class SaleHistoryPage(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        header = QLabel("Sale History")
        header.setStyleSheet("font-size:20px; font-weight:bold; color:#333;")
        layout.addWidget(header)

        try:
            self.graph = _SalesGraphWidget()
            layout.addWidget(self.graph, 1)
        except ImportError:
            # Fallback if matplotlib is not available
            error_msg = QLabel(
                "Charts require matplotlib.\n\n"
                "Install with: pip install matplotlib\n\n"
                "Then restart the application."
            )
            error_msg.setStyleSheet("font-size:14px; color:#666; text-align:center;")
            error_msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(error_msg)


class _SalesGraphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        # Import matplotlib here to handle errors gracefully
        try:
            from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
            from matplotlib.figure import Figure
            import numpy as np

            self.FigureCanvas = FigureCanvas
            self.Figure = Figure
            self.np = np
            self.matplotlib_available = True

        except ImportError:
            self.matplotlib_available = False
            error_label = QLabel("Matplotlib not available. Install with: pip install matplotlib")
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout = QVBoxLayout(self)
            layout.addWidget(error_label)
            return

        # Create matplotlib figure and canvas
        self.fig = self.Figure(figsize=(8, 6), dpi=100)
        self.canvas = self.FigureCanvas(self.fig)
        self.axes = self.fig.add_subplot(111)

        # Create control buttons
        self.y_btn = QPushButton("Year View")
        self.m_btn = QPushButton("Month View")
        self.d_btn = QPushButton("Year Comparison")

        # Style buttons
        button_style = """
            QPushButton{
                background:#f0f0f0; 
                color:black; 
                border:1px solid #999; 
                padding:8px 15px; 
                border-radius:4px;
                font-weight:bold;
            }
            QPushButton:hover{ 
                background:#e0e0e0; 
            }
            QPushButton:checked{ 
                background:#1976d2; 
                color:white;
            }
        """

        for btn in [self.y_btn, self.m_btn, self.d_btn]:
            btn.setCheckable(True)
            btn.setStyleSheet(button_style)

        self.y_btn.setChecked(True)

        # Connect buttons
        self.y_btn.clicked.connect(self.show_year)
        self.m_btn.clicked.connect(self.show_month)
        self.d_btn.clicked.connect(self.show_comparison)

        # Create button group
        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.y_btn)
        self.btn_group.addButton(self.m_btn)
        self.btn_group.addButton(self.d_btn)
        self.btn_group.setExclusive(True)

        # Layout
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.y_btn)
        button_layout.addWidget(self.m_btn)
        button_layout.addWidget(self.d_btn)
        button_layout.addStretch()

        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.canvas, 1)
        main_layout.addLayout(button_layout)

        # Load initial data
        self.show_year()

    def _sales_for_year(self, year):
        """Get sales data for a specific year"""
        sql = """
            SELECT MONTH(sale_time) AS month_num, SUM(total_amount) as total
            FROM sales 
            WHERE YEAR(sale_time) = %s 
            GROUP BY month_num 
            ORDER BY month_num
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (year,))
                results = cur.fetchall()

        # Create complete year data (12 months)
        monthly_sales = {month: 0.0 for month in range(1, 13)}
        for month_num, total in results:
            monthly_sales[month_num] = float(total)

        labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        values = [monthly_sales[month] for month in range(1, 13)]

        return labels, values

    def _sales_for_month(self, year, month):
        """Get sales data for a specific month"""
        sql = """
            SELECT DAY(sale_time) AS day_num, SUM(total_amount) as total
            FROM sales 
            WHERE YEAR(sale_time) = %s AND MONTH(sale_time) = %s
            GROUP BY day_num 
            ORDER BY day_num
        """
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (year, month))
                results = cur.fetchall()

        # Get number of days in month
        _, num_days = monthrange(year, month)

        # Create complete month data
        daily_sales = {day: 0.0 for day in range(1, num_days + 1)}
        for day_num, total in results:
            daily_sales[day_num] = float(total)

        labels = [str(day) for day in range(1, num_days + 1)]
        values = [daily_sales[day] for day in range(1, num_days + 1)]

        return labels, values

    def show_year(self):
        """Show current year sales by month"""
        if not self.matplotlib_available:
            return

        current_year = datetime.date.today().year
        labels, values = self._sales_for_year(current_year)

        self.axes.clear()

        # Create bar chart
        bars = self.axes.bar(labels, values, color='skyblue', edgecolor='navy', alpha=0.7)

        # Add value labels on bars
        for bar, value in zip(bars, values):
            if value > 0:
                height = bar.get_height()
                self.axes.text(bar.get_x() + bar.get_width() / 2., height + max(values) * 0.01,
                               f'₱{value:,.0f}', ha='center', va='bottom', fontsize=9)

        self.axes.set_title(f'Sales Overview - {current_year}', fontsize=14, fontweight='bold')
        self.axes.set_ylabel('Sales Amount (₱)', fontweight='bold')
        self.axes.set_xlabel('Month', fontweight='bold')
        self.axes.grid(True, alpha=0.3)

        # Rotate x-axis labels for better readability
        self.axes.tick_params(axis='x', rotation=45)

        # Adjust layout to prevent label cutoff
        self.fig.tight_layout()
        self.canvas.draw()

    def show_month(self):
        """Show current month sales by day"""
        if not self.matplotlib_available:
            return

        today = datetime.date.today()
        labels, values = self._sales_for_month(today.year, today.month)

        self.axes.clear()

        # Create bar chart
        bars = self.axes.bar(labels, values, color='lightgreen', edgecolor='darkgreen', alpha=0.7)

        # Add value labels on bars
        for bar, value in zip(bars, values):
            if value > 0:
                height = bar.get_height()
                self.axes.text(bar.get_x() + bar.get_width() / 2., height + max(values) * 0.01,
                               f'₱{value:,.0f}', ha='center', va='bottom', fontsize=8)

        month_name = today.strftime('%B')
        self.axes.set_title(f'Sales Overview - {month_name} {today.year}', fontsize=14, fontweight='bold')
        self.axes.set_ylabel('Sales Amount (₱)', fontweight='bold')
        self.axes.set_xlabel('Day of Month', fontweight='bold')
        self.axes.grid(True, alpha=0.3)

        # Rotate x-axis labels for better readability
        self.axes.tick_params(axis='x', rotation=45)

        # Adjust layout
        self.fig.tight_layout()
        self.canvas.draw()

    def show_comparison(self):
        """Show year-over-year comparison"""
        if not self.matplotlib_available:
            return

        current_year = datetime.date.today().year
        previous_year = current_year - 1

        # Get data for both years
        labels, current_values = self._sales_for_year(current_year)
        _, previous_values = self._sales_for_year(previous_year)

        self.axes.clear()

        # Set the width of bars
        bar_width = 0.35
        x_pos = self.np.arange(len(labels))

        # Create grouped bar chart
        bars1 = self.axes.bar(x_pos - bar_width / 2, previous_values, bar_width,
                              label=str(previous_year), color='lightcoral', alpha=0.7)
        bars2 = self.axes.bar(x_pos + bar_width / 2, current_values, bar_width,
                              label=str(current_year), color='lightblue', alpha=0.7)

        self.axes.set_xlabel('Month', fontweight='bold')
        self.axes.set_ylabel('Sales Amount (₱)', fontweight='bold')
        self.axes.set_title('Year-over-Year Sales Comparison', fontsize=14, fontweight='bold')
        self.axes.set_xticks(x_pos)
        self.axes.set_xticklabels(labels)
        self.axes.legend()
        self.axes.grid(True, alpha=0.3)

        # Rotate x-axis labels
        self.axes.tick_params(axis='x', rotation=45)

        # Adjust layout
        self.fig.tight_layout()
        self.canvas.draw()


# ==========================================================
#  MAIN ADMIN WINDOW
# ==========================================================
class AdminWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self, username: str, logout_callback):
        super().__init__()
        self.username = username
        self.logout_callback = logout_callback
        self.setWindowTitle(f"Admin Portal – {username}")
        self.resize(1200, 700)

        # ----------  central structure  ----------
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        # ----------  sidebar  ----------
        sidebar = QFrame()
        sidebar.setFixedWidth(261)
        sidebar.setStyleSheet("""
            QFrame{
                background-color: #f5f5f5;
                border-top-right-radius: 15px;
                border-bottom-right-radius: 15px;
                border: 2px solid #333333;
            }
        """)
        sb_layout = QVBoxLayout(sidebar)
        sb_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        sb_layout.setSpacing(12)
        sb_layout.setContentsMargins(15, 15, 15, 15)

        names = ["📊  Dashboard", "📈  Process of Sales",
                 "📋  Sale Report", "📜  Sale History", "🚪  Logout"]
        btn_group = QButtonGroup(self)
        btn_group.setExclusive(True)
        self.buttons = []

        for i, n in enumerate(names):
            b = QPushButton(n)
            b.setCheckable(i < 4)  # only first 4 are pages
            if i == 0:
                b.setChecked(True)
            b.setStyleSheet("""
                QPushButton{
                    background-color: #1976d2;
                    color: white;
                    border: none;
                    border-radius: 22px;
                    min-width: 230px;
                    min-height: 44px;
                    font-weight: bold;
                }
                QPushButton:hover { background-color: #1565c0; }
                QPushButton:checked { background-color: #ff9800; }
            """)
            sb_layout.addWidget(b, alignment=Qt.AlignmentFlag.AlignHCenter)
            btn_group.addButton(b)
            self.buttons.append(b)

        # ----------  content area  ----------
        content = QWidget()
        content.setStyleSheet("background-color: white;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)

        # ----------  create pages  ----------
        self.dashboard_page = DashboardPage()
        self.dashboard_page.set_username(username)
        self.process_sales_page = ProcessSalesPage()
        self.sale_report_page = SaleReportPage()
        self.sale_history_page = SaleHistoryPage()

        self.stacked_widget.addWidget(self.dashboard_page)
        self.stacked_widget.addWidget(self.process_sales_page)
        self.stacked_widget.addWidget(self.sale_report_page)
        self.stacked_widget.addWidget(self.sale_history_page)

        # ----------  assemble  ----------
        root.addWidget(sidebar)
        root.addWidget(content, 1)

        # ----------  signals  ----------
        btn_group.buttonClicked.connect(self._on_nav)

        # ----------  initial load  ----------
        self.dashboard_page.refresh_values()
        self.process_sales_page.load_sales()

    def _on_nav(self, btn):
        txt = btn.text()
        for b in self.buttons:
            b.setChecked(b is btn)

        if "Dashboard" in txt:
            self.stacked_widget.setCurrentIndex(0)
            self.dashboard_page.refresh_values()
        elif "Process of Sales" in txt:
            self.stacked_widget.setCurrentIndex(1)
            self.process_sales_page.load_sales()
        elif "Sale Report" in txt:
            self.stacked_widget.setCurrentIndex(2)
            self.sale_report_page._load_data()
        elif "Sale History" in txt:
            self.stacked_widget.setCurrentIndex(3)
            # Refresh the chart data when navigating to this page
            if hasattr(self.sale_history_page, 'graph') and self.sale_history_page.graph.matplotlib_available:
                self.sale_history_page.graph.show_year()
        elif "Logout" in txt:
            if self.logout_callback:
                self.logout_callback()
            self.close()


# ==========================================================
#  MANAGER WINDOW (UPDATED - Gray Theme, No Spin Buttons, Refund Section)
# ==========================================================
class ManagerWindow(QMainWindow):
    def __init__(self, username, logout_callback):
        super().__init__()
        self.username = username
        self.logout_callback = logout_callback
        self.setWindowTitle(f"Manager Portal – {username}")
        self.resize(1200, 800)  # Increased window size
        central = QWidget()
        central.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)

        # Sidebar
        side = QFrame()
        side.setFixedWidth(200)
        side.setStyleSheet("""
            QFrame{
                background-color: #3c3c3c;
                border-radius: 0px;
            }
            QPushButton{
                background: #3c3c3c;
                color: #ffffff;
                border: none;
                border-radius: 18px;
                padding: 10px;
                text-align: left;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover{
                background: #4a4a4a;
            }
            QPushButton:checked{
                background: #1976d2;
                color: #ffffff;
            }
        """)
        slay = QVBoxLayout(side)
        slay.setAlignment(Qt.AlignmentFlag.AlignTop)
        slay.setSpacing(12)
        slay.setContentsMargins(15, 20, 15, 20)
        self.grp = QButtonGroup(self)
        self.grp.setExclusive(True)

        for txt in ("📊  Dashboard", "📦  Inventory", "📈  Sales Reports", "🔄  Refund", "🚪  Logout"):
            btn = QPushButton(txt)
            btn.setCheckable(True)
            slay.addWidget(btn)
            self.grp.addButton(btn)
        root.addWidget(side)

        self.stack = QStackedWidget()
        root.addWidget(self.stack)

        self.dashboard_page = self.build_manager_dashboard()
        self.inventory_page = self.build_manager_inventory()
        self.sales_page = self.build_manager_sales()
        self.refund_page = self.build_manager_refund()  # Updated refund page
        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.inventory_page)
        self.stack.addWidget(self.sales_page)
        self.stack.addWidget(self.refund_page)

        self.grp.buttonClicked.connect(self.nav)
        self.grp.buttons()[0].setChecked(True)
        self.stack.setCurrentIndex(0)

        # Initialize refund variables
        self.current_transaction_id = None
        self.current_transaction_items = []

    def build_manager_refund(self):
        """Build the refund management page with improved GUI and partial refunds"""
        w = QWidget()
        w.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 30, 30, 30)

        title = QLabel("Refund Management")
        title.setStyleSheet(
            "font-size: 24px; font-weight: bold; color: #ffffff; background-color: transparent; margin-bottom: 20px;")
        lay.addWidget(title)

        # Search section
        search_section = QWidget()
        search_section.setStyleSheet("background: #3c3c3c; border: 1px solid #555; border-radius: 10px; padding: 20px;")
        search_layout = QHBoxLayout(search_section)

        search_layout.addWidget(QLabel("Search Transaction ID:"))
        self.refund_search = QLineEdit()
        self.refund_search.setPlaceholderText("Enter Transaction ID...")
        self.refund_search.setStyleSheet(
            "background: white; color: black; border: 2px solid #ccc; border-radius: 8px; padding: 12px; font-size: 16px;")
        self.refund_search.setMinimumWidth(300)
        self.refund_search.setMinimumHeight(40)

        search_btn = QPushButton("Search Transaction")
        search_btn.setStyleSheet("""
            QPushButton {
                background: #1976d2;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 16px;
                min-height: 40px;
            }
            QPushButton:hover {
                background: #1565c0;
            }
        """)
        search_btn.clicked.connect(self.search_transaction)

        search_layout.addWidget(self.refund_search)
        search_layout.addWidget(search_btn)
        search_layout.addStretch()

        lay.addWidget(search_section)

        # Transaction details section
        self.transaction_section = QWidget()
        self.transaction_section.setStyleSheet(
            "background: #3c3c3c; border: 1px solid #555; border-radius: 10px; padding: 20px; margin-top: 20px;")
        transaction_layout = QVBoxLayout(self.transaction_section)

        transaction_title = QLabel("Transaction Details")
        transaction_title.setStyleSheet("font-size: 20px; font-weight: bold; color: #ffffff; margin-bottom: 15px;")
        transaction_layout.addWidget(transaction_title)

        # Transaction info
        info_layout = QHBoxLayout()
        self.transaction_info = QLabel("No transaction selected")
        self.transaction_info.setStyleSheet("color: #cccccc; font-size: 16px; background-color: transparent;")
        self.transaction_info.setWordWrap(True)
        info_layout.addWidget(self.transaction_info)
        info_layout.addStretch()
        transaction_layout.addLayout(info_layout)

        # Items table - UPDATED with quantity selection
        items_label = QLabel("Select items and quantities to refund:")
        items_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #ffffff; margin-top: 20px; margin-bottom: 10px;")
        transaction_layout.addWidget(items_label)

        # UPDATED: Changed column structure for partial refunds
        self.refund_table = QTableWidget(0, 6)
        self.refund_table.setHorizontalHeaderLabels(
            ["Item", "Price", "Original Qty", "Refund Qty", "Refund Amount", "Select All"])
        self.refund_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.refund_table.horizontalHeader().setStretchLastSection(True)
        self.refund_table.setStyleSheet("""
            QTableWidget {
                background: #2b2b2b;
                border: 2px solid #555;
                color: #ffffff;
                gridline-color: #555;
                font-size: 14px;
            }
            QHeaderView::section {
                background: #1976d2;
                color: #ffffff;
                font-weight: bold;
                padding: 12px;
                border: none;
                font-size: 14px;
            }
            QTableWidget::item {
                padding: 12px;
                border-bottom: 1px solid #555;
                font-size: 14px;
            }
            QTableWidget::item:selected {
                background: #1976d2;
            }
            QLineEdit {
                background: white;
                color: black;
                border: 2px solid #ccc;
                border-radius: 5px;
                padding: 8px;
                font-size: 14px;
                font-weight: bold;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
            }
            QCheckBox::indicator:unchecked {
                border: 2px solid #ccc;
                background: white;
                border-radius: 3px;
            }
            QCheckBox::indicator:checked {
                border: 2px solid #1976d2;
                background: #1976d2;
                border-radius: 3px;
            }
        """)
        # Set column widths
        self.refund_table.setColumnWidth(0, 250)  # Item
        self.refund_table.setColumnWidth(1, 120)  # Price
        self.refund_table.setColumnWidth(2, 120)  # Original Qty
        self.refund_table.setColumnWidth(3, 150)  # Refund Qty
        self.refund_table.setColumnWidth(4, 150)  # Refund Amount
        self.refund_table.setColumnWidth(5, 120)  # Select All

        # Set row height to make table larger
        self.refund_table.verticalHeader().setDefaultSectionSize(1000)

        transaction_layout.addWidget(self.refund_table)

        # Refund controls
        controls_layout = QHBoxLayout()

        self.refund_amount_label = QLabel("Total Refund Amount: ₱0.00")
        self.refund_amount_label.setStyleSheet(
            "font-size: 20px; font-weight: bold; color: #ff6b6b; background-color: transparent; margin-right: 20px;")
        controls_layout.addWidget(self.refund_amount_label)
        controls_layout.addStretch()

        # Add "Select All" and "Clear All" buttons
        select_all_btn = QPushButton("Select All Items")
        select_all_btn.setStyleSheet("""
            QPushButton {
                background: #ff9f1c;
                color: black;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
                min-height: 40px;
            }
            QPushButton:hover {
                background: #ffb627;
            }
        """)
        select_all_btn.clicked.connect(self.select_all_items)
        controls_layout.addWidget(select_all_btn)

        clear_all_btn = QPushButton("Clear All")
        clear_all_btn.setStyleSheet("""
            QPushButton {
                background: #6c757d;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
                min-height: 40px;
            }
            QPushButton:hover {
                background: #5a6268;
            }
        """)
        clear_all_btn.clicked.connect(self.clear_all_items)
        controls_layout.addWidget(clear_all_btn)

        self.process_refund_btn = QPushButton("Process Refund")
        self.process_refund_btn.setStyleSheet("""
            QPushButton {
                background: #ff6b6b;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 16px;
                min-height: 40px;
            }
            QPushButton:hover {
                background: #ff5252;
            }
            QPushButton:disabled {
                background: #666;
                color: #999;
            }
        """)
        self.process_refund_btn.clicked.connect(self.process_refund)
        self.process_refund_btn.setEnabled(False)
        controls_layout.addWidget(self.process_refund_btn)

        transaction_layout.addLayout(controls_layout)

        lay.addWidget(self.transaction_section)
        self.transaction_section.hide()

        lay.addStretch()
        return w

    def search_transaction(self):
        """Search for transaction by ID"""
        transaction_id = self.refund_search.text().strip()
        if not transaction_id:
            QMessageBox.warning(self, "Search Error", "Please enter a transaction ID.")
            return

        print(f"DEBUG: Searching for transaction ID: {transaction_id}")

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # First check if refunds table exists, if not create it
                    try:
                        cur.execute("""
                            CREATE TABLE IF NOT EXISTS refunds (
                                id INT AUTO_INCREMENT PRIMARY KEY,
                                transaction_id VARCHAR(50) NOT NULL,
                                refund_amount DECIMAL(10,2) NOT NULL,
                                processed_by VARCHAR(50) NOT NULL,
                                processed_at DATETIME NOT NULL,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            )
                        """)
                        print("DEBUG: Refunds table checked/created")
                    except Exception as e:
                        print(f"DEBUG: Error creating refunds table: {e}")

                    # Search for transaction
                    cur.execute("""
                        SELECT cashier, sale_time, total_amount, payment_method, items_json 
                        FROM sales 
                        WHERE id = %s
                    """, (transaction_id,))
                    result = cur.fetchone()

                    if not result:
                        QMessageBox.warning(self, "Not Found", f"Transaction {transaction_id} not found.")
                        self.transaction_section.hide()
                        return

                    # Show transaction details
                    cashier, sale_time, total_amount, payment_method, items_json = result
                    self.transaction_info.setText(
                        f"Transaction ID: {transaction_id}\n"
                        f"Cashier: {cashier} | "
                        f"Date: {sale_time.strftime('%Y-%m-%d %H:%M')}\n"
                        f"Total: ₱{total_amount:,.2f} | "
                        f"Payment: {payment_method}"
                    )

                    # Load items into table
                    self.refund_table.setRowCount(0)
                    try:
                        items = json.loads(items_json)
                        self.current_transaction_items = items

                        print(f"DEBUG: Found {len(items)} items in transaction:")
                        for i, item in enumerate(items):
                            print(f"  Item {i + 1}: {item['name']} - ₱{item['price']} x {item['qty']}")

                        for item in items:
                            row = self.refund_table.rowCount()
                            self.refund_table.insertRow(row)

                            # Item name
                            self.refund_table.setItem(row, 0, QTableWidgetItem(item["name"]))

                            # Price
                            self.refund_table.setItem(row, 1, QTableWidgetItem(f"₱{float(item['price']):.2f}"))

                            # Original quantity
                            self.refund_table.setItem(row, 2, QTableWidgetItem(str(item["qty"])))

                            # Refund quantity - CHANGED TO LINE EDIT
                            refund_input = QLineEdit()
                            refund_input.setPlaceholderText("0")
                            refund_input.setValidator(QIntValidator(0, item["qty"]))
                            refund_input.setText("0")
                            refund_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
                            refund_input.textChanged.connect(self.update_refund_amount)
                            self.refund_table.setCellWidget(row, 3, refund_input)

                            # Refund amount (will be calculated)
                            refund_amount_item = QTableWidgetItem("₱0.00")
                            refund_amount_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                            self.refund_table.setItem(row, 4, refund_amount_item)

                            # Select all checkbox
                            checkbox = QCheckBox()
                            checkbox.stateChanged.connect(lambda state, r=row: self.toggle_item_refund(r, state))
                            self.refund_table.setCellWidget(row, 5, checkbox)

                        print(f"DEBUG: Loaded {len(items)} items into refund table")

                    except json.JSONDecodeError as e:
                        print(f"DEBUG: JSON decode error: {e}")
                        QMessageBox.critical(self, "Error", f"Failed to parse transaction items: {str(e)}")
                        return
                    except KeyError as e:
                        print(f"DEBUG: Missing key in item data: {e}")
                        QMessageBox.critical(self, "Error", f"Invalid item data structure: {str(e)}")
                        return

                    self.transaction_section.show()
                    self.current_transaction_id = transaction_id
                    self.update_refund_amount()

        except Exception as e:
            print(f"DEBUG: Error in search_transaction: {e}")
            QMessageBox.critical(self, "Error", f"Failed to search transaction: {str(e)}")

    def toggle_item_refund(self, row, state):
        """Toggle refund quantity for an item when checkbox is checked/unchecked"""
        if 0 <= row < self.refund_table.rowCount():
            refund_input = self.refund_table.cellWidget(row, 3)
            original_qty_item = self.refund_table.item(row, 2)

            if refund_input and original_qty_item:
                if state == Qt.CheckState.Checked.value:
                    # Set refund quantity to full original quantity
                    original_qty = int(original_qty_item.text())
                    refund_input.setText(str(original_qty))
                else:
                    # Set refund quantity to 0
                    refund_input.setText("0")

    def select_all_items(self):
        """Select all items for full refund"""
        for row in range(self.refund_table.rowCount()):
            checkbox = self.refund_table.cellWidget(row, 5)
            if checkbox:
                checkbox.setChecked(True)

    def clear_all_items(self):
        """Clear all refund selections"""
        for row in range(self.refund_table.rowCount()):
            checkbox = self.refund_table.cellWidget(row, 5)
            if checkbox:
                checkbox.setChecked(False)

    def update_refund_amount(self):
        """Update refund amount based on selected quantities"""
        try:
            total_refund = 0.0
            items_selected = False

            print("DEBUG: Updating refund amount...")

            for row in range(self.refund_table.rowCount()):
                refund_input = self.refund_table.cellWidget(row, 3)
                if refund_input and refund_input.text().strip():
                    try:
                        refund_qty = int(refund_input.text())
                    except ValueError:
                        refund_qty = 0

                    if refund_qty > 0:
                        price_text = self.refund_table.item(row, 1).text().replace('₱', '').replace(',', '').strip()

                        print(f"DEBUG: Row {row} - Price: '{price_text}', Refund Qty: '{refund_qty}'")

                        try:
                            price = float(price_text)
                            item_refund = price * refund_qty
                            total_refund += item_refund
                            items_selected = True

                            # Update individual refund amount display
                            self.refund_table.item(row, 4).setText(f"₱{item_refund:.2f}")

                            print(f"DEBUG: Added {refund_qty} x ₱{price} = ₱{item_refund}")
                        except ValueError as e:
                            print(f"DEBUG: Error parsing price: {e}")
                            continue

            print(f"DEBUG: Total refund amount: ₱{total_refund:,.2f}, Items selected: {items_selected}")
            self.refund_amount_label.setText(f"Total Refund Amount: ₱{total_refund:,.2f}")
            self.process_refund_btn.setEnabled(items_selected and total_refund > 0)

        except Exception as e:
            print(f"DEBUG: Error in update_refund_amount: {e}")

    def process_refund(self):
        """Process the refund for selected quantities"""
        if not hasattr(self, 'current_transaction_id') or not self.current_transaction_id:
            QMessageBox.warning(self, "Error", "No transaction selected.")
            return

        refund_amount_text = self.refund_amount_label.text().split('₱')[1].replace(',', '').strip()

        try:
            refund_amount = float(refund_amount_text)
        except ValueError:
            QMessageBox.warning(self, "Error", "Invalid refund amount.")
            return

        print(f"DEBUG: Starting refund process for transaction {self.current_transaction_id}")
        print(f"DEBUG: Refund amount: ₱{refund_amount:,.2f}")

        # Get selected items and quantities for debugging and confirmation
        refund_details = []
        for row in range(self.refund_table.rowCount()):
            refund_input = self.refund_table.cellWidget(row, 3)
            if refund_input and refund_input.text().strip():
                try:
                    refund_qty = int(refund_input.text())
                except ValueError:
                    refund_qty = 0

                if refund_qty > 0:
                    item_name = self.refund_table.item(row, 0).text()
                    original_qty = self.refund_table.item(row, 2).text()
                    refund_details.append(f"{item_name}: {refund_qty}/{original_qty} units")

        print(f"DEBUG: Refund details: {refund_details}")

        if not refund_details:
            QMessageBox.warning(self, "Error", "No items selected for refund.")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Refund",
            f"Process refund of ₱{refund_amount:,.2f} for transaction {self.current_transaction_id}?\n\n"
            f"Refund items:\n" + "\n".join(refund_details) + "\n\nThis action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        # Insert refund record
                        cur.execute("""
                            INSERT INTO refunds (transaction_id, refund_amount, processed_by, processed_at)
                            VALUES (%s, %s, %s, %s)
                        """, (self.current_transaction_id, refund_amount, self.username, datetime.datetime.now()))

                        refund_id = cur.lastrowid
                        print(f"DEBUG: Refund record inserted with ID: {refund_id}")

                        # Update stock for refunded items
                        items_refunded = 0
                        stock_updates = []

                        for row in range(self.refund_table.rowCount()):
                            refund_input = self.refund_table.cellWidget(row, 3)
                            if refund_input and refund_input.text().strip():
                                try:
                                    refund_qty = int(refund_input.text())
                                except ValueError:
                                    refund_qty = 0

                                if refund_qty > 0:
                                    item_name = self.refund_table.item(row, 0).text()

                                    # Find item ID and current stock
                                    cur.execute("SELECT id, stock FROM items WHERE name = %s", (item_name,))
                                    result = cur.fetchone()
                                    if result:
                                        item_id, current_stock = result
                                        print(
                                            f"DEBUG: Updating stock for {item_name} (ID: {item_id}) - Adding {refund_qty} to current stock {current_stock}")

                                        cur.execute("UPDATE items SET stock = stock + %s WHERE id = %s",
                                                    (refund_qty, item_id))
                                        items_refunded += 1
                                        stock_updates.append(f"{item_name}: +{refund_qty}")

                                        # Verify the update
                                        cur.execute("SELECT stock FROM items WHERE id = %s", (item_id,))
                                        new_stock = cur.fetchone()[0]
                                        print(f"DEBUG: Stock updated for {item_name}: {current_stock} -> {new_stock}")
                                    else:
                                        print(f"DEBUG: ERROR - Item {item_name} not found in database")
                                        QMessageBox.warning(self, "Warning",
                                                            f"Item '{item_name}' not found in database. Stock not updated for this item.")

                success_message = (
                    f"Refund processed successfully!\n\n"
                    f"Transaction: {self.current_transaction_id}\n"
                    f"Refund Amount: ₱{refund_amount:,.2f}\n"
                    f"Items Refunded: {items_refunded}\n"
                    f"Processed by: {self.username}"
                )

                if stock_updates:
                    success_message += f"\n\nStock updates:\n" + "\n".join(stock_updates)

                QMessageBox.information(self, "Refund Processed", success_message)

                # Reset form
                self.refund_search.clear()
                self.transaction_section.hide()
                self.process_refund_btn.setEnabled(False)
                self.current_transaction_id = None
                self.current_transaction_items = []

                print("DEBUG: Refund process completed successfully")

            except Exception as e:
                print(f"DEBUG: Error in process_refund: {e}")
                QMessageBox.critical(self, "Refund Error", f"Failed to process refund: {str(e)}")

    # ... (keep all the existing manager page methods the same) ...
    def build_manager_dashboard(self):
        w = QWidget()
        w.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 30, 30, 30)
        title = QLabel("Manager Dashboard")
        title.setStyleSheet("font-size:22px;font-weight:bold;color:#ffffff;background-color:transparent;")
        lay.addWidget(title)

        # KPI Card with gray theme
        class KPICard(QWidget):
            def __init__(self, t, v):
                super().__init__()
                self.setFixedSize(200, 80)
                self.setStyleSheet("""
                    background: #3c3c3c; 
                    border: 1px solid #555; 
                    border-radius: 10px;
                    color: #ffffff;
                """)
                l = QVBoxLayout(self)
                l.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.title = QLabel(t)
                self.value = QLabel(v)
                self.title.setStyleSheet("font-weight:bold;color:#cccccc;font-size:14px;background-color:transparent;")
                self.value.setStyleSheet("font-weight:bold;color:#4fc3f7;font-size:16px;background-color:transparent;")
                for lbl in (self.title, self.value):
                    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                l.addWidget(self.title)
                l.addWidget(self.value)

            def set_value(self, v):
                self.value.setText(v)

        h = QHBoxLayout()
        self.kpi_daily = KPICard("Today Sales", "₱0.00")
        self.kpi_week = KPICard("This Week", "₱0.00")
        self.kpi_top = KPICard("Top Cashier", "-")
        self.kpi_items = KPICard("Items in Stock", "0")
        for c in (self.kpi_daily, self.kpi_week, self.kpi_top, self.kpi_items):
            h.addWidget(c)
        h.addStretch()
        lay.addLayout(h)

        ref = QPushButton("Refresh")
        ref.setStyleSheet("""
            background:#1976d2;
            color:#fff;
            border:none;
            border-radius:5px;
            padding:8px 16px;
            font-weight:bold;
            font-size:14px;
        """)
        ref.clicked.connect(self.refresh_dashboard)
        lay.addWidget(ref, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addStretch()
        return w

    def build_manager_inventory(self):
        w = QWidget()
        w.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 30, 30, 30)

        title = QLabel("Inventory Management")
        title.setStyleSheet("font-size:22px;font-weight:bold;color:#ffffff;background-color:transparent;")
        lay.addWidget(title)

        # NEW: Add New Item section
        add_section = QWidget()
        add_section.setStyleSheet("background:#3c3c3c; border:1px solid #555; border-radius:10px; padding:15px;")
        add_layout = QVBoxLayout(add_section)

        add_title = QLabel("Add New Item")
        add_title.setStyleSheet("font-size:16px; font-weight:bold; color:#ffffff;")
        add_layout.addWidget(add_title)

        # Form for adding new items
        form_layout = QHBoxLayout()

        self.new_item_name = QLineEdit()
        self.new_item_name.setPlaceholderText("Item Name")
        self.new_item_name.setStyleSheet(
            "background:white; color:black; border:1px solid #ccc; border-radius:5px; padding:8px;")

        # UPDATED: Price input without spin buttons
        self.new_item_price = QLineEdit()
        self.new_item_price.setPlaceholderText("0.00")
        self.new_item_price.setValidator(QDoubleValidator(0.01, 999999.99, 2))
        self.new_item_price.setStyleSheet(
            "background:white; color:black; border:1px solid #ccc; border-radius:5px; padding:8px;")

        # UPDATED: Stock input without spin buttons
        self.new_item_stock = QLineEdit()
        self.new_item_stock.setPlaceholderText("0")
        self.new_item_stock.setValidator(QIntValidator(0, 9999))
        self.new_item_stock.setStyleSheet(
            "background:white; color:black; border:1px solid #ccc; border-radius:5px; padding:8px;")

        add_item_btn = QPushButton("Add New Item")
        add_item_btn.setStyleSheet("""
            background:#06d6a0;
            color:#000;
            border:none;
            border-radius:5px;
            padding:8px 16px;
            font-weight:bold;
        """)
        add_item_btn.clicked.connect(self.add_new_item)

        form_layout.addWidget(QLabel("Name:"))
        form_layout.addWidget(self.new_item_name)
        form_layout.addWidget(QLabel("Price:"))
        form_layout.addWidget(self.new_item_price)
        form_layout.addWidget(QLabel("Stock:"))
        form_layout.addWidget(self.new_item_stock)
        form_layout.addWidget(add_item_btn)

        add_layout.addLayout(form_layout)
        lay.addWidget(add_section)

        # quick-add section
        quick_add_section = QWidget()
        quick_add_section.setStyleSheet(
            "background:#3c3c3c; border:1px solid #555; border-radius:10px; padding:15px; margin-top:10px;")
        quick_layout = QHBoxLayout(quick_add_section)

        quick_layout.addWidget(QLabel("Quick add stock to existing item:"))
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setFixedWidth(250)
        self.combo.setStyleSheet(
            "background:white; color:black; border:1px solid #ccc; border-radius:5px; padding:8px;")

        # UPDATED: Stock input without spin buttons for quick add
        self.stock_input = QLineEdit()  # Changed from self.spin to self.stock_input
        self.stock_input.setPlaceholderText("1")
        self.stock_input.setValidator(QIntValidator(1, 9999))
        self.stock_input.setStyleSheet(
            "background:white; color:black; border:1px solid #ccc; border-radius:5px; padding:8px;")
        self.stock_input.setText("1")

        add_btn = QPushButton("Add Stock")
        add_btn.setStyleSheet("""
            background:#219ebc;
            color:#fff;
            border:none;
            border-radius:5px;
            padding:8px 16px;
            font-weight:bold;
        """)
        add_btn.clicked.connect(self.quick_add_inventory)

        quick_layout.addWidget(self.combo)
        quick_layout.addWidget(self.stock_input)
        quick_layout.addWidget(add_btn)
        quick_layout.addStretch()

        lay.addWidget(quick_add_section)

        # table
        self.inv_table = QTableWidget(0, 5)
        self.inv_table.setHorizontalHeaderLabels(["ID", "Name", "Price", "Stock", "Actions"])
        self.inv_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.inv_table.horizontalHeader().setStretchLastSection(True)
        self.inv_table.setStyleSheet("""
            QTableWidget{
                background:#3c3c3c;
                border:1px solid #555;
                color: #ffffff;
            } 
            QHeaderView::section{
                background:#1976d2;
                color:#fff;
                font-weight:bold;
            }
            QTableWidget::item {
                padding: 5px;
                color: #ffffff;
            }
        """)
        lay.addWidget(self.inv_table)

        self.load_inventory_table()
        self.fill_inventory_combo()
        return w

    def build_manager_sales(self):
        w = QWidget()
        w.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 30, 30, 30)

        title = QLabel("Sales Reports")
        title.setStyleSheet("font-size:22px;font-weight:bold;color:#ffffff;background-color:transparent;")
        lay.addWidget(title)

        h = QHBoxLayout()
        h.addWidget(QLabel("Date:"))
        self.date_pick = QDateEdit()
        self.date_pick.setDate(datetime.date.today())
        self.date_pick.setCalendarPopup(True)
        self.date_pick.setDisplayFormat("yyyy-MM-dd")
        self.date_pick.setStyleSheet(
            "background:white; color:black; border:1px solid #ccc; border-radius:5px; padding:8px;")

        ref_btn = QPushButton("Refresh")
        ref_btn.setStyleSheet("""
            background:#219ebc;
            color:#fff;
            border:none;
            border-radius:5px;
            padding:8px 16px;
            font-weight:bold;
        """)
        ref_btn.clicked.connect(self.load_sales_table)

        h.addWidget(self.date_pick)
        h.addWidget(ref_btn)
        h.addStretch()
        lay.addLayout(h)

        self.sales_table = QTableWidget(0, 6)
        self.sales_table.setHorizontalHeaderLabels(
            ["Cashier", "Date/Time", "Transaction ID", "Sub-total", "Grand Total", "Payment"])
        self.sales_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sales_table.horizontalHeader().setStretchLastSection(True)
        self.sales_table.setStyleSheet("""
            QTableWidget{
                background:#3c3c3c;
                border:1px solid #555;
                color: #ffffff;
            } 
            QHeaderView::section{
                background:#1976d2;
                color:#fff;
                font-weight:bold;
            }
            QTableWidget::item {
                padding: 5px;
                color: #ffffff;
            }
        """)
        lay.addWidget(self.sales_table)
        self.load_sales_table()
        return w

    # ----------  UPDATED: Add new item functionality with line edits  ----------
    def add_new_item(self):
        """Add a completely new item to the database"""
        name = self.new_item_name.text().strip()
        price_text = self.new_item_price.text().strip()
        stock_text = self.new_item_stock.text().strip()

        if not name:
            QMessageBox.warning(self, "Input Error", "Please enter an item name.")
            return

        if not price_text:
            QMessageBox.warning(self, "Input Error", "Please enter a price.")
            return

        if not stock_text:
            QMessageBox.warning(self, "Input Error", "Please enter stock quantity.")
            return

        try:
            price = float(price_text)
            stock = int(stock_text)

            if price <= 0:
                QMessageBox.warning(self, "Input Error", "Price must be greater than 0.")
                return

            if stock < 0:
                QMessageBox.warning(self, "Input Error", "Stock cannot be negative.")
                return

        except ValueError:
            QMessageBox.warning(self, "Input Error", "Please enter valid numbers for price and stock.")
            return

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if item already exists
                    cur.execute("SELECT id FROM items WHERE name = %s", (name,))
                    if cur.fetchone():
                        QMessageBox.warning(self, "Duplicate Item",
                                            f"Item '{name}' already exists in the database.")
                        return

                    # Insert new item
                    cur.execute("""
                        INSERT INTO items (name, price, stock) 
                        VALUES (%s, %s, %s)
                    """, (name, price, stock))

            QMessageBox.information(self, "Success",
                                    f"Item '{name}' added successfully!\n"
                                    f"Price: ₱{price:.2f}\n"
                                    f"Stock: {stock}")

            # Clear the form
            self.new_item_name.clear()
            self.new_item_price.clear()
            self.new_item_stock.clear()

            # Refresh the inventory
            self.load_inventory_table()
            self.fill_inventory_combo()

        except Exception as e:
            QMessageBox.critical(self, "Database Error",
                                 f"Failed to add item: {str(e)}")

    # ----------  UPDATED: Quick add inventory with line edit  ----------
    def quick_add_inventory(self):
        name = self.combo.currentText()
        if name not in self.item_map:
            QMessageBox.warning(self, "Input", "Select a valid item.")
            return

        qty_text = self.stock_input.text().strip()  # Changed from self.spin to self.stock_input
        if not qty_text:
            QMessageBox.warning(self, "Input", "Please enter quantity.")
            return

        try:
            qty = int(qty_text)
            if qty <= 0:
                QMessageBox.warning(self, "Input", "Quantity must be greater than 0.")
                return
        except ValueError:
            QMessageBox.warning(self, "Input", "Please enter a valid number for quantity.")
            return

        item_id = self.item_map[name]
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE items SET stock = stock + %s WHERE id = %s", (qty, item_id))
        QMessageBox.information(self, "Done", f"Added {qty} pcs to '{name}'.")
        self.load_inventory_table()

    # ----------  manager helpers  ----------
    def refresh_dashboard(self):
        today = datetime.date.today()
        week_start = today - datetime.timedelta(days=today.weekday())
        daily = self.sql_sum("DATE(sale_time) = %s", (today,))
        weekly = self.sql_sum("sale_time >= %s", (week_start,))
        top = self.top_cashier_today()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM items")
                items = cur.fetchone()[0]
        self.kpi_daily.set_value(f"₱{daily:,.2f}")
        self.kpi_week.set_value(f"₱{weekly:,.2f}")
        self.kpi_top.set_value(top)
        self.kpi_items.set_value(str(items))

    def sql_sum(self, where, params):
        sql = f"SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE {where}"
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return float(cur.fetchone()[0])

    def top_cashier_today(self):
        today = datetime.date.today()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT cashier, SUM(total_amount) FROM sales WHERE DATE(sale_time) = %s GROUP BY cashier ORDER BY SUM(total_amount) DESC LIMIT 1",
                    (today,))
                row = cur.fetchone()
                return f"{row[0]}  (₱{row[1]:,.2f})" if row else "-"

    def fill_inventory_combo(self):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name FROM items ORDER BY name")
                items = cur.fetchall()
        self.item_map = {name: id for id, name in items}
        self.combo.clear()
        self.combo.addItems(self.item_map.keys())
        completer = QCompleter(list(self.item_map.keys()), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.combo.setCompleter(completer)

    def load_inventory_table(self):
        self.inv_table.setRowCount(0)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, price, stock FROM items ORDER BY name")
                for id, name, price, stock in cur.fetchall():
                    row = self.inv_table.rowCount()
                    self.inv_table.insertRow(row)
                    self.inv_table.setItem(row, 0, QTableWidgetItem(str(id)))
                    self.inv_table.setItem(row, 1, QTableWidgetItem(name))
                    self.inv_table.setItem(row, 2, QTableWidgetItem(f"₱{price:,.2f}"))
                    self.inv_table.setItem(row, 3, QTableWidgetItem(str(stock)))
                    btn = QPushButton("Edit")
                    btn.setStyleSheet("""
                        background:#ffb703;
                        color:#000;
                        border:none;
                        border-radius:4px;
                        padding:5px 10px;
                        font-weight:bold;
                    """)
                    btn.clicked.connect(lambda _, i=id, n=name, p=price, s=stock: self.edit_item(i, n, p, s))
                    self.inv_table.setCellWidget(row, 4, btn)

    def edit_item(self, id, name, price, stock):
        new_name, ok = QInputDialog.getText(self, "Edit", "Item name:", text=name)
        if not ok: return
        new_price, ok = QInputDialog.getDouble(self, "Edit", "Price:", value=price, decimals=2)
        if not ok: return
        new_stock, ok = QInputDialog.getInt(self, "Edit", "Stock:", value=stock)
        if not ok: return
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("UPDATE items SET name=%s, price=%s, stock=%s WHERE id=%s",
                            (new_name, new_price, new_stock, id))
        QMessageBox.information(self, "Done", "Item updated.")
        self.load_inventory_table()
        self.fill_inventory_combo()

    def load_sales_table(self):
        self.sales_table.setRowCount(0)
        picked = self.date_pick.date().toPyDate()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT cashier, sale_time, id, total_amount, payment_method, items_json
                    FROM sales
                    WHERE DATE(sale_time) = %s
                    ORDER BY sale_time DESC
                """, (picked,))
                for cashier, ts, id, total, pay, items_json in cur.fetchall():
                    row = self.sales_table.rowCount()
                    self.sales_table.insertRow(row)
                    self.sales_table.setItem(row, 0, QTableWidgetItem(cashier))
                    self.sales_table.setItem(row, 1, QTableWidgetItem(ts.strftime("%Y-%m-%d %H:%M")))
                    self.sales_table.setItem(row, 2, QTableWidgetItem(str(id)))
                    self.sales_table.setItem(row, 3, QTableWidgetItem(""))
                    self.sales_table.setItem(row, 4, QTableWidgetItem(f"₱{total:,.2f}"))
                    self.sales_table.setItem(row, 5, QTableWidgetItem(pay))

    def nav(self, btn):
        txt = btn.text()
        if "Dashboard" in txt:
            self.stack.setCurrentIndex(0)
            self.refresh_dashboard()
        elif "Inventory" in txt:
            self.stack.setCurrentIndex(1)
            self.load_inventory_table()
        elif "Sales" in txt:
            self.stack.setCurrentIndex(2)
            self.load_sales_table()
        elif "Refund" in txt:
            self.stack.setCurrentIndex(3)
        elif "Logout" in txt:
            if self.logout_callback:
                self.logout_callback()
            self.close()

def add_new_item(self):
    name, ok = QInputDialog.getText(self, "Add New Item", "Item Name:")
    if not ok or not name:
        return

    price, ok = QInputDialog.getDouble(self, "Add New Item", "Price:", decimals=2)
    if not ok or price <= 0:
        return

    stock, ok = QInputDialog.getInt(self, "Add New Item", "Stock:", min=0)
    if not ok or stock < 0:
        return

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO items (name, price, stock) VALUES (%s, %s, %s)", (name, price, stock))
    QMessageBox.information(self, "Done", f"Added new item '{name}' to inventory.")
    self.load_inventory_table()
    self.fill_inventory_combo()

# ----------  CASHIER WINDOW (unchanged)  ----------
class CashierWindow(QMainWindow):
    def __init__(self, username, logout_callback):
        super().__init__()
        self.username = username
        self.logout_callback = logout_callback
        self.setWindowTitle(f"Cashier POS – {username}")
        self.resize(900, 650)
        self.setStyleSheet("background:#1e1e1e;")
        self.cart = []
        self.items_data = {}
        self._build_ui()
        self._load_items()
        self._fill_item_combo()

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)

        # ----------  TOP BAR  ----------
        top = QHBoxLayout()
        top.setContentsMargins(20, 15, 20, 10)
        title = QLabel(f"Welcome, <b style='color:white;'>{self.username}</b>")
        title.setStyleSheet("font-size:18px;color:white;")
        top.addWidget(title)
        top.addStretch()
        self.total_lbl = QLabel("₱ 0.00")
        self.total_lbl.setStyleSheet("font-size:26px;font-weight:bold;color:#ffd166;")
        top.addWidget(self.total_lbl)
        logout_btn = QPushButton("Logout")
        logout_btn.setFixedSize(80, 38)
        logout_btn.setStyleSheet("background:#e63946;color:#fff;border:none;border-radius:5px;font-weight:bold;")
        logout_btn.clicked.connect(self.logout)
        top.addWidget(logout_btn)
        lay.addLayout(top)

        # ----------  INPUT AREA  ----------
        inp = QHBoxLayout()
        inp.setSpacing(12)
        inp.setContentsMargins(20, 0, 20, 0)

        # Item name (searchable dropdown)
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self.combo.setPlaceholderText("Item name")
        self.combo.setFixedHeight(42)
        self.combo.setStyleSheet("""
            QComboBox{
                background:#2b2b2b;
                border:2px solid black;
                border-radius:6px;
                padding:6px;
                font-size:15px;
                color:#f8f9fa;
            }
            QComboBox QAbstractItemView {
                background:#2b2b2b;
                border:2px solid black;
                color:#f8f9fa;
                selection-background-color:#219ebc;
            }
            QComboBox::drop-down {
                border:none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #f8f9fa;
                width: 0px;
                height: 0px;
            }
        """)
        inp.addWidget(self.combo)

        # Item price (auto-filled, read-only)
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setPrefix("₱ ")
        self.price_spin.setRange(0.01, 999999)
        self.price_spin.setReadOnly(True)
        self.price_spin.setFixedHeight(42)
        self.price_spin.setStyleSheet(
            "background:#2b2b2b;border:1px solid #444;border-radius:6px;padding:6px;font-size:15px;color:#f8f9fa;")
        inp.addWidget(self.price_spin)

        # Item quantity
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 999)
        self.qty_spin.setFixedHeight(42)
        self.qty_spin.setValue(1)
        self.qty_spin.setStyleSheet(
            "background:#2b2b2b;border:1px solid #444;border-radius:6px;padding:6px;font-size:15px;color:#f8f9fa;")
        inp.addWidget(self.qty_spin)

        # Add button
        add_btn = QPushButton("Add")
        add_btn.setFixedHeight(42)
        add_btn.setStyleSheet(
            "background:#06d6a0;color:#000;border:none;border-radius:6px;padding:6px 14px;font-weight:bold;")
        add_btn.clicked.connect(self.add_to_cart)
        inp.addWidget(add_btn)
        lay.addLayout(inp)

        # ----------  CART TABLE  ----------
        self.cart_table = QTableWidget(0, 6)  # Changed to 6 columns for reduce button
        self.cart_table.setHorizontalHeaderLabels(["Item", "Price", "Qty", "Total", "Reduce", "Remove"])
        self.cart_table.setAlternatingRowColors(True)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self.cart_table.horizontalHeader()
        for i in range(4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        # Set fixed width for action columns
        self.cart_table.setColumnWidth(4, 80)
        self.cart_table.setColumnWidth(5, 80)
        self.cart_table.setStyleSheet("""
            QTableWidget{
                background:#2b2b2b;
                gridline-color:#444;
                color:#f8f9fa;
                border:1px solid #444;
                border-radius:6px;
                margin:0px 20px;
            }
            QHeaderView::section{
                background:#023047;
                color:#fff;
                padding:8px;
                border:none;
                font-weight:bold;
            }
        """)
        lay.addWidget(self.cart_table)

        # ----------  BOTTOM BAR  ----------
        bot = QHBoxLayout()
        bot.setContentsMargins(20, 15, 20, 15)

        self.clear_btn = QPushButton("Clear Cart")
        self.clear_btn.setFixedHeight(44)
        self.clear_btn.setStyleSheet(
            "QPushButton{background:#6c757d;color:#fff;border:none;border-radius:6px;font-size:15px;font-weight:bold;}QPushButton:hover{background:#5a6268;}")
        self.clear_btn.clicked.connect(self.clear_cart)
        bot.addWidget(self.clear_btn)

        bot.addStretch()

        self.checkout_btn = QPushButton("Checkout")
        self.checkout_btn.setFixedHeight(50)
        self.checkout_btn.setStyleSheet(
            "QPushButton{background:#06d6a0;color:#000;border:none;border-radius:6px;font-size:17px;font-weight:bold;}QPushButton:hover{background:#0affc2;}")
        self.checkout_btn.clicked.connect(self.checkout)
        bot.addWidget(self.checkout_btn)
        lay.addLayout(bot)

        # ----------  STATUS  ----------
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(
            "color:#adb5bd;padding:10px 20px;font-size:14px;background:#2b2b2b;margin:0px 20px 10px 20px;border-radius:5px;")
        lay.addWidget(self.status_lbl)

        # Connect combo selection to price auto-fill
        self.combo.currentTextChanged.connect(self.on_item_selected)

    def _load_items(self):
        """Load items from database"""
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, name, price, stock FROM items WHERE stock > 0 ORDER BY name")
                    self.items_data = cur.fetchall()
        except Exception as e:
            print(f"Error loading items: {e}")
            self.items_data = []

    def _fill_item_combo(self):
        """Fill the combo box with items and set up search"""
        self.item_map = {name: (id, price, stock) for id, name, price, stock in self.items_data}
        self.combo.clear()
        self.combo.addItems(self.item_map.keys())
        completer = QCompleter(list(self.item_map.keys()), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.setCompleter(completer)

    def on_item_selected(self, item_name):
        """When item is selected, auto-fill price and update stock info"""
        if item_name and item_name in self.item_map:
            id, price, stock = self.item_map[item_name]
            self.price_spin.setValue(price)
            self.qty_spin.setMaximum(min(999, stock))
            self.status_lbl.setText(f"Selected: {item_name} - Stock: {stock}")

    def add_to_cart(self):
        name = self.combo.currentText()
        if name not in self.item_map:
            QMessageBox.warning(self, "Input", "Select a valid item.")
            return

        id, price, stock = self.item_map[name]
        qty = self.qty_spin.value()

        # Check stock
        if qty > stock:
            QMessageBox.warning(self, "Stock", f"Not enough stock! Available: {stock}")
            return

        total = round(price * qty, 2)

        # Check if item already in cart
        for item in self.cart:
            if item["name"] == name:
                item["qty"] += qty
                item["total"] = round(item["price"] * item["qty"], 2)
                self.refresh_cart_table()
                self.qty_spin.setValue(1)
                self.status_lbl.setText(f"Updated {name} in cart")
                return

        # Add new item to cart
        self.cart.append({
            "id": id,
            "name": name,
            "price": price,
            "qty": qty,
            "total": total
        })
        self.refresh_cart_table()
        self.qty_spin.setValue(1)
        self.status_lbl.setText(f"Added {qty} × {name} to cart")

    def refresh_cart_table(self):
        self.cart_table.setRowCount(0)
        for row, item in enumerate(self.cart):
            self.cart_table.insertRow(row)
            self.cart_table.setItem(row, 0, QTableWidgetItem(item["name"]))
            self.cart_table.setItem(row, 1, QTableWidgetItem(f"₱{item['price']:.2f}"))
            self.cart_table.setItem(row, 2, QTableWidgetItem(str(item["qty"])))
            self.cart_table.setItem(row, 3, QTableWidgetItem(f"₱{item['total']:.2f}"))

            # Reduce quantity button (-1)
            reduce_btn = QPushButton("-1")
            reduce_btn.setFixedSize(60, 30)
            reduce_btn.setStyleSheet(
                "QPushButton{background:#ff9f1c;color:#000;border:none;border-radius:4px;font-size:12px;font-weight:bold;}QPushButton:hover{background:#ffb627;}")
            reduce_btn.clicked.connect(lambda _, r=row: self.reduce_quantity(r))
            self.cart_table.setCellWidget(row, 4, reduce_btn)

            # Remove item button
            del_btn = QPushButton("✖")
            del_btn.setFixedSize(60, 30)
            del_btn.setStyleSheet(
                "QPushButton{background:#e63946;color:#fff;border:none;border-radius:4px;font-weight:bold;}QPushButton:hover{background:#f77f00;}")
            del_btn.clicked.connect(lambda _, r=row: self.remove_row(r))
            self.cart_table.setCellWidget(row, 5, del_btn)

        self.update_total()

    def reduce_quantity(self, row):
        if 0 <= row < len(self.cart):
            item = self.cart[row]
            if item["qty"] > 1:
                # Reduce quantity by 1
                item["qty"] -= 1
                item["total"] = round(item["price"] * item["qty"], 2)
                self.status_lbl.setText(f"Reduced {item['name']} quantity to {item['qty']}")
            else:
                # Remove item if quantity becomes 0
                item_name = item["name"]
                del self.cart[row]
                self.status_lbl.setText(f"Removed {item_name} from cart")

            self.refresh_cart_table()

    def remove_row(self, row):
        if 0 <= row < len(self.cart):
            item_name = self.cart[row]["name"]
            del self.cart[row]
            self.refresh_cart_table()
            self.status_lbl.setText(f"Removed {item_name} from cart")

    def clear_cart(self):
        self.cart.clear()
        self.refresh_cart_table()
        self.status_lbl.setText("Cart cleared")

    def update_total(self):
        total = sum(item["total"] for item in self.cart)
        self.total_lbl.setText(f"₱ {total:,.2f}")

    def checkout(self):
        if not self.cart:
            QMessageBox.warning(self, "Cart", "Cart is empty.")
            return

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    for item in self.cart:
                        cur.execute("SELECT stock FROM items WHERE id = %s", (item["id"],))
                        result = cur.fetchone()
                        if not result or result[0] < item["qty"]:
                            raise RuntimeError(
                                f"Not enough stock for '{item['name']}'. Available: {result[0] if result else 0}"
                            )
        except RuntimeError as e:
            QMessageBox.warning(self, "Stock", str(e))
            return
        except Exception as e:
            QMessageBox.critical(self, "Database error", f"Stock check failed:\n{e}")
            return

        total = sum(item["total"] for item in self.cart)
        dlg = PaymentDialog(total, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        payment_method = dlg.method()
        final_total = dlg.final_total()
        discount_applied = dlg.discount_checked()
        cash_received = dlg.get_cash_amount() if payment_method == "Cash" else 0.0

        if payment_method == "Cash" and cash_received < final_total:
            QMessageBox.warning(
                self, "Payment error",
                f"Cash received (₱{cash_received:,.2f}) is less than total amount (₱{final_total:,.2f})"
            )
            return

        try:
            items_json = json.dumps(self.cart, default=str)  # Convert Decimal to string
            timestamp = datetime.datetime.now().replace(microsecond=0)

            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Insert sale record
                    cur.execute("""
                        INSERT INTO sales (cashier, sale_time, payment_method, total_amount, items_json, discount_applied)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (self.username, timestamp, payment_method, final_total, items_json, discount_applied))

                    # Update stock levels
                    for item in self.cart:
                        cur.execute("UPDATE items SET stock = stock - %s WHERE id = %s",
                                    (item["qty"], item["id"]))
        except Exception as e:
            QMessageBox.critical(self, "Database error", f"Failed to save sale: {str(e)}")

        self.cart.clear()
        self.refresh_cart_table()
        self._load_items()
        self._fill_item_combo()
        self.status_lbl.setText("Sale completed successfully!")


    def logout(self):
        if self.logout_callback:
            self.logout_callback()
        self.close()


# ----------  PAYMENT DIALOG WITH CASH/CARD AND DISCOUNT  ----------
class PaymentDialog(QDialog):
    def __init__(self, total_amount, parent=None):
        super().__init__(parent)
        self.total = Decimal(total_amount)  # Ensure total is a Decimal
        self.setWindowTitle("Payment")
        self.setFixedSize(400, 350)
        self.setStyleSheet("background:#1e1e1e;")

        v = QVBoxLayout(self)
        v.setContentsMargins(25, 25, 25, 25)

        # ---- total label ----
        self.total_lbl = QLabel(f"Total: ₱ {self.total:,.2f}")
        self.total_lbl.setStyleSheet("font-size:20px;color:#ffd166;font-weight:bold;")
        self.total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.total_lbl)

        # ---- discount ----
        self.discount_chk = QPushButton("Senior/PWD 20% OFF")
        self.discount_chk.setCheckable(True)
        self.discount_chk.setStyleSheet("""
            QPushButton{
                background:#2b2b2b;
                border:2px solid #444;
                border-radius:8px;
                padding:12px;
                color:#f8f9fa;
                font-size:14px;
                font-weight:bold;
            }
            QPushButton:checked{
                background:#ff9f1c;
                border-color:#ff9f1c;
                color:#000;
            }
        """)
        self.discount_chk.toggled.connect(self._update_ui)
        v.addWidget(self.discount_chk)

        # ---- discounted total ----
        self.discounted_lbl = QLabel("After discount: ₱ 0.00")
        self.discounted_lbl.setStyleSheet("font-size:16px;color:#06d6a0;font-weight:bold;")
        self.discounted_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.discounted_lbl)

        # ---- cash input ----
        cash_lay = QHBoxLayout()
        cash_lay.addWidget(QLabel("Cash received:"))
        self.cash_input = QDoubleSpinBox()
        self.cash_input.setPrefix("₱ ")
        self.cash_input.setRange(0.0, 999999)
        self.cash_input.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        self.cash_input.setStyleSheet("""
            background:#2b2b2b;
            border:2px solid #444;
            border-radius:6px;
            padding:8px;
            font-size:16px;
            color:#f8f9fa;
        """)
        self.cash_input.valueChanged.connect(self._update_ui)
        cash_lay.addWidget(self.cash_input)
        v.addLayout(cash_lay)

        # ---- change ----
        self.change_lbl = QLabel("Change: ₱ 0.00")
        self.change_lbl.setStyleSheet("font-size:18px;color:#06d6a0;font-weight:bold;")
        self.change_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.change_lbl)

        # ---- payment method ----
        method_layout = QVBoxLayout()
        method_label = QLabel("Payment Method:")
        method_label.setStyleSheet("color:#adb5bd;font-weight:bold;font-size:14px;")
        method_layout.addWidget(method_label)

        grid = QHBoxLayout()
        self.cash = QPushButton("Cash")
        self.cash.setCheckable(True)
        self.cash.setChecked(True)
        self.cash.setFixedHeight(45)
        self.cash.setStyleSheet("""
            QPushButton{
                background:#2b2b2b;
                border:2px solid #444;
                border-radius:8px;
                font-size:16px;
                color:#f8f9fa;
                font-weight:bold;
            }
            QPushButton:checked{
                background:#06d6a0;
                border-color:#06d6a0;
                color:#000;
            }
        """)
        self.card = QPushButton("Card")
        self.card.setCheckable(True)
        self.card.setFixedHeight(45)
        self.card.setStyleSheet("""
            QPushButton{
                background:#2b2b2b;
                border:2px solid #444;
                border-radius:8px;
                font-size:16px;
                color:#f8f9fa;
                font-weight:bold;
            }
            QPushButton:checked{
                background:#219ebc;
                border-color:#219ebc;
                color:#000;
            }
        """)
        grid.addWidget(self.cash)
        grid.addWidget(self.card)
        method_layout.addLayout(grid)
        v.addLayout(method_layout)

        grp = QButtonGroup(self)
        grp.addButton(self.cash)
        grp.addButton(self.card)

        # ---- buttons ----
        self.bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel |
                                   QDialogButtonBox.StandardButton.Ok)
        self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(False)
        self.bb.setStyleSheet("""
            QPushButton{
                background:#444;
                color:#fff;
                border:none;
                border-radius:6px;
                padding:10px 20px;
                font-weight:bold;
                font-size:14px;
            }
            QPushButton:hover{background:#555;}
        """)
        self.bb.rejected.connect(self.reject)
        self.bb.accepted.connect(self._on_accept)
        v.addWidget(self.bb)


        self.cash.toggled.connect(self.on_cash_toggled)
        self.card.toggled.connect(self.on_card_toggled)

    def _on_accept(self):
        final_total = self.final_total()

        if self.cash.isChecked():
            cash_received = self.cash_input.value()
            if cash_received <= 0:
                QMessageBox.warning(self, "Payment Error", "Please enter the cash amount received!")
                return
            if cash_received < final_total:
                QMessageBox.warning(self, "Payment Error",
                                    f"Cash received (₱{cash_received:,.2f}) is less than total amount (₱{final_total:,.2f})!")
                return
        self.accept()

    def _update_ui(self):
        final = self.final_total()

        if self.discount_chk.isChecked():
            discount_amount = self.total * Decimal('0.2')
            self.discounted_lbl.setText(f"After 20% discount: ₱ {(final):,.2f} (Save: ₱ {discount_amount:,.2f})")
            self.discounted_lbl.show()
        else:
            self.discounted_lbl.hide()

        if self.cash.isChecked():
            cash = Decimal(str(self.cash_input.value()))  # Convert float to Decimal
            change = cash - final
            self.change_lbl.setText(f"Change: ₱ {change:,.2f}")
            self.cash_input.setEnabled(True)
            # Set minimum cash amount to total when cash is selected
            self.cash_input.setMinimum(final)
        else:
            self.change_lbl.setText("Change: ₱ 0.00")
            self.cash_input.setEnabled(False)
            self.cash_input.setMinimum(0)
            self.cash_input.setValue(0.0)



    def final_total(self):
        if self.discount_chk.isChecked():
            return round(self.total * Decimal('0.8'), 2)  # Ensure this is a Decimal
        return self.total

    def method(self):
        return "Cash" if self.cash.isChecked() else "Card"

    def discount_checked(self):
        return self.cash_input.isEnabled() and self.discount_chk.isChecked()

    def get_cash_amount(self):
        return Decimal(str(self.cash_input.value()))  # Convert float to Decimal

    def on_cash_toggled(self, checked):
        if checked:
            self.cash_input.setValue(0.0)
            self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def on_card_toggled(self, checked):
        if checked:
            self.cash_input.setValue(0.0)
            self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

# ----------  LOGIN DISPATCHER  ----------
class CashierLoginDialog(QDialog):
    def __init__(self):
        super().__init__()  # FIXED: Removed the 'self' parameter
        self.setWindowTitle("Login – POS System")
        self.setFixedSize(360, 420)
        self.setStyleSheet("background:white;")
        v = QVBoxLayout(self)
        v.setContentsMargins(30, 25, 30, 25)
        self.user = QLineEdit()
        self.user.setStyleSheet("""
            QLineEdit{
                color: #000000;               /*  BLACK text  */
                background: #ffffff;          /*  white field */
                border: 1px solid #ced4da;
                border-radius: 6px;
                padding: 8px;
                font-size: 15px;
            }
        """)

        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.EchoMode.Password)
        self.pw.setStyleSheet("""
            QLineEdit{
                color: #000000;
                background: #ffffff;
                border: 1px solid #ced4da;
                border-radius: 6px;
                padding: 8px;
                font-size: 15px;
            }
        """)
        logo = QLabel()
        logo.setPixmap(
            QPixmap(r"C:\Users\Blue\Downloads\Untitled-1.png").scaled(150, 140, Qt.AspectRatioMode.KeepAspectRatio,
                                                                      Qt.TransformationMode.SmoothTransformation))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(logo)

        label_style = """
                    QLabel{
                        color: #000000;          /* black text */
                        background: transparent;
                        font-size: 15px;
                    }
                """

        user_lbl = QLabel("Username")
        user_lbl.setStyleSheet(label_style)
        v.addWidget(user_lbl)
        v.addWidget(self.user)

        pw_lbl = QLabel("Password")
        pw_lbl.setStyleSheet(label_style)
        v.addWidget(pw_lbl)
        v.addWidget(self.pw)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.setStyleSheet("""
            QPushButton{background:#007bff;color:white;border:none;border-radius:6px;padding:8px 24px;font-size:15px;font-weight:bold;}
            QPushButton:hover{background:#0069d9;}
        """)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)

    def creds(self):
        return self.user.text().strip(), self.pw.text().strip()

class CashierApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self._win = None
        self._show_login()

    def _show_login(self):
        if self._win:
            self._win.close()
            self._win = None
        dlg = CashierLoginDialog()
        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.quit()
            return
        user, pwd = dlg.creds()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM users WHERE username=%s AND password=SHA2(%s,256) AND role='cashier'", (user, pwd))
                if cur.fetchone():
                    self._win = CashierWindow(user, logout_callback=self._show_login)
                    self._win.show()
                    return
                cur.execute("SELECT 1 FROM users WHERE username=%s AND password=SHA2(%s,256) AND role='admin'", (user, pwd))
                if cur.fetchone():
                    self._win = AdminWindow(user, logout_callback=self._show_login)
                    self._win.show()
                    return
                cur.execute("SELECT 1 FROM managers WHERE username=%s AND password=SHA2(%s,256)", (user, pwd))
                if cur.fetchone():
                    self._win = ManagerWindow(user, logout_callback=self._show_login)
                    self._win.show()
                    return
                QMessageBox.critical(None, "Login", "Invalid credentials.")
                self._show_login()

if __name__ == "__main__":
    app = CashierApp(sys.argv)
    app.setStyleSheet("QWidget { background-color: #d3d3d3; }")
    sys.exit(app.exec())