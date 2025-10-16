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
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT id, name, price, stock FROM items WHERE stock > 0 ORDER BY name")
                items = cur.fetchall()
                return items
    except Exception as e:
        print(f"Error fetching items: {e}")
        return []

def sql_sum(where, params):
    sql = f"SELECT COALESCE(SUM(total_amount),0) FROM sales WHERE {where}"
    print(f"DEBUG: Executing SQL: {sql} with params: {params}")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = float(cur.fetchone()[0])
            print(f"DEBUG: SQL result: {result}")
            return result

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

class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #f8f9fa;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 2, 0)
        layout.setSpacing(10)
        self._last_top = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_top_cashier)
        self._timer.start(30000)

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

        grid_container = QWidget()
        grid_container.setStyleSheet("background-color: transparent;")
        grid_layout = QVBoxLayout(grid_container)
        grid_layout.setSpacing(0)
        grid_layout.setContentsMargins(4, 3, 3, 4)

        self.rect_widgets = []
        idx = 0
        for r in range(2):
            row_widget = QWidget()
            row_widget.setStyleSheet("background-color: transparent;")
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
        self._build_refresh_button_only()
        layout.addStretch()

    def set_username(self, name):
        pass

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
            msg = QMessageBox(self)
            msg.setWindowTitle("Top Cashier Notification")
            msg.setText(f"🏆 <b>Top Cashier Today</b><br><br>"
                        f"👤 {top_name}<br>"
                        f"💰 Total Sales: ₱{top_sales:,.2f}")
            msg.setStyleSheet("""
                QMessageBox {
                    background-color: white;
                    color: #333333;
                }
                QMessageBox QLabel {
                    color: #333333;
                    font-size: 14px;
                }
            """)
            msg.exec()

    def _build_refresh_button_only(self):
        refresh_container = QWidget()
        refresh_container.setFixedHeight(50)
        refresh_container.setStyleSheet("""
            background-color: transparent;
        """)
        h_layout = QHBoxLayout(refresh_container)
        h_layout.setContentsMargins(15, 10, 15, 10)
        h_layout.addStretch()

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
        h_layout.addWidget(refresh_btn)

        self.layout().addWidget(refresh_container)

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
                cur.execute("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'items' AND column_name = 'created_at'
                """)
                has_created_at = cur.fetchone()[0] > 0

                if has_created_at:
                    cur.execute("SELECT COUNT(*) FROM items WHERE DATE(created_at) = %s", (today,))
                else:
                    try:
                        cur.execute("ALTER TABLE items ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                        print("Added created_at column to items table")
                        cur.execute("SELECT COUNT(*) FROM items WHERE DATE(created_at) = %s", (today,))
                    except Exception as e:
                        print(f"Error adding created_at column: {e}")
                        cur.execute("SELECT COUNT(*) FROM items")
                new_products_result = cur.fetchone()
                new_products = new_products_result[0] if new_products_result else 0

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

class ProcessSalesPage(QWidget):
    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(9, 9, 9, 9)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 6)

        self.search_le = QLineEdit()
        self.search_le.setFixedWidth(200)
        self.search_le.setPlaceholderText("Search…")
        self.search_le.setStyleSheet("background-color:#219ebc; border:1px solid #999; color: #ffffff;")
        top_bar.addWidget(self.search_le)

        self.filter_cb = QComboBox()
        self.filter_cb.setFixedWidth(150)
        self.filter_cb.addItems(["All", "Cash", "Card"])
        self.filter_cb.setStyleSheet("background-color:#219ebc; border:1px solid #999; color: #ffffff;")
        top_bar.addWidget(self.filter_cb)

        self.date_pick = QDateEdit()
        self.date_pick.setDate(datetime.date.today())
        self.date_pick.setCalendarPopup(True)
        self.date_pick.setDisplayFormat("yyyy-MM-dd")
        self.date_pick.setStyleSheet("""
            QDateEdit { 
                color: #ffffff; 
                background: #1976d2; 
                border: 1px solid #1565c0; 
                padding: 3px; 
                border-radius: 4px;
            }
            QDateEdit::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 25px;
                border-left-width: 1px;
                border-left-color: #1565c0;
                border-left-style: solid;
                border-top-right-radius: 3px;
                border-bottom-right-radius: 3px;
                background: #1976d2;
            }
            QDateEdit::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #ffffff;
            }
            QCalendarWidget QToolButton {
                color: #ffffff;
                background: #1976d2;
                font-weight: bold;
            }
            QCalendarWidget QMenu {
                background: #1976d2;
                color: #ffffff;
            }
            QCalendarWidget QSpinBox {
                background: #1976d2;
                color: #ffffff;
                selection-background-color: #1565c0;
            }
            QCalendarWidget QWidget { 
                alternate-background-color: #1976d2; 
            }
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
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Cashier", "Date / time", "Grand total", "Payment method"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.setStyleSheet("""
            QHeaderView::section{ background:#000; color:#fff; }
            QTableWidget{ color:#000; background: white; }
        """)
        outer.addWidget(self.table)
        refresh_btn.clicked.connect(self.load_sales)
        self.filter_cb.currentTextChanged.connect(self.load_sales)
        self.search_le.textChanged.connect(self.load_sales)
        self.date_pick.dateChanged.connect(self.load_sales)
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
            SELECT cashier, sale_time, total_amount, payment_method
            FROM sales
            WHERE DATE(sale_time) = %s
              AND (cashier LIKE %s)
        """
        params = [selected_date, f"%{search}%"]
        if pay_filter != "All":
            sql += " AND payment_method = %s"
            params.append(pay_filter)
        sql += " ORDER BY sale_time DESC LIMIT 200"

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                for cashier, ts, total, pay in cur.fetchall():
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    self.table.setItem(row, 0, QTableWidgetItem(cashier))
                    self.table.setItem(row, 1, QTableWidgetItem(ts.strftime("%Y-%m-%d %H:%M")))
                    self.table.setItem(row, 2, QTableWidgetItem(f"₱{total:,.2f}"))
                    self.table.setItem(row, 3, QTableWidgetItem(pay))

class SaleReportPage(QWidget):
    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 20, 20, 20)
        self.setStyleSheet("background-color: #f5f5f5;")

        title = QLabel("Sale Report")
        title.setStyleSheet("font-size:20px; font-weight:bold; color:#333; padding:10px;")
        v.addWidget(title)
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
        self.charts_tab = QWidget()
        self.charts_tab.setStyleSheet("background-color: #f5f5f5;")
        charts_layout = QVBoxLayout(self.charts_tab)
        self._setup_qt_charts(charts_layout)
        self.tab_widget.addTab(self.charts_tab, "📈 Sales Analytics")
        QTimer.singleShot(100, self._load_data)

    def _setup_qt_charts(self, layout):
        charts_container = QWidget()
        charts_container.setStyleSheet("background-color: #f5f5f5;")
        charts_layout = QHBoxLayout(charts_container)
        charts_layout.setSpacing(20)
        profit_widget = QWidget()
        profit_widget.setStyleSheet("background-color: #f5f5f5;")
        profit_layout = QVBoxLayout(profit_widget)
        profit_title = QLabel("Daily Sales Comparison")
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
        try:
            print("DEBUG: Starting _load_data")

            today = datetime.date.today()
            yesterday = today - datetime.timedelta(days=1)
            year_start = today.replace(month=1, day=1)
            print(f"DEBUG: Date ranges - Today: {today}, Year: {year_start}")
            daily_sales = self._get_sales_sum("DATE(sale_time) = %s", (today,))
            yesterday_sales = self._get_sales_sum("DATE(sale_time) = %s", (yesterday,))
            year_sales = self._get_sales_sum("sale_time >= %s", (year_start,))
            print(f"DEBUG: Sales data - Daily: {daily_sales}, Yesterday: {yesterday_sales}, Yearly: {year_sales}")
            cash_today = self._get_sales_sum("payment_method = 'Cash' AND DATE(sale_time) = %s", (today,))
            card_today = self._get_sales_sum("payment_method = 'Card' AND DATE(sale_time) = %s", (today,))

            self._update_profit_chart(daily_sales, yesterday_sales)
            self._update_payment_chart(cash_today, card_today)

            print("DEBUG: _load_data completed successfully")

        except Exception as e:
            print(f"DEBUG: Error in _load_data: {e}")
            import traceback
            traceback.print_exc()

    def _get_sales_sum(self, where_clause, params):
        try:
            sql = f"SELECT COALESCE(SUM(total_amount), 0) FROM sales WHERE {where_clause}"
            print(f"DEBUG: Executing SQL: {sql} with params: {params}")

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    result = cur.fetchone()
                    amount = float(result[0]) if result else 0.0
                    print(f"DEBUG: SQL result: {amount}")
                    return amount
        except Exception as e:
            print(f"DEBUG: Error in _get_sales_sum: {e}")
            return 0.0

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self._load_data)

    def _update_profit_chart(self, today_sales, yesterday_sales):
        data = {'Yesterday': yesterday_sales, 'Today': today_sales}
        self.profit_chart.setData(data, "Daily Sales Comparison")
        self.profit_chart.update()

    def _update_payment_chart(self, cash_amount, card_amount):
        data = {'Cash': cash_amount, 'Card': card_amount}
        self.payment_chart.setData(data, "Payment Methods – Today")
        self.payment_chart.update()

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
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            width = self.width()
            height = self.height()
            painter.fillRect(0, 0, width, height, QColor(255, 255, 255))
            painter.setPen(QPen(QColor(200, 200, 200), 2))
            painter.drawRect(1, 1, width - 2, height - 2)
            if not self.data:
                painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                painter.setPen(QColor(100, 100, 100))
                painter.drawText(QRectF(0, height / 2 - 15, width, 30), Qt.AlignmentFlag.AlignCenter,
                                 "No data available")
                return
            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(QRectF(0, 15, width, 25), Qt.AlignmentFlag.AlignCenter, self.title)
            chart_margin = 60
            chart_width = width - 2 * chart_margin
            chart_height = height - 100
            chart_bottom = height - 40

            max_value = max(self.data.values()) if self.data else 1
            if max_value == 0:
                max_value = 1
            bar_width = chart_width / (len(self.data) * 2)
            spacing = bar_width / 2
            colors = [QColor(255, 153, 153), QColor(102, 179, 255)]  # Red, Blue

            for i, (label, value) in enumerate(self.data.items()):
                bar_height = (value / max_value) * chart_height
                x = chart_margin + i * (bar_width + spacing)
                y = chart_bottom - bar_height
                color = colors[i % len(colors)]
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawRect(QRectF(x, y, bar_width, bar_height))

                if value > 0:
                    painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                    painter.setPen(QColor(0, 0, 0))
                    value_text = f"₱{value:,.0f}"
                    painter.drawText(QRectF(x, y - 20, bar_width, 20), Qt.AlignmentFlag.AlignCenter, value_text)

                painter.setFont(QFont("Arial", 10, QFont.Weight.Normal))
                painter.setPen(QColor(0, 0, 0))
                painter.drawText(QRectF(x, chart_bottom + 5, bar_width, 20), Qt.AlignmentFlag.AlignCenter, label)

            painter.setFont(QFont("Arial", 8))
            painter.setPen(QColor(100, 100, 100))
            for i in range(5):
                y_value = chart_bottom - (i * chart_height / 4)
                value = (i * max_value / 4)
                value_text = f"₱{value:,.0f}"
                painter.drawText(QRectF(5, y_value - 10, chart_margin - 10, 20),
                                 Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, value_text)

            painter.setPen(QPen(QColor(220, 220, 220), 1))
            for i in range(1, 5):
                y = chart_bottom - (i * chart_height / 4)
                painter.drawLine(chart_margin, y, width - chart_margin, y)

        except Exception as e:
            print(f"Error painting bar chart: {e}")

class SimplePieChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {}
        self.title = ""
        self.setMinimumSize(380, 280)

    def setData(self, data, title):
        self.data = {k: v for k, v in data.items() if v > 0}
        self.title = title

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def paintEvent(self, event):
        try:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            width = self.width()
            height = self.height()
            painter.fillRect(0, 0, width, height, QColor(255, 255, 255))
            painter.setPen(QPen(QColor(200, 200, 200), 2))
            painter.drawRect(1, 1, width - 2, height - 2)

            if not self.data:
                painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                painter.setPen(QColor(100, 100, 100))
                painter.drawText(QRectF(0, height / 2 - 15, width, 30), Qt.AlignmentFlag.AlignCenter, "No payment data")
                return


            painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
            painter.setPen(QColor(0, 0, 0))
            painter.drawText(QRectF(0, 15, width, 25), Qt.AlignmentFlag.AlignCenter, self.title)
            total = sum(self.data.values())
            pie_diameter = min(width - 100, height - 100)
            pie_radius = pie_diameter / 2
            center_x = width / 2
            center_y = height / 2 + 10
            colors = [QColor(255, 153, 153), QColor(102, 179, 255)]
            start_angle = 0
            for i, (label, value) in enumerate(self.data.items()):
                angle = (value / total) * 360 * 16
                color = colors[i % len(colors)]
                painter.setBrush(QBrush(color))
                painter.setPen(QPen(QColor(0, 0, 0), 1))
                painter.drawPie(QRectF(center_x - pie_radius, center_y - pie_radius,
                                       pie_diameter, pie_diameter), start_angle, angle)
                mid_angle = start_angle + angle / 2
                mid_angle_rad = math.radians(mid_angle / 16)
                label_radius = pie_radius + 25
                label_x = center_x + label_radius * math.cos(mid_angle_rad)
                label_y = center_y - label_radius * math.sin(mid_angle_rad)
                percentage = (value / total) * 100
                label_text = f"{label}\n{percentage:.1f}%"
                painter.setFont(QFont("Arial", 9, QFont.Weight.Bold))
                painter.setPen(QColor(0, 0, 0))
                text_rect = QRectF(label_x - 40, label_y - 20, 80, 40)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label_text)
                start_angle += angle

            painter.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            painter.setPen(QColor(0, 0, 0))
            total_text = f"Total:\n₱{total:,.0f}"
            painter.drawText(QRectF(center_x - 40, center_y - 20, 80, 40),
                             Qt.AlignmentFlag.AlignCenter, total_text)

        except Exception as e:
            print(f"Error painting pie chart: {e}")

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

        self.fig = self.Figure(figsize=(8, 6), dpi=100)
        self.canvas = self.FigureCanvas(self.fig)
        self.axes = self.fig.add_subplot(111)
        self.y_btn = QPushButton("Year View")
        self.m_btn = QPushButton("Month View")
        self.d_btn = QPushButton("Year Comparison")
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
        self.y_btn.clicked.connect(self.show_year)
        self.m_btn.clicked.connect(self.show_month)
        self.d_btn.clicked.connect(self.show_comparison)
        self.btn_group = QButtonGroup(self)
        self.btn_group.addButton(self.y_btn)
        self.btn_group.addButton(self.m_btn)
        self.btn_group.addButton(self.d_btn)
        self.btn_group.setExclusive(True)
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.y_btn)
        button_layout.addWidget(self.m_btn)
        button_layout.addWidget(self.d_btn)
        button_layout.addStretch()
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self.canvas, 1)
        main_layout.addLayout(button_layout)
        self.show_year()

    def _sales_for_year(self, year):
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

        monthly_sales = {month: 0.0 for month in range(1, 13)}
        for month_num, total in results:
            monthly_sales[month_num] = float(total)

        labels = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
        values = [monthly_sales[month] for month in range(1, 13)]
        return labels, values

    def _sales_for_month(self, year, month):
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
        _, num_days = monthrange(year, month)
        daily_sales = {day: 0.0 for day in range(1, num_days + 1)}
        for day_num, total in results:
            daily_sales[day_num] = float(total)

        labels = [str(day) for day in range(1, num_days + 1)]
        values = [daily_sales[day] for day in range(1, num_days + 1)]

        return labels, values

    def show_year(self):
        if not self.matplotlib_available:
            return

        current_year = datetime.date.today().year
        labels, values = self._sales_for_year(current_year)
        self.axes.clear()
        bars = self.axes.bar(labels, values, color='skyblue', edgecolor='navy', alpha=0.7)
        for bar, value in zip(bars, values):
            if value > 0:
                height = bar.get_height()
                self.axes.text(bar.get_x() + bar.get_width() / 2., height + max(values) * 0.01,
                               f'₱{value:,.0f}', ha='center', va='bottom', fontsize=9)

        self.axes.set_title(f'Sales Overview - {current_year}', fontsize=14, fontweight='bold')
        self.axes.set_ylabel('Sales Amount (₱)', fontweight='bold')
        self.axes.set_xlabel('Month', fontweight='bold')
        self.axes.grid(True, alpha=0.3)
        self.axes.tick_params(axis='x', rotation=45)
        self.fig.tight_layout()
        self.canvas.draw()

    def show_month(self):
        if not self.matplotlib_available:
            return

        today = datetime.date.today()
        labels, values = self._sales_for_month(today.year, today.month)
        self.axes.clear()
        bars = self.axes.bar(labels, values, color='lightgreen', edgecolor='darkgreen', alpha=0.7)
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
        self.axes.tick_params(axis='x', rotation=45)
        self.fig.tight_layout()
        self.canvas.draw()

    def show_comparison(self):
        if not self.matplotlib_available:
            return
        current_year = datetime.date.today().year
        previous_year = current_year - 1
        labels, current_values = self._sales_for_year(current_year)
        _, previous_values = self._sales_for_year(previous_year)
        self.axes.clear()
        bar_width = 0.35
        x_pos = self.np.arange(len(labels))

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
        self.axes.tick_params(axis='x', rotation=45)
        self.fig.tight_layout()
        self.canvas.draw()

class AdminWindow(QMainWindow):
    logout_requested = pyqtSignal()

    def __init__(self, username: str, logout_callback):
        super().__init__()
        self.username = username
        self.logout_callback = logout_callback
        self.setWindowTitle(f"Admin Portal – {username}")
        self.resize(1200, 700)
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
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
                 "📋  Sale Report", "📜  Sale History",
                 "👥  Create User", "🚪  Logout"]
        btn_group = QButtonGroup(self)
        btn_group.setExclusive(True)
        self.buttons = []

        for i, n in enumerate(names):
            b = QPushButton(n)
            b.setCheckable(i < 5)
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

        content = QWidget()
        content.setStyleSheet("background-color: #f5f5f5;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget = QStackedWidget()
        content_layout.addWidget(self.stacked_widget)
        self.dashboard_page = DashboardPage()
        self.dashboard_page.set_username(username)
        self.process_sales_page = ProcessSalesPage()
        self.sale_report_page = SaleReportPage()
        self.sale_history_page = SaleHistoryPage()
        self.create_user_page = CreateUserPage()

        self.stacked_widget.addWidget(self.dashboard_page)
        self.stacked_widget.addWidget(self.process_sales_page)
        self.stacked_widget.addWidget(self.sale_report_page)
        self.stacked_widget.addWidget(self.sale_history_page)
        self.stacked_widget.addWidget(self.create_user_page)
        root.addWidget(sidebar)
        root.addWidget(content, 1)
        btn_group.buttonClicked.connect(self._on_nav)
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
            if hasattr(self.sale_history_page, 'graph') and self.sale_history_page.graph.matplotlib_available:
                self.sale_history_page.graph.show_year()
        elif "Create User" in txt:
            self.stacked_widget.setCurrentIndex(4)
        elif "Logout" in txt:
            if self.logout_callback:
                self.logout_callback()
            self.close()

class CreateUserPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setStyleSheet("background-color: #f8f9fa;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(25)
        title = QLabel("Create New User")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #333;")
        layout.addWidget(title)
        form_card = QFrame()
        form_card.setStyleSheet("""
            QFrame{
                background: white;
                border: 2px solid #e0e0e0;
                border-radius: 12px;
                padding: 30px;
            }
        """)
        form_layout = QVBoxLayout(form_card)
        form_layout.setSpacing(20)
        username_layout = QHBoxLayout()
        username_label = QLabel("Username:")
        username_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; min-width: 120px;")
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username...")
        self.username_input.setStyleSheet("""
            QLineEdit{
                background: white;
                color: #333;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
                font-size: 15px;
            }
            QLineEdit:focus{
                border-color: #1976d2;
            }
        """)
        username_layout.addWidget(username_label)
        username_layout.addWidget(self.username_input)
        form_layout.addLayout(username_layout)
        password_layout = QHBoxLayout()
        password_label = QLabel("Password:")
        password_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; min-width: 120px;")
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password...")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setStyleSheet("""
            QLineEdit{
                background: white;
                color: #333;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
                font-size: 15px;
            }
            QLineEdit:focus{
                border-color: #1976d2;
            }
        """)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        form_layout.addLayout(password_layout)
        role_layout = QHBoxLayout()
        role_label = QLabel("Role:")
        role_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #333; min-width: 120px;")
        self.role_combo = QComboBox()
        self.role_combo.addItems(["Cashier", "Manager", "Admin"])
        self.role_combo.setStyleSheet("""
            QComboBox{
                background: white;
                color: #333;
                border: 2px solid #e0e0e0;
                border-radius: 8px;
                padding: 12px;
                font-size: 15px;
            }
            QComboBox:focus{
                border-color: #1976d2;
            }
            QComboBox QAbstractItemView {
                background: white;
                border: 1px solid #e0e0e0;
                selection-background-color: #1976d2;
                color: #333;
            }
        """)
        role_layout.addWidget(role_label)
        role_layout.addWidget(self.role_combo)
        form_layout.addLayout(role_layout)
        create_btn_layout = QHBoxLayout()
        create_btn_layout.addStretch()
        self.create_btn = QPushButton("Create User")
        self.create_btn.setFixedSize(150, 45)
        self.create_btn.setStyleSheet("""
            QPushButton{
                background: #06d6a0;
                color: black;
                border: none;
                border-radius: 8px;
                font-weight: bold;
                font-size: 16px;
            }
            QPushButton:hover{
                background: #0affc2;
            }
            QPushButton:disabled{
                background: #cccccc;
                color: #666666;
            }
        """)
        self.create_btn.clicked.connect(self.create_user)
        create_btn_layout.addWidget(self.create_btn)
        form_layout.addLayout(create_btn_layout)

        layout.addWidget(form_card)
        layout.addStretch()

        self.username_input.textChanged.connect(self.validate_inputs)
        self.password_input.textChanged.connect(self.validate_inputs)

    def validate_inputs(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        self.create_btn.setEnabled(bool(username and password))

    def create_user(self):
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        role = self.role_combo.currentText()

        if not username or not password:
            self._show_message("Input Required",
                               "Please enter both username and password.",
                               QMessageBox.Icon.Warning)
            return

        if len(username) < 3:
            self._show_message("Invalid Username",
                               "Username must be at least 3 characters long.",
                               QMessageBox.Icon.Warning)
            return

        if len(password) < 4:
            self._show_message("Weak Password",
                               "Password must be at least 4 characters long.",
                               QMessageBox.Icon.Warning)
            return

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT username FROM users WHERE username = %s", (username,))
                    if cur.fetchone():
                        self._show_message("User Already Exists",
                                           f"Username '{username}' is already taken.\n\nPlease choose a different username.",
                                           QMessageBox.Icon.Warning)
                        return

                    cur.execute("SELECT username FROM managers WHERE username = %s", (username,))
                    if cur.fetchone():
                        self._show_message("User Already Exists",
                                           f"Username '{username}' is already taken.\n\nPlease choose a different username.",
                                           QMessageBox.Icon.Warning)
                        return

                    if role == "Admin" or role == "Cashier":
                        cur.execute("""
                            INSERT INTO users (username, password, role) 
                            VALUES (%s, SHA2(%s, 256), %s)
                        """, (username, password, role.lower()))

                        if role == "Admin":
                            message = (
                                f"✅ <b>Admin User Created Successfully!</b><br><br>"
                                f"👤 <b>Username:</b> {username}<br>"
                                f"🔑 <b>Role:</b> Administrator<br><br>"
                                f"This user can now login to the Admin Portal."
                            )
                        else:
                            message = (
                                f"✅ <b>Cashier User Created Successfully!</b><br><br>"
                                f"👤 <b>Username:</b> {username}<br>"
                                f"🔑 <b>Role:</b> Cashier<br><br>"
                                f"This user can now login to the Cashier POS system."
                            )

                    elif role == "Manager":
                        cur.execute("""
                            INSERT INTO managers (username, password) 
                            VALUES (%s, SHA2(%s, 256))
                        """, (username, password))
                        message = (
                            f"✅ <b>Manager User Created Successfully!</b><br><br>"
                            f"👤 <b>Username:</b> {username}<br>"
                            f"🔑 <b>Role:</b> Manager<br><br>"
                            f"This user can now login to the Manager Portal."
                        )

                    self._show_message("User Created", message, QMessageBox.Icon.Information)
                    self.username_input.clear()
                    self.password_input.clear()
                    self.role_combo.setCurrentIndex(0)
                    self.create_btn.setEnabled(False)

        except Exception as e:
            error_message = (
                f"❌ <b>Failed to Create User</b><br><br>"
                f"An error occurred while creating the user account:<br>"
                f"<code>{str(e)}</code><br><br>"
                f"Please check the database connection and try again."
            )
            self._show_message("Database Error", error_message, QMessageBox.Icon.Critical)

    def _show_message(self, title, message, icon):
        """Show a styled message box with consistent formatting"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(message)
        msg_box.setIcon(icon)
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: white;
                color: #333333;
            }
            QMessageBox QLabel {
                color: #333333;
                font-size: 14px;
            }
            QMessageBox QPushButton {
                background-color: #1976d2;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
                min-width: 80px;
            }
            QMessageBox QPushButton:hover {
                background-color: #1565c0;
            }
        """)
        if icon == QMessageBox.Icon.Information:
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)
        else:
            msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg_box.setDefaultButton(QMessageBox.StandardButton.Ok)

        msg_box.exec()

class ManagerWindow(QMainWindow):
    def __init__(self, username, logout_callback):
        super().__init__()
        self.username = username
        self.logout_callback = logout_callback
        self.setWindowTitle(f"Manager Portal – {username}")
        self.resize(1200, 800)
        central = QWidget()
        central.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
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
        self.refund_page = self.build_manager_refund()
        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.inventory_page)
        self.stack.addWidget(self.sales_page)
        self.stack.addWidget(self.refund_page)

        self.grp.buttonClicked.connect(self.nav)
        self.grp.buttons()[0].setChecked(True)
        self.stack.setCurrentIndex(0)
        self.current_transaction_id = None
        self.current_transaction_items = []
        self._ensure_created_at_column()

    def _ensure_created_at_column(self):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_name = 'items' AND column_name = 'created_at'
                    """)
                    has_created_at = cur.fetchone()[0] > 0

                    if not has_created_at:
                        cur.execute("ALTER TABLE items ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                        print("Added created_at column to items table")
        except Exception as e:
            print(f"Error ensuring created_at column exists: {e}")

    def build_manager_inventory(self):
        w = QWidget()
        w.setStyleSheet("background-color: #2b2b2b; color: #ffffff;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 30, 30, 30)

        title = QLabel("Inventory Management")
        title.setStyleSheet("font-size:22px;font-weight:bold;color:#ffffff;background-color:transparent;")
        lay.addWidget(title)
        add_section = QWidget()
        add_section.setStyleSheet("background:#3c3c3c; border:1px solid #555; border-radius:10px; padding:15px;")
        add_layout = QVBoxLayout(add_section)
        add_title = QLabel("Add New Item")
        add_title.setStyleSheet("font-size:16px; font-weight:bold; color:#ffffff;")
        add_layout.addWidget(add_title)
        form_layout = QHBoxLayout()
        self.new_item_name = QLineEdit()
        self.new_item_name.setPlaceholderText("Item Name")
        self.new_item_name.setStyleSheet(
            "background:white; color:black; border:1px solid #ccc; border-radius:5px; padding:8px;")

        self.new_item_price = QLineEdit()
        self.new_item_price.setPlaceholderText("0.00")
        self.new_item_price.setValidator(QDoubleValidator(0.01, 999999.99, 2))
        self.new_item_price.setStyleSheet(
            "background:white; color:black; border:1px solid #ccc; border-radius:5px; padding:8px;")

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

        self.stock_input = QLineEdit()
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

    def add_new_item(self):
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
                    cur.execute("SELECT id FROM items WHERE name = %s", (name,))
                    if cur.fetchone():
                        QMessageBox.warning(self, "Duplicate Item",
                                            f"Item '{name}' already exists in the database.")
                        return

                    cur.execute("""
                        INSERT INTO items (name, price, stock, created_at) 
                        VALUES (%s, %s, %s, NOW())
                    """, (name, price, stock))

            QMessageBox.information(self, "Success",
                                    f"Item '{name}' added successfully!\n"
                                    f"Price: ₱{price:.2f}\n"
                                    f"Stock: {stock}")

            self.new_item_name.clear()
            self.new_item_price.clear()
            self.new_item_stock.clear()
            self.load_inventory_table()
            self.fill_inventory_combo()

        except Exception as e:
            QMessageBox.critical(self, "Database Error",
                                 f"Failed to add item: {str(e)}")

    def build_manager_refund(self):
        w = QWidget()
        w.setStyleSheet("background-color: #2b2b2b;")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 20, 30, 20)
        lay.setSpacing(15)

        # 1.  BIG TITLE
        title = QLabel("REFUND")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:32px;font-weight:bold;color:#ffffff;")
        lay.addWidget(title)

        # 2.  STEP 1 CARD  (dark)
        step1 = QFrame()
        step1.setObjectName("card")
        step1.setStyleSheet("""
            QFrame#card{
                background:#3c3c3c;
                border:2px solid #1976d2;
                border-radius:12px;
                padding:15px;
            }
        """)
        h1 = QHBoxLayout(step1)
        h1.addWidget(QLabel("1.  Type the Receipt Number:"), alignment=Qt.AlignmentFlag.AlignVCenter)
        self.refund_search = QLineEdit()
        self.refund_search.setPlaceholderText("e.g. 12345")
        self.refund_search.setStyleSheet("font-size:18px;padding:8px;border:1px solid #bbb;border-radius:6px;")
        self.refund_search.setFixedWidth(180)
        search_btn = QPushButton("Find Receipt")
        search_btn.setFixedSize(140, 42)
        search_btn.setStyleSheet("""
            QPushButton{
                background:#06d6a0;
                color:black;
                border:none;
                border-radius:6px;
                font-size:16px;
                font-weight:bold;
            }
            QPushButton:hover{background:#0affc2;}
        """)
        search_btn.clicked.connect(self.search_transaction)
        h1.addWidget(self.refund_search)
        h1.addWidget(search_btn)
        h1.addStretch()
        lay.addWidget(step1)

        # 3.  STEP 2 CARD  (hidden until receipt found)
        self.step2 = QFrame()
        self.step2.setObjectName("card")
        self.step2.setStyleSheet(step1.styleSheet() + "border-color:#ff9800;")
        self.step2.hide()
        v2 = QVBoxLayout(self.step2)

        v2.addWidget(QLabel("2.  Tick the items to return:"), alignment=Qt.AlignmentFlag.AlignLeft)

        # ----  table  ----
        self.refund_table = QTableWidget(0, 5)
        self.refund_table.setHorizontalHeaderLabels(["Item", "Price", "Qty Bought", "Return Qty", "Refund"])
        self.refund_table.horizontalHeader().setStretchLastSection(True)
        self.refund_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.refund_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.refund_table.setStyleSheet("""
            QTableWidget{
                font-size:15px;
                border:1px solid #ddd;
                border-radius:6px;
            }
            QHeaderView::section{
                background:#ff9800;
                color:white;
                font-size:15px;
                padding:6px;
                font-weight:bold;
            }
        """)
        self.refund_table.setMinimumHeight(250)
        v2.addWidget(self.refund_table)

        # ----  big green refund button  ----
        self.big_refund_btn = QPushButton("GIVE REFUND")
        self.big_refund_btn.setEnabled(False)
        self.big_refund_btn.setFixedHeight(60)
        self.big_refund_btn.setStyleSheet("""
            QPushButton{
                background:#06d6a0;
                color:black;
                border:none;
                border-radius:10px;
                font-size:22px;
                font-weight:bold;
            }
            QPushButton:hover{background:#0affc2;}
            QPushButton:disabled{background:#ccc;color:#666;}
        """)
        self.big_refund_btn.clicked.connect(self.process_refund)
        v2.addWidget(self.big_refund_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        lay.addWidget(self.step2)

        # ----------  STATE  ----------
        self.current_transaction_id = None
        self.current_transaction_items = []

        return w

    # ----------  NEW HELPERS  ----------
    def search_transaction(self):
        tx = self.refund_search.text().strip()
        if not tx:
            QMessageBox.information(self, "Oops", "Please type the receipt number first.")
            return

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT cashier, sale_time, total_amount, items_json
                        FROM sales
                        WHERE id=%s
                    """, (tx,))
                    row = cur.fetchone()
                    if not row:
                        QMessageBox.information(self, "Not Found", "Receipt number not found.")
                        return
                    cashier, sale_time, total, items_json = row
                    self.current_transaction_id = tx
                    self.current_transaction_items = json.loads(items_json)

                    # fill table
                    self.refund_table.setRowCount(0)
                    for idx, item in enumerate(self.current_transaction_items):
                        r = self.refund_table.rowCount()
                        self.refund_table.insertRow(r)

                        # ----  original purchase qty  ----
                        bought_qty = int(item["qty"])

                        # ----  build items  ----
                        self.refund_table.setItem(r, 0, QTableWidgetItem(item["name"]))
                        self.refund_table.setItem(r, 1, QTableWidgetItem(f"₱{float(item['price']):.2f}"))
                        self.refund_table.setItem(r, 2, QTableWidgetItem(str(bought_qty)))

                        # ----  refund qty editor  ----
                        spin = QSpinBox()
                        spin.setRange(0, bought_qty)
                        spin.setValue(0)
                        spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
                        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        spin.setStyleSheet("background:white;color:black;border:1px solid #ccc;border-radius:4px;")
                        spin.valueChanged.connect(self._update_refund_total)
                        self.refund_table.setCellWidget(r, 3, spin)

                        # ----  refund amount  ----
                        refund_item = QTableWidgetItem("₱0.00")
                        refund_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                        self.refund_table.setItem(r, 4, refund_item)

                        # ----  PAINT THE WHOLE ROW SOFT BLUE  ----
                        for c in range(5):
                            if self.refund_table.item(r, c):
                                self.refund_table.item(r, c).setBackground(QBrush(QColor(219, 234, 254)))  # soft blue
                                self.refund_table.item(r, c).setForeground(QBrush(QColor(0, 0, 0)))       # black text

                    self.step2.show()
                    self._update_refund_total()

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not load receipt:\n{e}")

    def _update_refund_total(self):
        total_refund = 0.0
        for r in range(self.refund_table.rowCount()):
            spin = self.refund_table.cellWidget(r, 3)
            qty = spin.value()
            if qty:
                price = float(self.current_transaction_items[r]["price"])
                line_total = price * qty
                total_refund += line_total
                self.refund_table.item(r, 4).setText(f"₱{line_total:.2f}")
            else:
                self.refund_table.item(r, 4).setText("₱0.00")

        self.big_refund_btn.setEnabled(total_refund > 0)
        self.big_refund_btn.setText(f"GIVE REFUND  –  ₱{total_refund:.2f}")

    def process_refund(self):
        total = 0.0
        refund_qtys = []  # will hold (item_id, qty)
        for r in range(self.refund_table.rowCount()):
            spin = self.refund_table.cellWidget(r, 3)
            qty = spin.value()
            if qty:
                price = float(self.current_transaction_items[r]["price"])
                total += price * qty

                # -----  NEW: find id by name  -----
                item_name = self.current_transaction_items[r]["name"]
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM items WHERE name = %s", (item_name,))
                        row = cur.fetchone()
                        if not row:  # should never happen
                            QMessageBox.critical(self, "Item missing",
                                                 f"Item '{item_name}' not found in inventory.")
                            return
                        item_id = row[0]
                # -----------------------------------
                refund_qtys.append((item_id, qty))

        if not refund_qtys:
            return

        reply = QMessageBox.question(
            self,
            "Confirm",
            f"Return these items and give back ₱{total:.2f} ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # record refund
                    cur.execute("""
                        INSERT INTO refunds (transaction_id, refund_amount, processed_by, processed_at)
                        VALUES (%s, %s, %s, NOW())
                    """, (self.current_transaction_id, total, self.username))

                    # restore stock
                    for item_id, qty in refund_qtys:
                        cur.execute("UPDATE items SET stock = stock + %s WHERE id = %s", (qty, item_id))

            QMessageBox.information(self, "Done", f"Refund complete!\n₱{total:.2f} was returned to customer.")
            self.refund_search.clear()
            self.step2.hide()

        except Exception as e:
            QMessageBox.critical(self, "Refund Failed", str(e))

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

        inp = QHBoxLayout()
        inp.setSpacing(12)
        inp.setContentsMargins(20, 0, 20, 0)

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
        self.price_spin = QDoubleSpinBox()
        self.price_spin.setPrefix("₱ ")
        self.price_spin.setRange(0.01, 999999)
        self.price_spin.setReadOnly(True)
        self.price_spin.setFixedHeight(42)
        self.price_spin.setStyleSheet(
            "background:#2b2b2b;border:1px solid #444;border-radius:6px;padding:6px;font-size:15px;color:#f8f9fa;")
        inp.addWidget(self.price_spin)

        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 999)
        self.qty_spin.setFixedHeight(42)
        self.qty_spin.setValue(1)
        self.qty_spin.setStyleSheet(
            "background:#2b2b2b;border:1px solid #444;border-radius:6px;padding:6px;font-size:15px;color:#f8f9fa;")
        inp.addWidget(self.qty_spin)

        add_btn = QPushButton("Add")
        add_btn.setFixedHeight(42)
        add_btn.setStyleSheet(
            "background:#06d6a0;color:#000;border:none;border-radius:6px;padding:6px 14px;font-weight:bold;")
        add_btn.clicked.connect(self.add_to_cart)
        inp.addWidget(add_btn)
        lay.addLayout(inp)

        self.cart_table = QTableWidget(0, 6)
        self.cart_table.setHorizontalHeaderLabels(["Item", "Price", "Qty", "Total", "Reduce", "Remove"])
        self.cart_table.setAlternatingRowColors(True)
        self.cart_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.cart_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        hdr = self.cart_table.horizontalHeader()
        for i in range(4):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
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
        self.status_lbl = QLabel("Ready")
        self.status_lbl.setStyleSheet(
            "color:#adb5bd;padding:10px 20px;font-size:14px;background:#2b2b2b;margin:0px 20px 10px 20px;border-radius:5px;")
        lay.addWidget(self.status_lbl)
        self.combo.currentTextChanged.connect(self.on_item_selected)

    def _load_items(self):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, name, price, stock FROM items WHERE stock > 0 ORDER BY name")
                    self.items_data = cur.fetchall()
        except Exception as e:
            print(f"Error loading items: {e}")
            self.items_data = []

    def _fill_item_combo(self):
        self.item_map = {name: (id, price, stock) for id, name, price, stock in self.items_data}
        self.combo.clear()
        self.combo.addItems(self.item_map.keys())
        completer = QCompleter(list(self.item_map.keys()), self)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        self.combo.setCompleter(completer)

    def on_item_selected(self, item_name):
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

        if qty > stock:
            QMessageBox.warning(self, "Stock", f"Not enough stock! Available: {stock}")
            return

        total = round(price * qty, 2)
        for item in self.cart:
            if item["name"] == name:
                item["qty"] += qty
                item["total"] = round(item["price"] * item["qty"], 2)
                self.refresh_cart_table()
                self.qty_spin.setValue(1)
                self.status_lbl.setText(f"Updated {name} in cart")
                return

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

            reduce_btn = QPushButton("-1")
            reduce_btn.setFixedSize(60, 30)
            reduce_btn.setStyleSheet(
                "QPushButton{background:#ff9f1c;color:#000;border:none;border-radius:4px;font-size:12px;font-weight:bold;}QPushButton:hover{background:#ffb627;}")
            reduce_btn.clicked.connect(lambda _, r=row: self.reduce_quantity(r))
            self.cart_table.setCellWidget(row, 4, reduce_btn)

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

class PaymentDialog(QDialog):
    def __init__(self, total_amount, parent=None):
        super().__init__(parent)
        self.total = Decimal(total_amount)  # Ensure total is a Decimal
        self.setWindowTitle("Payment")
        self.setFixedSize(400, 350)
        self.setStyleSheet("background:#1e1e1e;")

        v = QVBoxLayout(self)
        v.setContentsMargins(25, 25, 25, 25)

        self.total_lbl = QLabel(f"Total: ₱ {self.total:,.2f}")
        self.total_lbl.setStyleSheet("font-size:20px;color:#ffd166;font-weight:bold;")
        self.total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.total_lbl)

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

        self.discounted_lbl = QLabel("After discount: ₱ 0.00")
        self.discounted_lbl.setStyleSheet("font-size:16px;color:#06d6a0;font-weight:bold;")
        self.discounted_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.discounted_lbl)

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

        self.change_lbl = QLabel("Change: ₱ 0.00")
        self.change_lbl.setStyleSheet("font-size:18px;color:#06d6a0;font-weight:bold;")
        self.change_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.change_lbl)

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
            cash = Decimal(str(self.cash_input.value()))
            change = cash - final
            self.change_lbl.setText(f"Change: ₱ {change:,.2f}")
            self.cash_input.setEnabled(True)
            self.cash_input.setMinimum(final)
        else:
            self.change_lbl.setText("Change: ₱ 0.00")
            self.cash_input.setEnabled(False)
            self.cash_input.setMinimum(0)
            self.cash_input.setValue(0.0)

    def final_total(self):
        if self.discount_chk.isChecked():
            return round(self.total * Decimal('0.8'), 2)
        return self.total

    def method(self):
        return "Cash" if self.cash.isChecked() else "Card"

    def discount_checked(self):
        return self.cash_input.isEnabled() and self.discount_chk.isChecked()

    def get_cash_amount(self):
        return Decimal(str(self.cash_input.value()))

    def on_cash_toggled(self, checked):
        if checked:
            self.cash_input.setValue(0.0)
            self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

    def on_card_toggled(self, checked):
        if checked:
            self.cash_input.setValue(0.0)
            self.bb.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)

class CashierLoginDialog(QDialog):
    def __init__(self):
        super().__init__()
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
        self._ensure_tables_exist()
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
                cur.execute("SELECT 1 FROM users WHERE username=%s AND password=SHA2(%s,256) AND role='cashier'",
                            (user, pwd))
                if cur.fetchone():
                    self._win = CashierWindow(user, logout_callback=self._show_login)
                    self._win.show()
                    return
                cur.execute("SELECT 1 FROM users WHERE username=%s AND password=SHA2(%s,256) AND role='admin'",
                            (user, pwd))
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

    def _ensure_tables_exist(self):
        try:
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            username VARCHAR(50) UNIQUE NOT NULL,
                            password VARCHAR(64) NOT NULL,
                            role ENUM('cashier', 'admin') NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS managers (
                            id INT AUTO_INCREMENT PRIMARY KEY,
                            username VARCHAR(50) UNIQUE NOT NULL,
                            password VARCHAR(64) NOT NULL,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    cur.execute("SELECT COUNT(*) FROM users")
                    user_count = cur.fetchone()[0]
                    if user_count == 0:
                        cur.execute("""
                            INSERT INTO users (username, password, role) 
                            VALUES ('admin', SHA2('admin123', 256), 'admin')
                        """)
                        print("✅ Created default admin user: admin / admin123")
                    else:
                        print(f"✅ Database check complete. Found {user_count} existing user(s).")

            print("✅ Database tables are ready")
        except Exception as e:
            print(f"❌ Error ensuring tables exist: {e}")


if __name__ == "__main__":
    app = CashierApp(sys.argv)
    app.setStyleSheet("QWidget { background-color: #d3d3d3; }")
    sys.exit(app.exec())