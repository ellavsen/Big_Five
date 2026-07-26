#!/bin/bash
#
# Поднимает всю систему одной командой: веб-сервис, туннель, бота.
#
# Главное, ради чего скрипт вообще написан: бесплатный туннель Cloudflare выдаёт
# НОВЫЙ случайный адрес при каждом запуске, а адрес зашит в .env и по нему
# строится кнопка «Открыть карту». Вписывать его руками — значит однажды забыть
# и получить кнопку, ведущую в никуда. Так уже случалось дважды.
#
# Здесь адрес выцепляется из лога туннеля и подставляется в .env сам.
#
# Остановка — Ctrl+C: гасятся только те процессы, которые запустил этот скрипт.
# Именно поэтому PID'ы запоминаются, а не ищутся потом через pkill по имени:
# широкий pkill однажды прибил постороннюю службу, к проекту отношения не имевшую.

set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
LOG_DIR="logs"
WEB_LOG="$LOG_DIR/web.log"
TUNNEL_LOG="$LOG_DIR/tunnel.log"

WEB_PID=""
TUNNEL_PID=""

say()  { printf "\n\033[1m%s\033[0m\n" "$*"; }
ok()   { printf "   ✓ %s\n" "$*"; }
warn() { printf "   ! %s\n" "$*"; }
die()  { printf "\n\033[31m✗ %s\033[0m\n\n" "$*" >&2; exit 1; }

cleanup() {
    # Гасим только то, что действительно запустили, и сообщаем только о том,
    # что действительно останавливаем: «бот остановлен» на упавшей проверке
    # окружения — это ложь, которая сбивает с толку при разборе.
    if [ -z "$TUNNEL_PID" ] && [ -z "$WEB_PID" ]; then
        return
    fi

    printf "\n"
    say "Останавливаю"
    [ -n "$TUNNEL_PID" ] && kill "$TUNNEL_PID" 2>/dev/null && ok "туннель остановлен"
    [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null && ok "веб-сервис остановлен"
    printf "\nПрофиль в базе никуда не делся — он переживает выключение.\n\n"
}
trap cleanup EXIT INT TERM

mkdir -p "$LOG_DIR"

# --- 1. Проверки до запуска ------------------------------------------------
# Лучше отказаться сразу и понятно, чем упасть на середине.

say "1/5  Проверяю окружение"

[ -d venv ] || die "Нет папки venv. Создайте: python3.12 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
[ -f .env ] || die "Нет файла .env. Скопируйте шаблон: cp .env.example .env — и заполните ключи."

source venv/bin/activate
ok "venv активирован"

for var in TELEGRAM_BOT_TOKEN OPENAI_API_KEY DATABASE_URL; do
    grep -qE "^${var}=.+" .env || die "В .env не заполнен $var"
done
ok ".env заполнен"

pg_isready -q || die "PostgreSQL не отвечает. Запустите: brew services start postgresql@16"
ok "PostgreSQL отвечает"

command -v cloudflared >/dev/null || die "Нет cloudflared. Установите: brew install cloudflared"
ok "cloudflared на месте"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    die "Порт $PORT уже занят. Освободите его или запустите с другим: PORT=8010 ./run.sh"
fi
ok "порт $PORT свободен"

# --- 2. Веб-сервис ---------------------------------------------------------

say "2/5  Запускаю веб-сервис Mini App"

uvicorn app.web:app --port "$PORT" --log-level warning > "$WEB_LOG" 2>&1 &
WEB_PID=$!

for _ in $(seq 30); do
    curl -sf -o /dev/null "http://127.0.0.1:$PORT/" && break
    sleep 1
done
curl -sf -o /dev/null "http://127.0.0.1:$PORT/" || die "Веб-сервис не поднялся. Смотрите $WEB_LOG"
ok "страница отвечает на http://127.0.0.1:$PORT/ (лог: $WEB_LOG)"

# --- 3. Туннель ------------------------------------------------------------
#
# --protocol http2 обязателен: в некоторых сетях режется UDP, и QUIC-рукопожатие
# висит до бесконечности с «handshake did not complete in time».

say "3/5  Поднимаю HTTPS-туннель"

: > "$TUNNEL_LOG"
cloudflared tunnel --url "http://localhost:$PORT" --protocol http2 > "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

URL=""
for _ in $(seq 60); do
    URL=$(grep -o "https://[a-z0-9-]*\.trycloudflare\.com" "$TUNNEL_LOG" 2>/dev/null | head -1 || true)
    [ -n "$URL" ] && grep -q "Registered tunnel connection" "$TUNNEL_LOG" && break
    sleep 1
done

[ -n "$URL" ] || die "Туннель не выдал адрес за минуту. Смотрите $TUNNEL_LOG"
ok "адрес получен: $URL"

# Проверяем снаружи, а не «на глаз». Быстрый туннель умеет умирать молча:
# регистрация снимается на стороне Cloudflare, процесс висит и переподключается
# в пустоту, а Telegram показывает человеку просто ошибку.
REACHABLE=""
for _ in $(seq 15); do
    if curl -sf -o /dev/null --max-time 10 "$URL/"; then REACHABLE="да"; break; fi
    sleep 3
done

if [ -n "$REACHABLE" ]; then
    ok "адрес отвечает из интернета"
else
    # Не выходим: бывает, что имя не резолвится именно с этой машины
    # (DNS провайдера ещё не подхватил свежий поддомен), а с телефона всё открывается.
    warn "с этого компьютера адрес не открылся — с телефона может работать"
    warn "если карта в Telegram не откроется, перезапустите скрипт: адрес будет новый"
fi

# --- 4. Адрес в .env -------------------------------------------------------

say "4/5  Прописываю адрес для кнопки «Открыть карту»"

python - "$URL" <<'PY'
import sys
from pathlib import Path

url = sys.argv[1]
env = Path(".env")
lines = [ln for ln in env.read_text(encoding="utf-8").splitlines() if not ln.startswith("WEBAPP_URL=")]
lines.append(f"WEBAPP_URL={url}")
env.write_text("\n".join(lines) + "\n", encoding="utf-8")
PY
ok "WEBAPP_URL обновлён в .env"

# --- 5. Бот ----------------------------------------------------------------

say "5/5  Запускаю бота"

printf "\n\033[1mВсё поднято.\033[0m\n\n"
printf "   бот      @akmebobot — пишите ему в Telegram\n"
printf "   карта    %s\n" "$URL"
printf "   логи     %s, %s\n" "$WEB_LOG" "$TUNNEL_LOG"
printf "\n   Остановить всё — Ctrl+C. Не закрывайте это окно.\n\n"

# Бот в переднем плане: пока он работает, скрипт держит остальное. Ctrl+C гасит
# бота, а trap следом убирает веб-сервис и туннель.
python -m app.main
