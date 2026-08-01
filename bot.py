import asyncio
import logging
import os
import sqlite3
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command

logging.basicConfig(level=logging.INFO)

# Получаем токен из Railway
TOKEN = os.getenv("BOT_TOKEN")

dp = Dispatcher()


def init_db():
    conn = sqlite3.connect("kristall.db")
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            balance INTEGER DEFAULT 0
        )
    """
    )
    conn.commit()
    conn.close()


@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("kristall.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

    await message.answer(
        "💎 **Привет! Добро пожаловать в Kristall Bot!**\n\n"
        "Команды бота:\n"
        "• /balance — проверить баланс кристаллов\n"
        "• /daily — получить бонусные кристаллы"
    )


@dp.message(Command("balance"))
async def cmd_balance(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("kristall.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    balance = row[0] if row else 0
    conn.close()

    await message.answer(f"💎 Твой баланс: **{balance}** кристаллов.")


@dp.message(Command("daily"))
async def cmd_daily(message: types.Message):
    user_id = message.from_user.id
    conn = sqlite3.connect("kristall.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET balance = balance + 100 WHERE user_id = ?", (user_id,)
    )
    conn.commit()
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    new_balance = cursor.fetchone()[0]
    conn.close()

    await message.answer(
        f"🎉 Вы получили **100** кристаллов!\nТеперь у вас **{new_balance}** 💎."
    )


async def main():
    if not TOKEN:
        raise SystemExit(
            "ОШИБКА: Зайди в Railway -> Variables и добавь BOT_TOKEN!"
        )

    bot = Bot(token=TOKEN)
    init_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
