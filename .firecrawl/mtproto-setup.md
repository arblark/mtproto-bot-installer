#!/bin/bash

set -e

\# ─────────────────────────────────────────────────────────────
\# MTProto Proxy — автоматическая установка (nineseconds/mtg)
\# ─────────────────────────────────────────────────────────────

CONFIG\_DIR="/etc/mtproto-proxy"
CONFIG\_FILE="${CONFIG\_DIR}/config"
LOG\_FILE="/var/log/mtproto-setup.log"

RED='\\033\[0;31m'\
GREEN='\\033\[0;32m'\
YELLOW='\\033\[1;33m'\
CYAN='\\033\[0;36m'\
BOLD='\\033\[1m'\
NC='\\033\[0m'\
\
AUTO\_MODE=false\
\
print\_header() {\
 echo ""\
 echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"\
 echo -e "${CYAN}║${BOLD} MTProto Proxy — Автоматическая установка ${NC}${CYAN}║${NC}"\
 echo -e "${CYAN}║ nineseconds/mtg v2 (Docker) ║${NC}"\
 echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"\
 echo ""\
}\
\
check\_root() {\
 if \[\[ $EUID -ne 0 \]\]; then\
 echo -e "${RED}Ошибка: скрипт нужно запускать от root (sudo)${NC}"\
 exit 1\
 fi\
}\
\
detect\_ip() {\
 local ip=""\
 ip=$(curl -4 -s --max-time 5 https://ifconfig.me 2>/dev/null) \\
 \|\| ip=$(curl -4 -s --max-time 5 https://api.ipify.org 2>/dev/null) \\
 \|\| ip=$(curl -4 -s --max-time 5 https://icanhazip.com 2>/dev/null) \\
 \|\| ip=$(hostname -I 2>/dev/null \| awk '{print $1}') \\
 \|\| ip="YOUR\_SERVER\_IP"\
 echo "$ip"\
}\
\
prompt\_value() {\
 local varname="$1"\
 local description="$2"\
 local default="$3"\
\
 if \[\[ "$AUTO\_MODE" == true \]\]; then\
 eval "$varname=\\"$default\\""\
 return\
 fi\
\
 echo -en "${YELLOW}${description}${NC} \[${GREEN}${default}${NC}\]: "\
 read -r input\
 input="${input:-$default}"\
 eval "$varname=\\"$input\\""\
}\
\
prompt\_yes\_no() {\
 local prompt\_text="$1"\
 local default="${2:-y}"\
\
 if \[\[ "$AUTO\_MODE" == true \]\]; then\
 \[\[ "$default" == "y" \]\]\
 return\
 fi\
\
 if \[\[ "$default" == "y" \]\]; then\
 echo -en "${YELLOW}${prompt\_text}${NC} \[${GREEN}Y/n${NC}\]: "\
 else\
 echo -en "${YELLOW}${prompt\_text}${NC} \[${GREEN}y/N${NC}\]: "\
 fi\
 read -r answer\
 answer="${answer:-$default}"\
 \[\[ "${answer,,}" == "y" \|\| "${answer,,}" == "yes" \]\]\
}\
\
save\_config() {\
 mkdir -p "$CONFIG\_DIR"\
 cat > "$CONFIG\_FILE" </dev/null; then\
 echo -e "${GREEN}✓ Docker уже установлен: $(docker --version)${NC}"\
 return\
 fi\
\
 echo -e "${CYAN}➜ Установка Docker...${NC}"\
\
 if command -v apt-get &>/dev/null; then\
 apt-get update -qq\
 apt-get install -y -qq docker.io\
 elif command -v yum &>/dev/null; then\
 yum install -y docker\
 systemctl start docker\
 elif command -v dnf &>/dev/null; then\
 dnf install -y docker\
 systemctl start docker\
 else\
 echo -e "${YELLOW}➜ Пакетный менеджер не найден, пробуем официальный скрипт Docker...${NC}"\
 curl -fsSL https://get.docker.com \| sh\
 fi\
\
 systemctl enable docker\
 systemctl start docker\
 echo -e "${GREEN}✓ Docker установлен: $(docker --version)${NC}"\
}\
\
stop\_existing\_container() {\
 local name="$1"\
 if docker ps -a --format '{{.Names}}' \| grep -qw "$name"; then\
 echo -e "${YELLOW}➜ Останавливаю существующий контейнер '${name}'...${NC}"\
 docker rm -f "$name" &>/dev/null \|\| true\
 fi\
}\
\
generate\_secret() {\
 local domain="$1"\
 docker run --rm nineseconds/mtg generate-secret --hex "$domain" 2>/dev/null\
}\
\
wait\_for\_container() {\
 local name="$1"\
 local max\_attempts=10\
 local attempt=0\
\
 echo -e "${CYAN}➜ Ожидание запуска контейнера...${NC}"\
 while (( attempt < max\_attempts )); do\
 if docker ps --format '{{.Names}}' \| grep -qw "$name"; then\
 echo -e "${GREEN}✓ Контейнер '${name}' запущен${NC}"\
 return 0\
 fi\
 (( attempt++ ))\
 sleep 1\
 done\
\
 echo -e "${RED}✗ Контейнер не запустился за ${max\_attempts} секунд. Логи:${NC}"\
 docker logs "$name" 2>&1 \|\| true\
 return 1\
}\
\
check\_port\_available() {\
 local port="$1"\
 local pid\_info\
\
 if command -v ss &>/dev/null; then\
 pid\_info=$(ss -tulpn 2>/dev/null \| grep ":${port} " \|\| true)\
 elif command -v netstat &>/dev/null; then\
 pid\_info=$(netstat -tulpn 2>/dev/null \| grep ":${port} " \|\| true)\
 else\
 return 0\
 fi\
\
 if \[\[ -n "$pid\_info" \]\]; then\
 echo -e "${RED}✗ Порт ${port} уже занят:${NC}"\
 echo -e " ${YELLOW}${pid\_info}${NC}"\
 echo ""\
\
 if \[\[ "$AUTO\_MODE" == true \]\]; then\
 echo -e "${RED}Ошибка: порт ${port} занят (авто-режим, прерываю)${NC}"\
 exit 1\
 fi\
\
 if prompt\_yes\_no " Продолжить установку на этот порт?" "n"; then\
 return 0\
 fi\
\
 echo -en "${YELLOW} Введите другой порт: ${NC}"\
 read -r new\_port\
 if \[\[ -z "$new\_port" \]\]; then\
 echo -e "${RED}Порт не указан, прерываю${NC}"\
 exit 1\
 fi\
 EXT\_PORT="$new\_port"\
 check\_port\_available "$EXT\_PORT"\
 fi\
}\
\
validate\_domain() {\
 local domain="$1"\
\
 if command -v dig &>/dev/null; then\
 if ! dig +short "$domain" A 2>/dev/null \| grep -qE '^\[0-9\]+\\.' ; then\
 echo -e "${YELLOW}⚠ Домен '${domain}' не резолвится. Fake-TLS может не работать.${NC}"\
 if \[\[ "$AUTO\_MODE" == false \]\]; then\
 if ! prompt\_yes\_no " Продолжить с этим доменом?" "y"; then\
 prompt\_value FAKE\_DOMAIN " Введите другой домен" "apple.com"\
 validate\_domain "$FAKE\_DOMAIN"\
 fi\
 fi\
 else\
 echo -e "${GREEN}✓ Домен '${domain}' резолвится${NC}"\
 fi\
 elif command -v nslookup &>/dev/null; then\
 if ! nslookup "$domain" 8.8.8.8 &>/dev/null; then\
 echo -e "${YELLOW}⚠ Домен '${domain}' не резолвится. Fake-TLS может не работать.${NC}"\
 if \[\[ "$AUTO\_MODE" == false \]\]; then\
 if ! prompt\_yes\_no " Продолжить с этим доменом?" "y"; then\
 prompt\_value FAKE\_DOMAIN " Введите другой домен" "apple.com"\
 validate\_domain "$FAKE\_DOMAIN"\
 fi\
 fi\
 else\
 echo -e "${GREEN}✓ Домен '${domain}' резолвится${NC}"\
 fi\
 elif command -v host &>/dev/null; then\
 if ! host "$domain" &>/dev/null; then\
 echo -e "${YELLOW}⚠ Домен '${domain}' не резолвится. Fake-TLS может не работать.${NC}"\
 else\
 echo -e "${GREEN}✓ Домен '${domain}' резолвится${NC}"\
 fi\
 fi\
}\
\
verify\_proxy\_connection() {\
 local port="$1"\
 local max\_attempts=5\
 local attempt=0\
\
 echo -e "${CYAN}➜ Проверка доступности порта ${port}...${NC}"\
 while (( attempt < max\_attempts )); do\
 if (echo >/dev/tcp/127.0.0.1/"$port") 2>/dev/null; then\
 echo -e "${GREEN}✓ Порт ${port} отвечает — прокси работает${NC}"\
 return 0\
 fi\
 (( attempt++ ))\
 sleep 1\
 done\
\
 echo -e "${YELLOW}⚠ Порт ${port} не отвечает локально (может быть нормально при NAT)${NC}"\
 return 0\
}\
\
install\_qrencode() {\
 if command -v qrencode &>/dev/null; then\
 return 0\
 fi\
\
 if command -v apt-get &>/dev/null; then\
 apt-get install -y -qq qrencode &>/dev/null && return 0\
 elif command -v yum &>/dev/null; then\
 yum install -y -q qrencode &>/dev/null && return 0\
 elif command -v dnf &>/dev/null; then\
 dnf install -y -q qrencode &>/dev/null && return 0\
 fi\
\
 return 1\
}\
\
print\_qr\_code() {\
 local link="$1"\
\
 if install\_qrencode; then\
 echo -e " ${BOLD}QR-код (наведите камеру телефона):${NC}"\
 echo ""\
 qrencode -t ANSIUTF8 "$link"\
 echo ""\
 fi\
}\
\
open\_firewall\_port() {\
 local port="$1"\
\
 if command -v ufw &>/dev/null; then\
 echo -e "${CYAN}➜ Открываю порт ${port} в UFW...${NC}"\
 ufw allow "${port}/tcp" &>/dev/null\
 echo -e "${GREEN}✓ Порт ${port}/tcp открыт в UFW${NC}"\
 fi\
\
 if command -v firewall-cmd &>/dev/null; then\
 echo -e "${CYAN}➜ Открываю порт ${port} в firewalld...${NC}"\
 firewall-cmd --permanent --add-port="${port}/tcp" &>/dev/null\
 firewall-cmd --reload &>/dev/null\
 echo -e "${GREEN}✓ Порт ${port}/tcp открыт в firewalld${NC}"\
 fi\
}\
\
close\_firewall\_port() {\
 local port="$1"\
\
 if command -v ufw &>/dev/null; then\
 ufw delete allow "${port}/tcp" &>/dev/null \|\| true\
 echo -e "${GREEN}✓ Порт ${port}/tcp закрыт в UFW${NC}"\
 fi\
\
 if command -v firewall-cmd &>/dev/null; then\
 firewall-cmd --permanent --remove-port="${port}/tcp" &>/dev/null \|\| true\
 firewall-cmd --reload &>/dev/null\
 echo -e "${GREEN}✓ Порт ${port}/tcp закрыт в firewalld${NC}"\
 fi\
}\
\
print\_result() {\
 local tme\_link="https://t.me/proxy?server=${SERVER\_IP}&port=${EXT\_PORT}&secret=${SECRET}"\
 local tg\_link="tg://proxy?server=${SERVER\_IP}&port=${EXT\_PORT}&secret=${SECRET}"\
\
 echo ""\
 echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"\
 echo -e "${CYAN}║${BOLD} Установка завершена! ${NC}${CYAN}║${NC}"\
 echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"\
 echo ""\
 echo -e " ${BOLD}Сервер:${NC} ${SERVER\_IP}"\
 echo -e " ${BOLD}Порт:${NC} ${EXT\_PORT}"\
 echo -e " ${BOLD}Секрет:${NC} ${SECRET}"\
 echo -e " ${BOLD}Домен:${NC} ${FAKE\_DOMAIN}"\
 echo -e " ${BOLD}DNS:${NC} ${DNS\_SERVER}"\
 echo -e " ${BOLD}Контейнер:${NC} ${CONTAINER\_NAME}"\
 echo ""\
 echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
 echo -e " ${BOLD}Ссылки для подключения в Telegram:${NC}"\
 echo ""\
 echo -e " ${GREEN}${tme\_link}${NC}"\
 echo ""\
 echo -e " ${GREEN}${tg\_link}${NC}"\
 echo ""\
 echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
\
 print\_qr\_code "$tme\_link"\
\
 echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
 echo -e " ${BOLD}Полезные команды:${NC}"\
 echo -e " Статус: $0 --status"\
 echo -e " Ссылки: $0 --show"\
 echo -e " Обновить: $0 --update"\
 echo -e " Удалить: $0 --uninstall"\
 echo ""\
}\
\
\# ─── Команда: --status ───────────────────────────────────────\
\
do\_status() {\
 check\_root\
\
 if ! load\_config; then\
 echo -e "${RED}MTProto Proxy не установлен (конфигурация не найдена)${NC}"\
 exit 1\
 fi\
\
 local name="${CONTAINER\_NAME:-mtproto}"\
\
 echo ""\
 echo -e "${BOLD}MTProto Proxy — Статус${NC}"\
 echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
\
 if docker ps --format '{{.Names}}' 2>/dev/null \| grep -qw "$name"; then\
 local status\_line\
 status\_line=$(docker ps --format 'table {{.Status}}\\t{{.Ports}}' --filter "name=^${name}$" \| tail -1)\
 echo -e " ${BOLD}Состояние:${NC} ${GREEN}работает${NC}"\
 echo -e " ${BOLD}Детали:${NC} ${status\_line}"\
 elif docker ps -a --format '{{.Names}}' 2>/dev/null \| grep -qw "$name"; then\
 local status\_line\
 status\_line=$(docker ps -a --format '{{.Status}}' --filter "name=^${name}$" \| tail -1)\
 echo -e " ${BOLD}Состояние:${NC} ${RED}остановлен${NC}"\
 echo -e " ${BOLD}Детали:${NC} ${status\_line}"\
 else\
 echo -e " ${BOLD}Состояние:${NC} ${RED}контейнер не найден${NC}"\
 fi\
\
 echo -e " ${BOLD}Сервер:${NC} ${SERVER\_IP}"\
 echo -e " ${BOLD}Порт:${NC} ${EXT\_PORT}"\
 echo -e " ${BOLD}Секрет:${NC} ${SECRET}"\
 echo -e " ${BOLD}Домен:${NC} ${FAKE\_DOMAIN}"\
 echo -e " ${BOLD}DNS:${NC} ${DNS\_SERVER}"\
 echo -e " ${BOLD}Контейнер:${NC} ${name}"\
\
 echo ""\
 echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
 echo -e " ${BOLD}Ссылки:${NC}"\
 echo -e " ${GREEN}https://t.me/proxy?server=${SERVER\_IP}&port=${EXT\_PORT}&secret=${SECRET}${NC}"\
 echo -e " ${GREEN}tg://proxy?server=${SERVER\_IP}&port=${EXT\_PORT}&secret=${SECRET}${NC}"\
 echo ""\
 exit 0\
}\
\
\# ─── Команда: --show ─────────────────────────────────────────\
\
do\_show() {\
 check\_root\
\
 if ! load\_config; then\
 echo -e "${RED}MTProto Proxy не установлен (конфигурация не найдена)${NC}"\
 exit 1\
 fi\
\
 local tme\_link="https://t.me/proxy?server=${SERVER\_IP}&port=${EXT\_PORT}&secret=${SECRET}"\
 local tg\_link="tg://proxy?server=${SERVER\_IP}&port=${EXT\_PORT}&secret=${SECRET}"\
\
 echo ""\
 echo -e "${BOLD}MTProto Proxy — Ссылки для подключения${NC}"\
 echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
 echo ""\
 echo -e " ${GREEN}${tme\_link}${NC}"\
 echo ""\
 echo -e " ${GREEN}${tg\_link}${NC}"\
 echo ""\
 echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
\
 print\_qr\_code "$tme\_link"\
\
 exit 0\
}\
\
\# ─── Команда: --uninstall ────────────────────────────────────\
\
do\_uninstall() {\
 print\_header\
 check\_root\
\
 local name="mtproto"\
 local port=""\
\
 if load\_config; then\
 name="${CONTAINER\_NAME:-mtproto}"\
 port="${EXT\_PORT}"\
 fi\
\
 echo -e "${YELLOW}➜ Удаление MTProto Proxy...${NC}"\
\
 if docker ps -a --format '{{.Names}}' \| grep -qw "$name"; then\
 docker rm -f "$name" &>/dev/null \|\| true\
 echo -e "${GREEN}✓ Контейнер '${name}' удалён${NC}"\
 else\
 echo -e "${YELLOW} Контейнер '${name}' не найден${NC}"\
 fi\
\
 if \[\[ -n "$port" \]\]; then\
 close\_firewall\_port "$port"\
 fi\
\
 if prompt\_yes\_no " Удалить Docker-образ nineseconds/mtg?" "n"; then\
 docker rmi nineseconds/mtg &>/dev/null \|\| true\
 echo -e "${GREEN}✓ Образ удалён${NC}"\
 fi\
\
 if prompt\_yes\_no " Удалить конфигурацию (${CONFIG\_DIR})?" "n"; then\
 rm -rf "$CONFIG\_DIR"\
 echo -e "${GREEN}✓ Конфигурация удалена${NC}"\
 fi\
\
 echo ""\
 echo -e "${GREEN}✓ MTProto Proxy полностью удалён${NC}"\
 exit 0\
}\
\
\# ─── Команда: --update ───────────────────────────────────────\
\
do\_update() {\
 print\_header\
 check\_root\
\
 if ! load\_config; then\
 echo -e "${RED}Ошибка: конфигурация не найдена (${CONFIG\_FILE}).${NC}"\
 echo -e "${YELLOW}Сначала выполните установку: $0${NC}"\
 exit 1\
 fi\
\
 local name="${CONTAINER\_NAME:-mtproto}"\
\
 echo -e "${CYAN}➜ Обновление образа nineseconds/mtg...${NC}"\
 docker pull nineseconds/mtg\
 echo -e "${GREEN}✓ Образ обновлён${NC}"\
\
 stop\_existing\_container "$name"\
\
 echo -e "${CYAN}➜ Перезапуск контейнера с сохранёнными параметрами...${NC}"\
 docker run -d \\
 --name "$name" \\
 --restart always \\
 -p "${EXT\_PORT}:${INTERNAL\_PORT}" \\
 --dns "$DNS\_SERVER" \\
 nineseconds/mtg simple-run \\
 -n "$DNS\_SERVER" \\
 -i "$IP\_PREFER" \\
 "0.0.0.0:${INTERNAL\_PORT}" \\
 "$SECRET"\
\
 if wait\_for\_container "$name"; then\
 verify\_proxy\_connection "$EXT\_PORT"\
 print\_result\
 else\
 exit 1\
 fi\
 exit 0\
}\
\
\# ─── Обработка аргументов ────────────────────────────────────\
\
case "${1:-}" in\
 --uninstall\|-u)\
 do\_uninstall\
 ;;\
 --update\|-U)\
 do\_update\
 ;;\
 --status\|-s)\
 do\_status\
 ;;\
 --show)\
 do\_show\
 ;;\
 --auto\|-a)\
 AUTO\_MODE=true\
 ;;\
 --help\|-h)\
 echo "Использование: $0 \[ОПЦИЯ\]"\
 echo ""\
 echo " (без опций) Интерактивная установка / переустановка"\
 echo " --auto, -a Установка без вопросов (значения по умолчанию или из env)"\
 echo " --update, -U Обновить образ и перезапустить контейнер"\
 echo " --uninstall, -u Удалить контейнер, образ и конфигурацию"\
 echo " --status, -s Показать статус прокси"\
 echo " --show Показать ссылки для подключения и QR-код"\
 echo " --help, -h Показать эту справку"\
 echo ""\
 echo "Переменные окружения (для --auto):"\
 echo " MT\_SERVER\_IP IP сервера (по умолчанию: автоопределение)"\
 echo " MT\_PORT Внешний порт (по умолчанию: 443)"\
 echo " MT\_DOMAIN Домен маскировки (по умолчанию: apple.com)"\
 echo " MT\_DNS DNS сервер (по умолчанию: 1.1.1.1)"\
 echo " MT\_IP\_MODE Режим IP (по умолчанию: prefer-ipv4)"\
 echo " MT\_CONTAINER Имя контейнера (по умолчанию: mtproto)"\
 exit 0\
 ;;\
esac\
\
\# ─── Основной поток: установка ───────────────────────────────\
\
print\_header\
check\_root\
\
SERVER\_IP=$(detect\_ip)\
\
if \[\[ "$AUTO\_MODE" == true \]\]; then\
 echo -e "${CYAN}Режим автоматической установки (--auto)${NC}"\
fi\
\
echo -e "${CYAN}Обнаруженный IP сервера: ${GREEN}${SERVER\_IP}${NC}"\
\
SAVED\_SECRET=""\
SAVED\_DOMAIN=""\
if load\_config; then\
 SAVED\_SECRET="$SECRET"\
 SAVED\_DOMAIN="$FAKE\_DOMAIN"\
 echo -e "${CYAN}Найдена предыдущая конфигурация (${CONFIG\_FILE})${NC}"\
fi\
\
echo ""\
if \[\[ "$AUTO\_MODE" == false \]\]; then\
 echo -e "${BOLD}Настройка параметров прокси (Enter — значение по умолчанию):${NC}"\
 echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
fi\
\
prompt\_value SERVER\_IP " IP сервера" "${MT\_SERVER\_IP:-$SERVER\_IP}"\
prompt\_value EXT\_PORT " Внешний порт" "${MT\_PORT:-${EXT\_PORT:-443}}"\
prompt\_value INTERNAL\_PORT " Внутренний порт контейнера" "${INTERNAL\_PORT:-3128}"\
prompt\_value FAKE\_DOMAIN " Домен маскировки (fake-tls)" "${MT\_DOMAIN:-${FAKE\_DOMAIN:-apple.com}}"\
prompt\_value DNS\_SERVER " DNS сервер" "${MT\_DNS:-${DNS\_SERVER:-1.1.1.1}}"\
prompt\_value IP\_PREFER " Режим IP (prefer-ipv4/prefer-ipv6/only-ipv4/only-ipv6)" "${MT\_IP\_MODE:-${IP\_PREFER:-prefer-ipv4}}"\
prompt\_value CONTAINER\_NAME " Имя контейнера" "${MT\_CONTAINER:-${CONTAINER\_NAME:-mtproto}}"\
\
echo ""\
echo -e "${CYAN}──────────────────────────────────────────────────${NC}"\
\
\# ─── Проверка порта ──────────────────────────────────────────\
\
check\_port\_available "$EXT\_PORT"\
\
\# ─── Валидация домена ────────────────────────────────────────\
\
validate\_domain "$FAKE\_DOMAIN"\
\
\# ─── Обновление системы ──────────────────────────────────────\
\
echo -e "${CYAN}➜ Обновление системы...${NC}"\
if command -v apt-get &>/dev/null; then\
 apt-get update -qq && apt-get upgrade -y -qq\
elif command -v yum &>/dev/null; then\
 yum update -y -q\
elif command -v dnf &>/dev/null; then\
 dnf upgrade -y -q\
fi\
echo -e "${GREEN}✓ Система обновлена${NC}"\
\
install\_docker\
\
echo -e "${CYAN}➜ Загрузка образа nineseconds/mtg...${NC}"\
docker pull nineseconds/mtg\
echo -e "${GREEN}✓ Образ загружен${NC}"\
\
\# ─── Секрет: переиспользование или генерация нового ──────────\
\
REUSE\_SECRET=false\
if \[\[ -n "$SAVED\_SECRET" \]\]; then\
 if \[\[ "$FAKE\_DOMAIN" == "$SAVED\_DOMAIN" \]\]; then\
 echo ""\
 echo -e "${CYAN}Найден сохранённый секрет от предыдущей установки.${NC}"\
 if prompt\_yes\_no " Использовать существующий секрет? (клиентские ссылки не изменятся)" "y"; then\
 SECRET="$SAVED\_SECRET"\
 REUSE\_SECRET=true\
 fi\
 else\
 echo ""\
 echo -e "${YELLOW}Домен маскировки изменился (${SAVED\_DOMAIN} → ${FAKE\_DOMAIN}), нужен новый секрет.${NC}"\
 fi\
fi\
\
if \[\[ "$REUSE\_SECRET" == false \]\]; then\
 echo -e "${CYAN}➜ Генерация секрета для домена '${FAKE\_DOMAIN}'...${NC}"\
 SECRET=$(generate\_secret "$FAKE\_DOMAIN")\
\
 if \[\[ -z "$SECRET" \]\]; then\
 echo -e "${RED}Ошибка: не удалось сгенерировать секрет${NC}"\
 exit 1\
 fi\
fi\
echo -e "${GREEN}✓ Секрет: ${SECRET}${NC}"\
\
stop\_existing\_container "$CONTAINER\_NAME"\
\
echo -e "${CYAN}➜ Запуск контейнера...${NC}"\
docker run -d \\
 --name "$CONTAINER\_NAME" \\
 --restart always \\
 -p "${EXT\_PORT}:${INTERNAL\_PORT}" \\
 --dns "$DNS\_SERVER" \\
 nineseconds/mtg simple-run \\
 -n "$DNS\_SERVER" \\
 -i "$IP\_PREFER" \\
 "0.0.0.0:${INTERNAL\_PORT}" \\
 "$SECRET"\
\
if ! wait\_for\_container "$CONTAINER\_NAME"; then\
 exit 1\
fi\
\
\# ─── Проверка соединения ─────────────────────────────────────\
\
verify\_proxy\_connection "$EXT\_PORT"\
\
\# ─── Файрвол ─────────────────────────────────────────────────\
\
open\_firewall\_port "$EXT\_PORT"\
\
\# ─── Сохранение конфигурации ─────────────────────────────────\
\
save\_config\
echo -e "${GREEN}✓ Конфигурация сохранена в ${CONFIG\_FILE}${NC}"\
\
print\_result