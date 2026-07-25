from dotenv import load_dotenv
from app.telegram_bot import run_bot

if __name__ == "__main__":
    load_dotenv()
    run_bot()
