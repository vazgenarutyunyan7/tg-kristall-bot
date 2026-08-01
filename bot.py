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

# База данных карточек (с базовой ценой, доходом и коэффициентом удорожания)
CARDS = {
    "team": {
        "name": "👨‍💻 Команда",
        "base_cost": 50,
        "base_pnl": 10,
        "multiplier": 1.15,
    },
    "marketing": {
        "name": "📢 Реклама",
        "base_cost": 150,
        "base_pnl": 35,
        "multiplier": 1.15,
    },
    "servers": {
        "name": "🖥️ Серверы",
        "base_cost": 500,
        "base_pnl": 100,
        "multiplier": 1.15,
    },
}

# Секретное комбо дня (нужно иметь уровень >= 1 для этих карточек)
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
            last_claim INTEGER
        )
    """
  )
  # Таблица для уровней карточек: сохраняет, сколько раз пользователь купил конкретную карточку
  cursor.execute(
      """
        CREATE TABLE IF NOT EXISTS user_cards (
            user_id INTEGER,
            card_id TEXT,
            level INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, card_id)
        )
    """
  )
  conn.commit()
  conn.close()


def get_user_cards(user_id):
  conn = sqlite3.connect("kristall.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT card_id, level FROM user_cards WHERE user_id = ?", (user_id,)
  )
  rows = cursor.fetchall()
  conn.close()
  return {row[0]: row[1] for row in rows}


def get_user(user_id):
  conn = sqlite3.connect("kristall.db")
  cursor = conn.cursor()
  now = int(time.time())

  cursor.execute(
      "SELECT balance, pnl, last_claim FROM users WHERE user_id = ?", (user_id,)
  )
  row = cursor.fetchone()

  if not row:
    cursor.execute(
        "INSERT INTO users (user_id, balance, pnl, last_claim) VALUES (?,"
        " 100.0, 0.0, ?)",
        (user_id, now),
    )
    conn.commit()
    conn.close()
    return {"balance": 100.0, "pnl": 0.0, "last_claim": now}

  balance, pnl, last_claim = row

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

  return {"balance": balance, "pnl": pnl, "last_claim": now}


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
      f"Прокачивай карточки многократно, собирай комбо и забирай пассивный доход!",
      reply_markup=main_keyboard(),
  )


@dp.callback_query(F.data == "profile")
async def cb_profile(call: types.CallbackQuery):
  user = get_user(call.from_user.id)
  user_cards = get_user_cards(call.from_user.id)
  total_cards_bought = sum(user_cards.values())

  await call.message.edit_text(
      f"👤 **Твой профиль:**\n\n"
      f"💎 Баланс: **{int(user['balance'])}** кристаллов\n"
      f"⚡ Прибыль в час: **+{int(user['pnl'])}** / час\n"
      f"🃏 Всего прокачек карточек: **{total_cards_bought}**",
      reply_markup=main_keyboard(),
  )


@dp.callback_query(F.data == "mine")
async def cb_mine(call: types.CallbackQuery):
  user_id = call.from_user.id
  user_cards = get_user_cards(user_id)
  buttons = []

  for card_id, card in CARDS.items():
    current_level = user_cards.get(card_id, 0)

    # Считаем актуальную стоимость по формуле с коэффициентом
    current_cost = int(card["base_cost"] * (card["multiplier"] ** current_level))
    current_pnl_gain = card["base_pnl"] * (current_level + 1)

    btn_text = (
        f"{card['name']} [ур. {current_level}] | +{current_pnl_gain}/ч | 💰"
        f" {current_cost} 💎"
    )
    buttons.append(
        [InlineKeyboardButton(text=btn_text, callback_data=f"buy_{card_id}")]
    )

  buttons.append(
      [InlineKeyboardButton(text="⬅️ Назад", callback_data="profile")]
  )

  await call.message.edit_text(
      "⛏️ **Магазин карточек:**\nПокупай улучшения, чтобы разгонять пассивный"
      " доход!",
      reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
  )


@dp.callback_query(F.data.startswith("buy_"))
async def cb_buy(call: types.CallbackQuery):
  card_id = call.data.split("_")[1]
  user_id = call.from_user.id
  user = get_user(user_id)
  card = CARDS.get(card_id)

  user_cards = get_user_cards(user_id)
  current_level = user_cards.get(card_id, 0)

  # Считаем текущую стоимость для текущего уровня карточки
  current_cost = int(card["base_cost"] * (card["multiplier"] ** current_level))

  if user["balance"] < current_cost:
    await call.answer(
        f"Не хватает кристаллов! Нужно: {current_cost}", show_alert=True
    )
    return

  # Покупка / Улучшение
  new_balance = user["balance"] - current_cost
  # Доход увеличивается на базовое значение карточки за каждый новый уровень
  pnl_addition = card["base_pnl"]
  new_pnl = user["pnl"] + pnl_addition
  new_level = current_level + 1

  # Сохраняем в базу данных
  conn = sqlite3.connect("kristall.db")
  cursor = conn.cursor()
  # Обновляем баланс и общий PnL игрока
  cursor.execute(
      "UPDATE users SET balance = ?, pnl = ? WHERE user_id = ?",
      (new_balance, new_pnl, user_id),
  )
  # Обновляем уровень конкретной карточки
  cursor.execute(
      """
        INSERT INTO user_cards (user_id, card_id, level) VALUES (?, ?, ?)
        ON CONFLICT(user_id, card_id) DO UPDATE SET level = ?
    """,
      (user_id, card_id, new_level, new_level),
  )
  conn.commit()
  conn.close()

  await call.answer(
      f"✅ Успешно! {card['name']} прокачана до {new_level} уровня!"
  )
  await cb_mine(call)


@dp.callback_query(F.data == "check_combo")
async def cb_combo(call: types.CallbackQuery):
  user_id = call.from_user.id
  user_cards = get_user_cards(user_id)

  # Проверка: открыты ли все карточки из комбо хотя бы на 1-й уровень
  has_combo = all(
      user_cards.get(card, 0) > 0 for card in TODAY_COMBO
  )

  if has_combo:
    conn = sqlite3.connect("kristall.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET balance = balance + 5000 WHERE user_id = ?", (user_id,)
    )
    conn.commit()
    conn.close()
    await call.answer(
        "🎉 Поздравляем! Ты собрал Комбо Дня и получил +5000 кристаллов!",
        show_alert=True,
    )
  else:
    await call.answer(
        "❌ Ты ещё не прокачал нужные карточки для комбо (нужен 1+ уровень)!",
        show_alert=True,
    )


async def main():
  if not TOKEN:
    raise SystemExit("BOT_TOKEN не найден!")
  init_db()
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
