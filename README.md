# EcoFleet MCP Server

MCP сервер для работы с EcoFleet (fleet management) через Claude Desktop.
Даёт Claude доступ к транспорту, задачам, клиентам, логбуку, расписаниям и отчётам.

---

## Установка (для клиента)

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
```
~/Library/Application Support/Claude/claude_desktop_config.json
```

Добавить в секцию `mcpServers`:

```json
"ecofleet": {
  "command": "python3",
  "args": ["/путь/до/ecofleet-mcp/server.py"],
  "env": {
    "ECOFLEET_API_KEY": "ВАШ_API_КЛЮЧ",
    "ECOFLEET_BASE_URL": "https://app.ecofleet.com/seeme/services"
  }
}
```

Где взять ключ: **app.ecofleet.com → Профиль → Settings → API key**

### 4. Перезапустить Claude Desktop

После перезапуска в Claude появятся 43 инструмента EcoFleet.

---

## Инструменты (43 шт.)

### Vehicles (5)
- `ecofleet_list_vehicles` — список всех транспортных средств
- `ecofleet_get_vehicle_last_data` — текущее местоположение и статус
- `ecofleet_get_vehicle_trips` — история поездок за период
- `ecofleet_get_vehicle_raw_data` — сырые GPS данные
- `ecofleet_assign_driver` — назначить водителя на ТС

### Tasks/Orders (5)
- `ecofleet_list_tasks` — список задач с фильтрацией
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

### Reports (2)
- `ecofleet_list_reports` — список доступных отчётов
- `ecofleet_get_report` — получить данные отчёта (JSON/CSV/XLS/PDF)

### WorkSchedule (5)
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
- `ecofleet_send_stop_message` — отправить маршрутную точку
- `ecofleet_get_message_status` — статус доставки сообщения

---

## Примечание по аутентификации

Сервер использует `apikey` как query-параметр. Если ваш аккаунт EcoFleet
использует другой метод аутентификации — измените переменную `ECOFLEET_BASE_URL`
или обратитесь к разработчику для настройки.
