# app.py
import sqlite3
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, TypedDict

import pandas as pd
import streamlit as st

# Optional: integrate LangGraph if available (your original)
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except Exception:
    LANGGRAPH_AVAILABLE = False

# -----------------------
# CONFIG / MENU / CONSTANTS
# -----------------------
DB_PATH = "hotel_room_service.db"
ADMIN_PASSWORD = "admin123"  # change to secure password in production

# Mock menu (expandable)
MENU = {
    "coffee": 120,
    "tea": 90,
    "sandwich": 180,
    "pasta": 250,
    "juice": 150,
    "towel": 0,
    "toothpaste": 0,
    "water bottle": 50,
    "club sandwich": 220,
    "omelette": 160,
}

TAX_PERCENT = 5.0       # GST percentage
SERVICE_CHARGE = 10.0   # Service charge percentage
CURRENCY = "₹"


# -----------------------
# ORDER STATE TYPE
# -----------------------
class OrderState(TypedDict):
    order_id: str
    created_at: str
    room_number: str
    guest_name: str
    items: List[Dict]
    unavailable_items: List[str]
    subtotal: float
    taxes: float
    service_charge: float
    tip: float
    total: float
    special_requests: str
    status: str  # pending, accepted, preparing, out-for-delivery, delivered, cancelled
    priority: str  # normal / urgent


# -----------------------
# DB UTILITIES
# -----------------------
def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            created_at TEXT,
            room_number TEXT,
            guest_name TEXT,
            items TEXT,              -- JSON string
            unavailable_items TEXT,  -- CSV
            subtotal REAL,
            taxes REAL,
            service_charge REAL,
            tip REAL,
            total REAL,
            special_requests TEXT,
            status TEXT,
            priority TEXT
        )
        """
    )
    conn.commit()
    return conn


conn = init_db()


# -----------------------
# HELPERS
# -----------------------
import json


def calculate_amount(items: List[Dict], tip: float) -> Dict:
    subtotal = 0.0
    for it in items:
        subtotal += it["qty"] * it["price"]
    taxes = round(subtotal * (TAX_PERCENT / 100.0), 2)
    service = round(subtotal * (SERVICE_CHARGE / 100.0), 2)
    total = round(subtotal + taxes + service + tip, 2)
    return {"subtotal": round(subtotal, 2), "taxes": taxes, "service_charge": service, "total": total}


def save_order_to_db(state: OrderState):
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO orders (
            order_id, created_at, room_number, guest_name,
            items, unavailable_items, subtotal, taxes,
            service_charge, tip, total, special_requests,
            status, priority
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            state["order_id"],
            state["created_at"],
            state["room_number"],
            state["guest_name"],
            json.dumps(state["items"]),
            ",".join(state["unavailable_items"]),
            state["subtotal"],
            state["taxes"],
            state["service_charge"],
            state["tip"],
            state["total"],
            state["special_requests"],
            state["status"],
            state["priority"],
        ),
    )
    conn.commit()


def get_orders(status_filter: str = None) -> pd.DataFrame:
    cursor = conn.cursor()
    if status_filter:
        cursor.execute("SELECT * FROM orders WHERE status = ? ORDER BY created_at DESC", (status_filter,))
    else:
        cursor.execute("SELECT * FROM orders ORDER BY created_at DESC")
    rows = cursor.fetchall()
    cols = [d[0] for d in cursor.description]
    df = pd.DataFrame(rows, columns=cols)
    if not df.empty:
        df["items"] = df["items"].apply(lambda s: json.loads(s))
        df["unavailable_items"] = df["unavailable_items"].fillna("").apply(lambda s: s.split(",") if s else [])
    return df


def update_order_status(order_id: str, new_status: str):
    cursor = conn.cursor()
    cursor.execute("UPDATE orders SET status = ? WHERE order_id = ?", (new_status, order_id))
    conn.commit()


def mark_unavailable_items(order_id: str, items: List[str]):
    # append to unavailable_items and set status to 'partial' or keep pending
    cursor = conn.cursor()
    cursor.execute("SELECT unavailable_items FROM orders WHERE order_id = ?", (order_id,))
    row = cursor.fetchone()
    existing = row[0] or ""
    all_items = set(filter(None, existing.split(","))) | set(items)
    cursor.execute("UPDATE orders SET unavailable_items = ? WHERE order_id = ?", (",".join(all_items), order_id))
    conn.commit()


# -----------------------
# LANGGRAPH (optional) - retains your original graph idea
# -----------------------
def make_langgraph_agent():
    if not LANGGRAPH_AVAILABLE:
        return None

    # Keep the same basic nodes you provided
    def collect_order(state: OrderState):
        user_input = state.get("user_input", "").lower()
        items = []
        # detect items and default qty 1
        for menu_item in MENU:
            if menu_item in user_input:
                items.append({"item": menu_item, "qty": 1, "price": MENU[menu_item]})
        state["items"] = items
        return state

    def check_availability(state: OrderState):
        unavailable = []
        for order in state.get("items", []):
            if order["item"] not in MENU:
                unavailable.append(order["item"])
        state["unavailable_items"] = unavailable
        return state

    def confirm_order(state: OrderState):
        total = 0
        for order in state.get("items", []):
            total += order["qty"] * order["price"]
        state["bill_amount"] = total
        if len(state.get("items", [])) == 0:
            state["message"] = "I couldn't find any available items in your order."
            return state
        msg = "### ✅ Order Confirmed!\n\n**Items Ordered:**\n"
        for order in state["items"]:
            msg += f"- **{order['item'].title()} x {order['qty']}** — {CURRENCY}{order['price']}\n"
        msg += f"\n### 💰 Total: {CURRENCY}{total}\n"
        msg += "Your items will arrive shortly. Thank you!"
        state["message"] = msg
        return state

    graph = StateGraph(OrderState)
    graph.add_node("collect", collect_order)
    graph.add_node("availability", check_availability)
    graph.add_node("confirm", confirm_order)
    graph.set_entry_point("collect")
    graph.add_edge("collect", "availability")
    graph.add_edge("availability", "confirm")
    graph.add_edge("confirm", END)
    return graph.compile()


agent = make_langgraph_agent() if LANGGRAPH_AVAILABLE else None


# -----------------------
# STREAMLIT UI
# -----------------------
st.set_page_config(page_title="Hotel Room Service", layout="wide")
st.title("🏨 Hotel Room Service — Dashboard & Ordering")

# Sidebar: quick info & admin login
with st.sidebar:
    st.header("Quick Actions")
    st.write("Menu items:", len(MENU))
    if st.checkbox("Show menu prices (sidebar)"):
        for k, v in MENU.items():
            st.write(f"- {k.title()}: {CURRENCY}{v}")

    st.markdown("---")
    st.subheader("Admin Login")
    admin_pw = st.text_input("Admin password", type="password")
    if admin_pw and admin_pw == ADMIN_PASSWORD:
        st.success("Admin logged in")
        st.session_state["is_admin"] = True
    elif admin_pw:
        st.error("Wrong password")

    st.markdown("---")
    st.write("Operational settings:")
    st.write(f"- Tax: {TAX_PERCENT}%")
    st.write(f"- Service charge: {SERVICE_CHARGE}%")

# Main layout: two columns
col1, col2 = st.columns([2, 3])

# ---------- Guest ordering panel ----------
with col1:
    st.subheader("Place an Order (Guest)")
    guest_name = st.text_input("Guest name", placeholder="e.g., John Doe")
    room_number = st.text_input("Room number", placeholder="e.g., 101")
    priority = st.selectbox("Priority", ["normal", "urgent"])

    # Allow both a natural-language text box (keeps your original flow) and a structured builder
    use_text_nl = st.checkbox("Use natural language order (detect items from text)", value=False)

    if use_text_nl:
        nl_input = st.text_area("Type your order in plain English",
                                placeholder="Example: Please send 2 sandwiches and a coffee to room 305. No sugar.")
    else:
        st.write("Select items and quantities:")
        # present menu with quantity number_inputs
        selected_items = []
        for name, price in MENU.items():
            cols = st.columns([3, 1])
            with cols[0]:
                qty = st.number_input(f"{name.title()}", min_value=0, max_value=20, value=0, key=f"qty_{name}")
            with cols[1]:
                st.write(f"{CURRENCY}{price}")
            if qty > 0:
                selected_items.append({"item": name, "qty": int(qty), "price": price})

    special_requests = st.text_area("Special requests (e.g., no onion, extra napkins)", value="")
    tip = st.number_input("Tip (optional)", min_value=0.0, step=10.0, value=0.0)

    if st.button("Preview Order"):
        # build order items either from NL or structured
        if use_text_nl:
            if not nl_input.strip():
                st.warning("Please write your order in the text box.")
            else:
                # Try to parse items by simple keyword match
                detected = []
                lower = nl_input.lower()
                for menu_item in MENU:
                    if menu_item in lower:
                        detected.append({"item": menu_item, "qty": 1, "price": MENU[menu_item]})
                st.write("Detected items (you can still place a structured order below if incorrect):")
                st.json(detected)
                st.session_state["preview_items"] = detected
        else:
            if not selected_items:
                st.warning("Please select at least one item")
            else:
                st.session_state["preview_items"] = selected_items
                st.success("Preview ready — press Confirm to place the order")

    if st.button("Confirm & Place Order"):
        # final gather
        final_items = st.session_state.get("preview_items", []) if use_text_nl or "preview_items" in st.session_state else (selected_items if not use_text_nl else [])
        if not final_items:
            st.warning("No items detected/selected — use Preview first or select items")
        elif not room_number.strip():
            st.warning("Please enter room number.")
        else:
            # check availability: in this mock, if item price = 0 treat as amenity free (available)
            unavailable = [it["item"] for it in final_items if it["item"] not in MENU]
            # calculate amounts
            amounts = calculate_amount(final_items, float(tip))
            order_id = str(uuid.uuid4())[:8]
            created_at = datetime.utcnow().isoformat()
            state: OrderState = {
                "order_id": order_id,
                "created_at": created_at,
                "room_number": room_number,
                "guest_name": guest_name or "Guest",
                "items": final_items,
                "unavailable_items": unavailable,
                "subtotal": amounts["subtotal"],
                "taxes": amounts["taxes"],
                "service_charge": amounts["service_charge"],
                "tip": float(tip),
                "total": amounts["total"],
                "special_requests": special_requests,
                "status": "pending",
                "priority": priority,
            }
            save_order_to_db(state)
            st.success(f"Order placed — ID: {order_id}")
            st.markdown("### Receipt")
            st.write(f"**Order ID:** {order_id}")
            st.write(f"**Room:** {room_number}   •   **Guest:** {guest_name or 'Guest'}")
            st.write("**Items:**")
            for it in final_items:
                st.write(f"- {it['item'].title()} x {it['qty']} — {CURRENCY}{it['price']}")
            st.write(f"Subtotal: {CURRENCY}{state['subtotal']}")
            st.write(f"Tax ({TAX_PERCENT}%): {CURRENCY}{state['taxes']}")
            st.write(f"Service ({SERVICE_CHARGE}%): {CURRENCY}{state['service_charge']}")
            if tip:
                st.write(f"Tip: {CURRENCY}{tip}")
            st.write(f"**Total: {CURRENCY}{state['total']}**")
            st.info("Operator will accept and prepare your order shortly.")


# ---------- Admin / Operator dashboard ----------
with col2:
    st.subheader("Operator Dashboard")

    is_admin = st.session_state.get("is_admin", False)
    view_mode = st.selectbox("View orders by status", ["all", "pending", "accepted", "preparing", "out-for-delivery", "delivered", "cancelled"])

    df_orders = get_orders(None if view_mode == "all" else view_mode)
    if df_orders.empty:
        st.info("No orders found.")
    else:
        # Show high-level table
        display_cols = ["order_id", "created_at", "room_number", "guest_name", "status", "total", "priority"]
        st.dataframe(df_orders[display_cols].sort_values("created_at", ascending=False))

        # operator actions
        order_to_manage = st.selectbox("Select order to manage", df_orders["order_id"].tolist())
        if order_to_manage:
            row = df_orders[df_orders["order_id"] == order_to_manage].iloc[0]
            st.markdown(f"### Order {row['order_id']} — Status: **{row['status']}**")
            st.write(f"Room: {row['room_number']} • Guest: {row['guest_name']}")
            st.write("Items:")
            for it in row["items"]:
                st.write(f"- {it['item'].title()} x {it['qty']} — {CURRENCY}{it['price']}")
            st.write(f"Subtotal: {CURRENCY}{row['subtotal']}")
            st.write(f"Tax: {CURRENCY}{row['taxes']}")
            st.write(f"Service: {CURRENCY}{row['service_charge']}")
            st.write(f"Tip: {CURRENCY}{row['tip']}")
            st.write(f"Total: {CURRENCY}{row['total']}")
            st.write("Unavailable items:", ", ".join(row["unavailable_items"]) if row["unavailable_items"] else "None")
            st.write("Special requests:", row["special_requests"] or "None")

            if is_admin:
                st.markdown("#### Actions")
                cols = st.columns(4)
                if cols[0].button("Accept Order"):
                    update_order_status(order_to_manage, "accepted")
                    st.experimental_rerun()
                if cols[1].button("Start Preparing"):
                    update_order_status(order_to_manage, "preparing")
                    st.experimental_rerun()
                if cols[2].button("Mark Out for Delivery"):
                    update_order_status(order_to_manage, "out-for-delivery")
                    st.experimental_rerun()
                if cols[3].button("Mark Delivered"):
                    update_order_status(order_to_manage, "delivered")
                    st.experimental_rerun()

                st.markdown("-----")
                colu1, colu2 = st.columns([3, 1])
                with colu1:
                    mark_unavailable = st.multiselect("Mark these items unavailable", [it["item"] for it in row["items"]])
                with colu2:
                    if st.button("Apply Unavailable"):
                        mark_unavailable_items(order_to_manage, mark_unavailable)
                        st.success("Marked unavailable")
                        st.experimental_rerun()

                st.markdown("-----")
                if st.button("Cancel Order"):
                    update_order_status(order_to_manage, "cancelled")
                    st.experimental_rerun()
            else:
                st.info("Log in as admin (sidebar) to take actions on orders")

    # Export
    if st.button("Export all orders as CSV"):
        all_df = get_orders(None)
        if all_df.empty:
            st.warning("No orders to export")
        else:
            to_export = all_df.copy()
            # convert items to friendly text
            to_export["items_text"] = to_export["items"].apply(lambda il: "; ".join([f"{i['item']} x{i['qty']}" for i in il]))
            to_export = to_export.drop(columns=["items"])
            csv = to_export.to_csv(index=False)
            st.download_button("Download CSV", csv, file_name="orders_export.csv", mime="text/csv")

# ---------- Footer / Extras ----------
st.markdown("---")
st.markdown("### Features implemented in this demo")
st.write(
    """
- Natural-language vs structured order input (simple keyword detection)
- Quantity selection, tip input, special requests
- Order persistence (SQLite)
- Operator/admin dashboard with simple password
- Order lifecycle: pending → accepted → preparing → out-for-delivery → delivered
- Mark unavailable items / cancel orders
- Receipt preview and CSV export
"""
)

if LANGGRAPH_AVAILABLE:
    st.info("LangGraph integration active: you can optionally build NLP-driven flows. Agent created.")
else:
    st.info("LangGraph not available. To enable, `pip install langgraph` and restart the app (optional).")
