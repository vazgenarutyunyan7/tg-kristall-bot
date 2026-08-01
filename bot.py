import asyncio
import logging
import os
import sqlite3
import time
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

logging.basicConfig(level=logging.INFO)
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher()

# База данных карточек
CARDS = {
    "team": {"name": "👨‍💻 Команда", "base_cost": 50, "base_pnl": 10},
    "marketing": {"name": "📢 Реклама", "base_cost": 150, "base_pnl": 35},
    "servers": {"name": "🖥️ Серверы", "base_cost": 500, "base_pnl": 100},
}

# Секретное комбо дня (ключи карточек)
TODAY_COMBO = ["team", "marketing"]


def init_db():
    conn = sqlite3.connect("kristall.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 100.0,
            pnl REAL DEFAULT 0.0,
            last_claim INTEGER,
            cards TEXT DEFAULT ''
        )
    """
    )
    conn.commit()
    conn.close()


def get_user(user_id):
    conn = sqlite3.connect("kristall.db")
    cursor = conn.cursor()
    now = int(time.time())

    cursor.execute(
        "SELECT balance, pnl, last_claim, cards FROM users WHERE user_id = ?",
        (user_id,),
    )
    row = cursor.fetchone()

    if not row:
        cursor.execute(
            "INSERT INTO users (user_id, balance, pnl, last_claim, cards) VALUES (?, 100.0, 0.0, ?, '')",
            (user_id, now),
        )
        conn.commit()
        conn.close()
        return {"balance": 100.0, "pnl": 0.0, "last_claim": now, "cards": []}

    balance, pnl, last_claim, cards_str = row
    cards = cards_str.split(",") if cards_str else []

    # Начисление пассивного дохода за оффлайн время
    seconds_offline = now - last_claim
    if seconds_offline > 0 and pnl > 0:
        added_balance = (pnl / 3600) * seconds_offline
        balance += added_balance

    cursor.execute(
        "UPDATE users SET balance = ?, last_claim = ? WHERE user_id = ?",
        (balance, now, user_id),
    )
    conn.commit()
    conn.close()

    return {"balance": balance, "pnl": pnl, "last_claim": now, "cards": cards}


# Главная клавиатура
def main_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⛏️ Шахта (Карточки)", callback_data="mine"
                ),
                InlineKeyboardButton(text="👤 Профиль", callback_data="profile"),
            ],
            [
                InlineKeyboardButton(
                    text="🧩 Проверить Комбо", callback_data="check_combo"
                )
            ],
        ]
    )


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user = get_user(message.from_user.id)
    await message.answer(
        f"🐹 **Добро пожаловать в Kristall Kombat!**\n\n"
        f"💎 Баланс: **{int(user['balance'])}** кристаллов\n"
        f"⚡ Прибыль в час: **+{int(user['pnl'])}** / час\n\n"
        f"Прокачивай карточки, собирай комбо и забирай пассивный доход!",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data == "profile")
async def cb_profile(call: types.CallbackQuery):
    user = get_user(call.from_user.id)
    await call.message.edit_text(
        f"👤 **Твой профиль:**\n\n"
        f"💎 Баланс: **{int(user['balance'])}** кристаллов\n"
        f"⚡ Прибыль в час: **+{int(user['pnl'])}** / час\n"
        f"🃏 Куплено карточек: **{len(user['cards'])}**",
        reply_markup=main_keyboard(),
    )


@dp.callback_query(F.data == "mine")
async def cb_mine(call: types.CallbackQuery):
    user = get_user(call.from_user.id)
    buttons = []

    for card_id, card in CARDS.items():
        bought = card_id in user["cards"]
        status = "✅ Куплена" if bought else f"💰 {card['base_cost']} 💎"
        btn_text = f"{card['name']} | +{card['base_pnl']}/ч | {status}"
        buttons.append(
            [InlineKeyboardButton(text=btn_text, callback_data=f"buy_{card_id}")]
        )

    buttons.append(
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]
    )

    await call.message.edit_text(
        "⛏️ **Магазин карточек:**\nПокупай карточки, чтобы увеличить доход в час!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(call: types.CallbackQuery):
    card_id = call.data.split("_")[1]
    user = get_user(call.from_user.id)
    card = CARDS.get(card_id)

    if card_id in user["cards"]:
        await call.answer("У тебя уже есть эта карточка!", show_alert=True)
        return

    if user["balance"] < card["base_cost"]:
        await call.answer("Не хватает кристаллов!", show_alert=True)
        return

    # Покупка
    new_balance = user["balance"] - card["base_cost"]
    new_pnl = user["pnl"] + card["base_pnl"]
    user["cards"].append(card_id)
    cards_str = ",".join(user["cards"])

    conn = sqlite3.connect("kristall.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET balance = ?, pnl = ?, cards = ? WHERE user_id = ?",
        (new_balance, new_pnl, cards_str, call.from_user.id),
    )
    conn.commit()
    conn.close()

    await call.answer(f"Успешно куплено: {card['name']}!")
    await cb_mine(call)


@dp.callback_query(F.data == "check_combo")
async def cb_combo(call: types.CallbackQuery):
    user = get_user(call.from_user.id)
    # Проверка: открыты ли все карточки из комбо
    has_combo = all(card in user["cards"] for card in TODAY_COMBO)

    if has_combo:
        conn = sqlite3.connect("kristall.db")
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET balance = balance + 5000 WHERE user_id = ?",
            (call.from_user.id,),
        )
        conn.commit()
        conn.close()
        await call.answer(
            "🎉 Поздравляем! Ты собрал Комбо Дня и получил +5000 кристаллов!",
            show_alert=True,
        )
    else:
        await call.answer(
            "❌ Ты ещё не собрал нужные карточки для комбо!", show_alert=True
        )


async def main():
    if not TOKEN:
        raise SystemExit("BOT_TOKEN не найден!")
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
