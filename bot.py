import os
import uuid
import sqlite3
import asyncio
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage


# =========================================================
# CONFIG
# =========================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN missing")

if not RAZORPAY_KEY_ID:
    raise ValueError("RAZORPAY_KEY_ID missing")

if not RAZORPAY_KEY_SECRET:
    raise ValueError("RAZORPAY_KEY_SECRET missing")


RAZORPAY_BASE = "https://api.razorpay.com/v1"

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# =========================================================
# DATABASE
# =========================================================

DB = "payments.db"


def init_db():
    conn = sqlite3.connect(DB)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            order_id TEXT NOT NULL UNIQUE,
            razorpay_qr_id TEXT,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)

    conn.commit()
    conn.close()


init_db()


def save_payment(
    user_id,
    order_id,
    qr_id,
    amount,
    expires_at
):
    conn = sqlite3.connect(DB)

    conn.execute("""
        INSERT INTO payments
        (
            user_id,
            order_id,
            razorpay_qr_id,
            amount,
            status,
            created_at,
            expires_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        order_id,
        qr_id,
        amount,
        "pending",
        datetime.now(timezone.utc).isoformat(),
        expires_at.isoformat(),
    ))

    conn.commit()
    conn.close()


def get_payment(user_id):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    row = conn.execute("""
        SELECT *
        FROM payments
        WHERE user_id = ?
        AND status = 'pending'
        ORDER BY id DESC
        LIMIT 1
    """, (user_id,)).fetchone()

    conn.close()

    return dict(row) if row else None


def update_status(order_id, status):
    conn = sqlite3.connect(DB)

    conn.execute("""
        UPDATE payments
        SET status = ?
        WHERE order_id = ?
    """, (status, order_id))

    conn.commit()
    conn.close()


# =========================================================
# FSM
# =========================================================

class PaymentState(StatesGroup):
    amount = State()


# =========================================================
# RAZORPAY REQUEST
# =========================================================

def razorpay_request(method, endpoint, data=None):

    url = RAZORPAY_BASE + endpoint

    response = requests.request(
        method=method,
        url=url,
        auth=(
            RAZORPAY_KEY_ID,
            RAZORPAY_KEY_SECRET
        ),
        json=data,
        timeout=30
    )

    try:
        result = response.json()
    except Exception:
        result = {
            "error": response.text
        }

    if not response.ok:
        raise Exception(
            f"Razorpay Error {response.status_code}: {result}"
        )

    return result


# =========================================================
# KEYBOARDS
# =========================================================

def start_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="💳 Pay Now",
                    callback_data="pay_now"
                )
            ]
        ]
    )


def amount_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="1",
                    callback_data="num_1"
                ),
                InlineKeyboardButton(
                    text="2",
                    callback_data="num_2"
                ),
                InlineKeyboardButton(
                    text="3",
                    callback_data="num_3"
                )
            ],

            [
                InlineKeyboardButton(
                    text="4",
                    callback_data="num_4"
                ),
                InlineKeyboardButton(
                    text="5",
                    callback_data="num_5"
                ),
                InlineKeyboardButton(
                    text="6",
                    callback_data="num_6"
                )
            ],

            [
                InlineKeyboardButton(
                    text="7",
                    callback_data="num_7"
                ),
                InlineKeyboardButton(
                    text="8",
                    callback_data="num_8"
                ),
                InlineKeyboardButton(
                    text="9",
                    callback_data="num_9"
                )
            ],

            [
                InlineKeyboardButton(
                    text="Del",
                    callback_data="num_del"
                ),
                InlineKeyboardButton(
                    text="0",
                    callback_data="num_0"
                ),
                InlineKeyboardButton(
                    text="Pay",
                    callback_data="num_pay"
                )
            ],

            [
                InlineKeyboardButton(
                    text="Cancel",
                    callback_data="cancel_amount"
                )
            ]
        ]
    )


def payment_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="✅ Check Payment",
                    callback_data="check_payment"
                )
            ],

            [
                InlineKeyboardButton(
                    text="❌ Cancel",
                    callback_data="cancel_payment"
                )
            ]
        ]
    )


def new_payment_keyboard():

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔄 Create New Payment",
                    callback_data="pay_now"
                )
            ]
        ]
    )


# =========================================================
# START
# =========================================================

@dp.message(CommandStart())
async def start(message: Message, state: FSMContext):

    await state.clear()

    text = (
        "Welcome!\n\n"
        "UPI Auto Payment Bot\n\n"
        "Add money instantly via UPI.\n"
        "Payments are verified through Razorpay.\n\n"
        "Use Pay Now to make a payment."
    )

    await message.answer(
        text,
        reply_markup=start_keyboard()
    )


# =========================================================
# PAY NOW
# =========================================================

@dp.callback_query(F.data == "pay_now")
async def pay_now(
    callback: CallbackQuery,
    state: FSMContext
):

    await state.clear()

    await state.update_data(amount="")

    await callback.message.answer(
        "UPI Auto Payment\n\n"
        "Enter amount (min Rs 1)\n\n"
        "Rs 0",
        reply_markup=amount_keyboard()
    )

    await state.set_state(PaymentState.amount)

    await callback.answer()


# =========================================================
# AMOUNT KEYPAD
# =========================================================

@dp.callback_query(
    PaymentState.amount,
    F.data.startswith("num_")
)
async def keypad(
    callback: CallbackQuery,
    state: FSMContext
):

    action = callback.data.replace("num_", "")

    data = await state.get_data()

    amount = data.get("amount", "")

    # -----------------------------------------
    # DELETE
    # -----------------------------------------

    if action == "del":

        amount = amount[:-1]

        await state.update_data(
            amount=amount
        )

        display = amount or "0"

        await callback.message.edit_text(
            "UPI Auto Payment\n\n"
            "Enter amount (min Rs 1)\n\n"
            f"Rs {display}",
            reply_markup=amount_keyboard()
        )

        await callback.answer()

        return

    # -----------------------------------------
    # PAY
    # -----------------------------------------

    if action == "pay":

        if not amount:

            await callback.answer(
                "Please enter amount.",
                show_alert=True
            )

            return

        amount_int = int(amount)

        if amount_int < 1:

            await callback.answer(
                "Minimum amount is Rs 1.",
                show_alert=True
            )

            return

        await state.clear()

        try:
            await callback.message.delete()
        except Exception:
            pass

        await create_razorpay_qr(
            callback.message,
            amount_int
        )

        await callback.answer()

        return

    # -----------------------------------------
    # NUMBER
    # -----------------------------------------

    if action.isdigit():

        if len(amount) >= 8:

            await callback.answer(
                "Amount too large.",
                show_alert=True
            )

            return

        if amount == "0":
            amount = action
        else:
            amount += action

        await state.update_data(
            amount=amount
        )

        await callback.message.edit_text(
            "UPI Auto Payment\n\n"
            "Enter amount (min Rs 1)\n\n"
            f"Rs {amount}",
            reply_markup=amount_keyboard()
        )

        await callback.answer()


# =========================================================
# CREATE RAZORPAY QR
# =========================================================

async def create_razorpay_qr(
    message: Message,
    amount: int
):

    user_id = message.from_user.id

    order_id = (
        f"ORD-"
        f"{datetime.now().strftime('%Y%m%d')}-"
        f"{uuid.uuid4().hex[:8].upper()}"
    )

    # 15 minutes
    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(minutes=15)
    )

    # Unix timestamp for Razorpay
    close_by = int(
        expires_at.timestamp()
    )

    payload = {

        "type": "upi",

        "name": "Payment",

        "usage": "single_use",

        "fixed_amount": True,

        # Razorpay amount = paise
        "payment_amount": amount * 100,

        "description": order_id,

        "close_by": close_by,

        "notes": {
            "order_id": order_id,
            "telegram_user_id": str(user_id)
        }
    }

    try:

        qr = await asyncio.to_thread(
            razorpay_request,
            "POST",
            "/payments/qr_codes",
            payload
        )

    except Exception as e:

        await message.answer(
            "❌ Razorpay QR generate nahi ho paya.\n\n"
            f"Error: {str(e)[:500]}"
        )

        return

    qr_id = qr.get("id")

    image_url = qr.get("image_url")

    if not qr_id or not image_url:

        await message.answer(
            "❌ Razorpay ne QR response nahi diya.\n\n"
            f"{qr}"
        )

        return

    save_payment(
        user_id=user_id,
        order_id=order_id,
        qr_id=qr_id,
        amount=amount,
        expires_at=expires_at
    )

    caption = (
        "💳 UPI Auto Payment\n\n"
        f"Amount: Rs {amount}\n"
        f"Order: {order_id}\n\n"
        "1. Scan QR with GPay / PhonePe / Paytm\n"
        f"2. Pay exactly Rs {amount}\n"
        "3. Tap Check Payment\n\n"
        "⏳ Expires in 15 minutes"
    )

    await message.answer_photo(
        photo=image_url,
        caption=caption,
        reply_markup=payment_keyboard()
    )

    # Local expiry timer
    asyncio.create_task(
        expiry_timer(
            user_id,
            order_id
        )
    )


# =========================================================
# EXPIRY TIMER
# =========================================================

async def expiry_timer(
    user_id: int,
    order_id: str
):

    await asyncio.sleep(15 * 60)

    payment = get_payment(user_id)

    if not payment:
        return

    if payment["order_id"] != order_id:
        return

    if payment["status"] != "pending":
        return

    update_status(
        order_id,
        "expired"
    )

    # Close Razorpay QR
    try:

        await asyncio.to_thread(
            razorpay_request,
            "POST",
            f"/payments/qr_codes/"
            f"{payment['razorpay_qr_id']}/close"
        )

    except Exception:
        pass


# =========================================================
# CHECK PAYMENT
# =========================================================

@dp.callback_query(F.data == "check_payment")
async def check_payment(
    callback: CallbackQuery
):

    user_id = callback.from_user.id

    payment = get_payment(user_id)

    if not payment:

        await callback.answer(
            "No active payment found.",
            show_alert=True
        )

        return

    expires_at = datetime.fromisoformat(
        payment["expires_at"]
    )

    # -----------------------------------------
    # LOCAL EXPIRY CHECK
    # -----------------------------------------

    if datetime.now(timezone.utc) >= expires_at:

        update_status(
            payment["order_id"],
            "expired"
        )

        try:

            await callback.message.edit_caption(
                caption=(
                    "⏰ Payment Expired\n\n"
                    f"Amount: Rs {payment['amount']}\n"
                    f"Order: {payment['order_id']}\n\n"
                    "This payment request has expired.\n"
                    "Please create a new payment."
                ),
                reply_markup=new_payment_keyboard()
            )

        except Exception:
            pass

        await callback.answer(
            "Payment expired.",
            show_alert=True
        )

        return

    # -----------------------------------------
    # RAZORPAY PAYMENT CHECK
    # -----------------------------------------

    try:

        result = await asyncio.to_thread(
            razorpay_request,
            "GET",
            f"/payments/qr_codes/"
            f"{payment['razorpay_qr_id']}/payments"
        )

    except Exception as e:

        await callback.answer(
            "Razorpay verification failed.",
            show_alert=True
        )

        return

    items = result.get("items", [])

    successful_payment = None

    for p in items:

        status = p.get("status")

        amount_paid = p.get("amount")

        if (
            status == "captured"
            and amount_paid == payment["amount"] * 100
        ):

            successful_payment = p

            break

    # -----------------------------------------
    # SUCCESS
    # -----------------------------------------

    if successful_payment:

        update_status(
            payment["order_id"],
            "paid"
        )

        await callback.message.edit_caption(
            caption=(
                "✅ Payment Successful!\n\n"
                f"Amount: Rs {payment['amount']}\n"
                f"Order: {payment['order_id']}\n\n"
                "Payment verified successfully."
            ),
            reply_markup=new_payment_keyboard()
        )

        await callback.answer(
            "Payment verified successfully!",
            show_alert=True
        )

        return

    # -----------------------------------------
    # PENDING
    # -----------------------------------------

    await callback.answer(
        "⏳ Payment not received yet.",
        show_alert=True
    )


# =========================================================
# CANCEL PAYMENT
# =========================================================

@dp.callback_query(F.data == "cancel_payment")
async def cancel_payment(
    callback: CallbackQuery
):

    user_id = callback.from_user.id

    payment = get_payment(user_id)

    if payment:

        update_status(
            payment["order_id"],
            "cancelled"
        )

        try:

            await asyncio.to_thread(
                razorpay_request,
                "POST",
                f"/payments/qr_codes/"
                f"{payment['razorpay_qr_id']}/close"
            )

        except Exception:
            pass

    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer(
        "❌ Payment cancelled.",
        reply_markup=start_keyboard()
    )

    await callback.answer()


# =========================================================
# RUN
# =========================================================

async def main():

    print("================================")
    print("Razorpay Payment Bot Started")
    print("================================")

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
