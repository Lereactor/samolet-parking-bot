# Session Log — Parking Bot

## 2026-02-21 — Session 1: Full Build & Deploy

### Timeline

**1. Проектирование (brainstorming)**
- Изучили стек соседнего проекта school-bot (`/c/Claude/telegram/`)
- Выбрали тип: ЖК (жилой комплекс)
- Согласовали 7 фичей: ядро, перегородили, уезжаю, гости, SOS, объявления, справочник

**2. Разработка (один проход — 20 файлов, 1875 строк)**
- Создали структуру: handlers/, services/, middlewares/, docs/
- Написали все модули, все скомпилировались с первого раза
- Initial commit → push на GitHub

**3. Инфраструктура**
- Создали бота через @BotFather → `@Samolet_parking_bot`
- PostgreSQL на Render (free, Oregon)
- Web Service на Render через API (первый раз в Frankfurt → region mismatch → пересоздан в Oregon)
- Env vars не подхватились при создании → установлены через PUT API
- Деплой прошёл → Status: live

**4. Мониторинг**
- Health check endpoint: `https://samolet-parking-bot.onrender.com/health`
- UptimeRobot: HTTP(s) monitor, interval 5 min

**5. Доработки по ходу тестирования**
- Админ проходит полную регистрацию (имя + места), автоодобряется
- Пользователь может иметь несколько мест (ввод по одному → "готово")
- Кнопки ➕ Добавить место / ➖ Удалить место
- Админ-команда `/spot add/remove/info` для управления чужими местами
- Away/back с выбором места при нескольких
- Подробная помощь для пользователей + раздел админа
- Текст "от управляющей" → "Объявление"
- Имя бота в примерах → @Samolet_parking_bot

### Git History
```
565d498 Initial commit: Parking Bot for residential complex
10f5526 Support admin as user and multiple spots per user
c672a12 Add spot management: remove spots, admin /spot command
a233c09 Detailed help text for users and admin section
```

### Issues & Fixes
| Проблема | Причина | Решение |
|----------|---------|---------|
| Deploy failed (1-й раз) | Сервис в Frankfurt, БД в Oregon | Пересоздали сервис в Oregon |
| Deploy failed (2-й раз) | Env vars пустые после создания | PUT /env-vars через API |
| Autodeploy не подхватывает | Render free tier задержка | Ручной trigger через POST /deploys |
| Админ не мог добавить место | Авторег без места | Полная регистрация с местами |
