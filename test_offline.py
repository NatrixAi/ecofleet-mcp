"""
Offline tests for EcoFleet MCP server.
No API keys required — uses mocks and env var validation only.
"""

import sys
import os
import json
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock

PASS = 0
FAIL = 0

def ok(msg):
    global PASS; PASS += 1
    print(f"  ✅ {msg}")

def fail(msg):
    global FAIL; FAIL += 1
    print(f"  ❌ {msg}")

# ── 1. Imports ────────────────────────────────────────────
print("=" * 60)
print("TEST 1: Imports")
print("=" * 60)

for mod, attr in [("httpx", "__version__"), ("pydantic", "__version__"), ("fastmcp", None)]:
    try:
        m = __import__(mod)
        ver = getattr(m, attr, "ok") if attr else "ok"
        ok(f"{mod} {ver}")
    except ImportError as e:
        fail(f"{mod}: {e}")

# ── 2. Module load ────────────────────────────────────────
print()
print("=" * 60)
print("TEST 2: Module load")
print("=" * 60)

os.environ["ECOFLEET_API_KEY"] = "test_key"
os.environ["ECOFLEET_BASE_URL"] = "https://app.ecofleet.com/seeme/services"

sys.path.insert(0, "/Users/dmitrijcernov/Documents/VASILIJ/ecofleet_mcp")

try:
    import server as E
    ok("server.py loaded successfully")
except Exception as e:
    fail(f"Failed to load server.py: {e}")
    sys.exit(1)

# ── 3. Tool registration ──────────────────────────────────
print()
print("=" * 60)
print("TEST 3: Tool registration (41 expected)")
print("=" * 60)

EXPECTED = {
    # Vehicles (5)
    "ecofleet_list_vehicles", "ecofleet_get_vehicle_last_data",
    "ecofleet_get_vehicle_trips", "ecofleet_get_vehicle_raw_data",
    "ecofleet_assign_driver",
    # Tasks (5)
    "ecofleet_list_tasks", "ecofleet_get_task", "ecofleet_create_task",
    "ecofleet_update_task", "ecofleet_delete_task",
    # Customers (4)
    "ecofleet_list_customers", "ecofleet_create_customer",
    "ecofleet_delete_customer", "ecofleet_geocode_address",
    # Logbook (4)
    "ecofleet_get_logbook", "ecofleet_approve_trip",
    "ecofleet_lock_trip", "ecofleet_reject_trip",
    # Reports (2)
    "ecofleet_list_reports", "ecofleet_get_report",
    # Work Schedule (5)
    "ecofleet_get_work_schedule", "ecofleet_get_all_schedules",
    "ecofleet_add_schedule", "ecofleet_remove_schedule",
    "ecofleet_clear_schedule_range",
    # Users / People (4)
    "ecofleet_list_users", "ecofleet_create_user",
    "ecofleet_update_user", "ecofleet_delete_user",
    # On Duty (2)
    "ecofleet_set_on_duty", "ecofleet_set_off_duty",
    # Places (1)
    "ecofleet_list_places",
    # Expenses (3)
    "ecofleet_list_expenses", "ecofleet_add_expense", "ecofleet_delete_expense",
    # Organization (3)
    "ecofleet_list_roles", "ecofleet_list_departments", "ecofleet_get_action_log",
    # Messages (3)
    "ecofleet_send_text_message", "ecofleet_send_stop_message",
    "ecofleet_get_message_status",
}

try:
    registered = {t.name for t in E.mcp._tool_manager.list_tools()}
    print(f"  Registered: {len(registered)} tools\n")
    for name in sorted(EXPECTED):
        if name in registered:
            ok(name)
        else:
            fail(f"MISSING: {name}")
    extra = registered - EXPECTED
    if extra:
        print(f"\n  ℹ️  Additional tools:")
        for t in sorted(extra): print(f"     + {t}")
except Exception as e:
    fail(f"Could not inspect tools: {e}")

# ── 4. Env var validation ─────────────────────────────────
print()
print("=" * 60)
print("TEST 4: Env var validation")
print("=" * 60)

async def test_env():
    os.environ.pop("ECOFLEET_API_KEY", None)
    result = await E.ecofleet_list_vehicles(E.ListVehiclesInput())
    if "Config error" in result or "must be set" in result:
        ok("Missing ECOFLEET_API_KEY → proper error returned")
    else:
        fail(f"Unexpected response: {result[:80]}")
    os.environ["ECOFLEET_API_KEY"] = "fake_key_for_test"

asyncio.run(test_env())

# ── 5. Pydantic model validation ──────────────────────────
print()
print("=" * 60)
print("TEST 5: Pydantic model validation")
print("=" * 60)

from pydantic import ValidationError

# 5a. ListVehiclesInput — defaults
try:
    m = E.ListVehiclesInput()
    ok("ListVehiclesInput — defaults OK")
except Exception as e:
    fail(f"ListVehiclesInput: {e}")

# 5b. ListTasksInput — pagination defaults (PaginationMixin)
try:
    m = E.ListTasksInput()
    assert m.limit == 20
    assert m.offset == 0
    ok("ListTasksInput — pagination defaults OK")
except Exception as e:
    fail(f"ListTasksInput: {e}")

# 5c. ListTasksInput — limit too high
try:
    m = E.ListTasksInput(limit=9999)
    fail(f"Should reject limit=9999 (got {m.limit})")
except ValidationError:
    ok("ListTasksInput — rejects limit > 500")

# 5d. GetTaskInput — task_id required
try:
    m = E.GetTaskInput()
    fail("Should require task_id")
except ValidationError:
    ok("GetTaskInput — requires task_id")

# 5e. GetTaskInput — valid (task_id is string in EcoFleet)
try:
    m = E.GetTaskInput(task_id="task_42")
    assert m.task_id == "task_42"
    ok("GetTaskInput — valid input OK (str ID)")
except Exception as e:
    fail(f"GetTaskInput valid: {e}")

# 5f. CreateTaskInput — title required
try:
    m = E.CreateTaskInput()
    fail("Should require title")
except ValidationError:
    ok("CreateTaskInput — requires title")

# 5g. CreateTaskInput — valid
try:
    m = E.CreateTaskInput(title="Deliver package", address="Vilnius, Gedimino pr. 1")
    assert m.title == "Deliver package"
    ok("CreateTaskInput — valid input OK")
except Exception as e:
    fail(f"CreateTaskInput valid: {e}")

# 5h. DeleteTaskInput — task_id required
try:
    m = E.DeleteTaskInput()
    fail("Should require task_id")
except ValidationError:
    ok("DeleteTaskInput — requires task_id")

# 5i. GetVehicleTripsInput — object_id required
try:
    m = E.GetVehicleTripsInput()
    fail("Should require object_id")
except ValidationError:
    ok("GetVehicleTripsInput — requires object_id")

# 5j. GetVehicleTripsInput — valid
try:
    m = E.GetVehicleTripsInput(object_id="VEH_001", date_from="2026-01-01 00:00:00", date_to="2026-01-31 23:59:59")
    assert m.object_id == "VEH_001"
    ok("GetVehicleTripsInput — valid input OK")
except Exception as e:
    fail(f"GetVehicleTripsInput valid: {e}")

# 5k. AssignDriverInput — both fields required
try:
    m = E.AssignDriverInput()
    fail("Should require object_id and driver_id")
except ValidationError:
    ok("AssignDriverInput — requires object_id + driver_id")

# 5l. SendTextMessageInput — required fields
try:
    m = E.SendTextMessageInput(device_id="DEV_1", message="Hello driver!")
    assert m.message == "Hello driver!"
    ok("SendTextMessageInput — valid input OK")
except Exception as e:
    fail(f"SendTextMessageInput: {e}")

# ── 6. Mock HTTP responses ────────────────────────────────
print()
print("=" * 60)
print("TEST 6: Mock HTTP responses")
print("=" * 60)

def _mock_client(response_data, status_code=200):
    mock_resp = MagicMock()
    mock_resp.json.return_value = response_data
    mock_resp.raise_for_status = MagicMock()
    mock_cl = AsyncMock()
    mock_cl.__aenter__ = AsyncMock(return_value=mock_cl)
    mock_cl.__aexit__ = AsyncMock(return_value=False)
    mock_cl.get = AsyncMock(return_value=mock_resp)
    mock_cl.post = AsyncMock(return_value=mock_resp)
    return mock_cl

MOCK_VEHICLES = {
    "data": [
        {"id": "VH1", "name": "Truck Alpha", "registrationNumber": "ABC123", "groupId": "G1"},
        {"id": "VH2", "name": "Van Beta",    "registrationNumber": "XYZ789", "groupId": "G2"},
    ]
}

MOCK_TASKS = {
    "data": [
        {"id": "1", "title": "Task A", "status": "pending",   "assignedDriver": "DRV1", "address": "Vilnius"},
        {"id": "2", "title": "Task B", "status": "completed", "assignedDriver": "DRV2", "address": "Kaunas"},
    ]
}

MOCK_CUSTOMERS = {
    "data": [
        {"id": 10, "name": "UAB Test Company", "address": "Gedimino pr. 1", "phone": "+37060000001"},
        {"id": 11, "name": "SIA Example",      "address": "Brīvības 5",     "phone": "+37120000002"},
    ]
}

async def test_list_vehicles_json():
    with patch("httpx.AsyncClient", return_value=_mock_client(MOCK_VEHICLES)):
        from server import ResponseFormat
        result = await E.ecofleet_list_vehicles(E.ListVehiclesInput(response_format=ResponseFormat.JSON))
    data = json.loads(result)
    vehicles = data.get("data", [])
    assert len(vehicles) == 2
    assert vehicles[0]["name"] == "Truck Alpha"
    ok("ecofleet_list_vehicles — JSON: 2 vehicles returned")

async def test_list_vehicles_markdown():
    with patch("httpx.AsyncClient", return_value=_mock_client(MOCK_VEHICLES)):
        result = await E.ecofleet_list_vehicles(E.ListVehiclesInput())
    assert "Truck Alpha" in result and "Van Beta" in result
    ok("ecofleet_list_vehicles — Markdown format OK")

async def test_list_tasks_markdown():
    with patch("httpx.AsyncClient", return_value=_mock_client(MOCK_TASKS)):
        result = await E.ecofleet_list_tasks(E.ListTasksInput())
    assert "Task A" in result or "Task B" in result or "task" in result.lower()
    ok("ecofleet_list_tasks — Markdown format OK")

async def test_list_customers_json():
    with patch("httpx.AsyncClient", return_value=_mock_client(MOCK_CUSTOMERS)):
        from server import ResponseFormat
        result = await E.ecofleet_list_customers(E.ListCustomersInput(response_format=ResponseFormat.JSON))
    data = json.loads(result)
    customers = data.get("data", [])
    assert len(customers) == 2
    ok("ecofleet_list_customers — JSON: 2 customers returned")

async def test_empty_vehicles():
    with patch("httpx.AsyncClient", return_value=_mock_client({"response": []})):
        result = await E.ecofleet_list_vehicles(E.ListVehiclesInput())
    assert "no" in result.lower() or "0" in result or "empty" in result.lower() or len(result) < 50
    ok("ecofleet_list_vehicles — empty response handled")

for coro in [test_list_vehicles_json, test_list_vehicles_markdown,
             test_list_tasks_markdown, test_list_customers_json,
             test_empty_vehicles]:
    try:
        asyncio.run(coro())
    except Exception as e:
        fail(f"{coro.__name__}: {e}")

# ── 7. HTTP error handling ────────────────────────────────
print()
print("=" * 60)
print("TEST 7: HTTP error handling")
print("=" * 60)

from httpx import HTTPStatusError, Request, Response as HResp

def _make_http_error(status_code: int):
    mock_req = MagicMock(spec=Request)
    mock_res = MagicMock(spec=HResp)
    mock_res.status_code = status_code
    mock_res.text = f"Error {status_code}"
    mock_res.json.side_effect = Exception("not json")
    err_resp = MagicMock()
    err_resp.raise_for_status.side_effect = HTTPStatusError(
        str(status_code), request=mock_req, response=mock_res
    )
    mock_cl = _mock_client({})
    mock_cl.get = AsyncMock(return_value=err_resp)
    mock_cl.post = AsyncMock(return_value=err_resp)
    return mock_cl

async def test_401():
    with patch("httpx.AsyncClient", return_value=_make_http_error(401)):
        result = await E.ecofleet_list_vehicles(E.ListVehiclesInput())
    assert "401" in result or "api key" in result.lower() or "invalid" in result.lower()
    ok("HTTP 401 → proper error message")

async def test_404():
    with patch("httpx.AsyncClient", return_value=_make_http_error(404)):
        result = await E.ecofleet_get_task(E.GetTaskInput(task_id="nonexistent_task"))
    assert "404" in result or "not found" in result.lower()
    ok("HTTP 404 → proper error message")

async def test_429():
    with patch("httpx.AsyncClient", return_value=_make_http_error(429)):
        result = await E.ecofleet_list_vehicles(E.ListVehiclesInput())
    assert "429" in result or "rate" in result.lower() or "limit" in result.lower()
    ok("HTTP 429 → proper error message")

for coro in [test_401, test_404, test_429]:
    try:
        asyncio.run(coro())
    except Exception as e:
        fail(f"{coro.__name__}: {e}")

# ── 8. Internal helpers ───────────────────────────────────
print()
print("=" * 60)
print("TEST 8: Internal helpers")
print("=" * 60)

# _creds with API key
os.environ["ECOFLEET_API_KEY"] = "test_key_123"
os.environ["ECOFLEET_BASE_URL"] = "https://app.ecofleet.com/seeme/services"
key, base_url = E._creds()
assert key == "test_key_123"
assert base_url == "https://app.ecofleet.com/seeme/services"
ok("_creds — returns correct key and base_url")

# _creds strips trailing slash
os.environ["ECOFLEET_BASE_URL"] = "https://app.ecofleet.com/seeme/services/"
key, base_url = E._creds()
assert not base_url.endswith("/")
ok("_creds — strips trailing slash from base_url")

# _creds missing key
os.environ.pop("ECOFLEET_API_KEY", None)
try:
    E._creds()
    fail("Should raise ValueError for missing key")
except ValueError as e:
    ok(f"_creds — raises ValueError for missing key")

# Restore
os.environ["ECOFLEET_API_KEY"] = "fake_key"

# _error: 401
e = HTTPStatusError("401", request=MagicMock(spec=Request), response=MagicMock(spec=HResp, status_code=401, text=""))
MagicMock(spec=HResp).json = MagicMock(side_effect=Exception())
msg = E._error(e)
assert "401" in msg
ok("_error — 401 message OK")

# _error: ValueError (config)
msg = E._error(ValueError("ECOFLEET_API_KEY environment variable must be set."))
assert "Config error" in msg
ok("_error — ValueError → Config error OK")

# _error: timeout
msg = E._error(type("Timeout", (Exception,), {})())
assert "Error" in msg
ok("_error — generic error handled")

# _fmt
result = E._fmt({"key": "value", "num": 42})
parsed = json.loads(result)
assert parsed["key"] == "value"
ok("_fmt — JSON formatting OK")

# ── Summary ───────────────────────────────────────────────
print()
print("=" * 60)
print(f"RESULTS: {PASS} passed / {FAIL} failed")
print("=" * 60)
if FAIL > 0:
    sys.exit(1)
