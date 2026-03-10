# EcoFleet MCP Server

MCP сервер для работы с [EcoFleet](https://app.ecofleet.com) (fleet management) через Claude Desktop.  
Даёт Claude доступ к транспорту, задачам, клиентам, логбуку, расписаниям и отчётам.

---

## Быстрый старт

### 1. Клонировать репозиторий

```bash
git clone https://github.com/NatrixAi/ecofleet-mcp.git
cd ecofleet-mcp
```

### 2. Установить зависимости

```bash
pip install -r requirements.txt
```

### 3. Добавить в конфиг Claude Desktop

Открыть файл:
- **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

Добавить в секцию `mcpServers`:

```json
"ecofleet": {
  "command": "python3",
  "args": ["/абсолютный/путь/до/ecofleet-mcp/server.py"],
  "env": {
    "ECOFLEET_API_KEY": "ВАШ_API_КЛЮЧ",
    "ECOFLEET_BASE_URL": "https://app.ecofleet.com/seeme"
  }
}
```

> ⚠️ **ВАЖНО:** `ECOFLEET_BASE_URL` должен быть `https://app.ecofleet.com/seeme` — **без `/services` на конце**.

Где взять ключ: **app.ecofleet.com → Профиль → Settings → API key**

### 4. Перезапустить Claude Desktop

После перезапуска в Claude появятся инструменты EcoFleet.

---

## Инструменты

### Vehicles (5)
- `ecofleet_list_vehicles` — список всех транспортных средств
- `ecofleet_get_vehicle_last_data` — текущее местоположение и статус
- `ecofleet_get_vehicle_trips` — история поездок за период
- `ecofleet_get_vehicle_raw_data` — сырые GPS данные
- `ecofleet_assign_driver` — назначить водителя на ТС

### Tasks/Orders (5)
- `ecofleet_list_tasks` — список задач с фильтрацией по дате
- `ecofleet_get_task` — детали задачи
- `ecofleet_create_task` — создать задачу
- `ecofleet_update_task` — обновить задачу
- `ecofleet_delete_task` — удалить задачу

### Customers (4)
- `ecofleet_list_customers` — список клиентов
- `ecofleet_create_customer` — создать клиента
- `ecofleet_delete_customer` — удалить клиента
- `ecofleet_geocode_address` — геокодировать адрес

### Logbook (4)
- `ecofleet_get_logbook` — журнал поездок
- `ecofleet_approve_trip` — одобрить поездку
- `ecofleet_lock_trip` — заблокировать поездку
- `ecofleet_reject_trip` — отклонить поездку

### Reports (3)
- `ecofleet_list_reports` — список доступных отчётов
- `ecofleet_get_report_conf` — параметры конкретного отчёта (**обязательный шаг перед get_report**)
- `ecofleet_get_report` — получить данные отчёта (JSON/CSV/XLS/PDF)

### Work Schedule (5)
- `ecofleet_get_work_schedule` — расписание сотрудника
- `ecofleet_get_all_schedules` — расписание всех сотрудников
- `ecofleet_add_schedule` — добавить смену
- `ecofleet_remove_schedule` — удалить смену
- `ecofleet_clear_schedule_range` — очистить расписание за период

### People/Users (4)
- `ecofleet_list_users` — список пользователей и водителей
- `ecofleet_create_user` — создать пользователя
- `ecofleet_update_user` — обновить профиль
- `ecofleet_delete_user` — удалить пользователя

### OnDuty (2)
- `ecofleet_set_on_duty` — водитель на смене
- `ecofleet_set_off_duty` — водитель не на смене

### Places (1)
- `ecofleet_list_places` — список мест организации

### Expenses (3)
- `ecofleet_list_expenses` — список расходов/топлива
- `ecofleet_add_expense` — добавить расход
- `ecofleet_delete_expense` — удалить расход

### Organization (3)
- `ecofleet_list_roles` — список ролей
- `ecofleet_list_departments` — список отделов
- `ecofleet_get_action_log` — журнал действий (аудит)

### Messages/Garmin (3)
- `ecofleet_send_text_message` — отправить текст на Garmin устройство
- `ecofleet_send_stop_message` — отправить маршрутную точку на Garmin
- `ecofleet_get_message_status` — статус доставки сообщения

---

## Критические особенности API (читать обязательно)

### Формат дат — везде `YYYY-MM-DD HH:MM:SS`

Все инструменты принимающие период используют:
- `date_from`: `"2026-01-10 00:00:00"`
- `date_to`: `"2026-01-14 23:59:59"`

> ❌ Не работает: `"2026-01-10"` (без времени) для большинства endpoint-ов

### Отчёты — обязательный 3-шаговый workflow

```
1. ecofleet_list_reports        → получить список ID отчётов
2. ecofleet_get_report_conf     → узнать точные параметры отчёта
3. ecofleet_get_report          → запросить данные
```

**Шаг 2 нельзя пропускать.** Без него запрос вернёт `"No rights for this report"` — это не проблема прав, это неверные параметры.

Параметры `ecofleet_get_report`:

| Что передавать | Правильно | Неправильно |
|---------------|-----------|-------------|
| ID отчёта | `id` | `reportId` |
| Начало периода | `begTimestamp` | `from` |
| Конец периода | `endTimestamp` | `till` |
| Список ТС | `objectIds[]` (массив int) | `objectId` (строка) |
| Формат JSON | не указывать | `format=json` (не существует) |

### Rate limit

API EcoFleet: **не более 1 запроса в секунду**.  
Задержка 1.1 сек уже встроена в код — ничего настраивать не нужно.

### Известные ограничения

| Отчёт | Статус | Причина |
|-------|--------|---------|
| `customLT1` | ❌ HTTP 500 | Только для лесохозяйственных организаций ("Urėdijos") |
| `customLT2` | ❌ HTTP 500 | То же |
| `trackSummary` | ⚠️ Частично | Требует одиночный `objectId`, а не массив |

### Поле Sandėrio ID в задачах

Отчёт `newTasksReport` содержит поле `4474-18016` — это ID сделки в Kommo CRM (Sandėrio ID).  
Позволяет связывать задачи EcoFleet со сделками Kommo без доступа к WebApp.

---

## API документация

`https://app.ecofleet.com/services/apidoc/apidoc`

> Документация открывается только из браузера с активной сессией EcoFleet.

---

## История изменений

- **04.03.2026** — Исправлены параметры `ecofleet_list_tasks` (`begTimestamp`/`endTimestamp` вместо `from`/`till`); добавлен `ecofleet_get_report_conf`; исправлены параметры `ecofleet_get_report`; добавлен rate limit 1.1 сек; исправлена обработка HTTP 500
- **Начальная версия** — базовый набор инструментов
