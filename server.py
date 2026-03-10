#!/usr/bin/env python3
"""
EcoFleet MCP Server

MCP server for working with EcoFleet fleet management platform.
Provides tools for vehicles, tasks, customers, logbook, reports,
work schedules, people, expenses, organization, and messaging.

Authentication via environment variables:
  ECOFLEET_API_KEY   - your EcoFleet API key
  ECOFLEET_BASE_URL  - base URL (default: https://app.ecofleet.com/seeme/services)
"""

import asyncio
import json
import os
from typing import Optional, List, Dict, Any
from enum import Enum

import httpx
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# ─────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────

mcp = FastMCP("ecofleet_mcp")

DEFAULT_BASE_URL = "https://app.ecofleet.com/seeme"


def _creds() -> tuple[str, str]:
    api_key = os.environ.get("ECOFLEET_API_KEY", "")
    base_url = os.environ.get("ECOFLEET_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    if not api_key:
        raise ValueError("ECOFLEET_API_KEY environment variable must be set.")
    return api_key, base_url


# ─────────────────────────────────────────────
# Shared HTTP helpers
# ─────────────────────────────────────────────

# Минимальная задержка между запросами — не более 1 req/sec (требование EcoFleet API)
_RATE_LIMIT_DELAY = 1.1  # секунд

async def _get(path: str, params: Dict[str, Any] = {}) -> Any:
    api_key, base_url = _creds()
    all_params = {"key": api_key, "json": 1, **{k: v for k, v in params.items() if v is not None}}
    await asyncio.sleep(_RATE_LIMIT_DELAY)
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{base_url}{path}", params=all_params)
        if r.status_code == 500:
            try:
                body = r.json()
                msg = body.get("errormessage") or "Internal server error"
            except Exception:
                msg = "Internal server error"
            raise ValueError(f"Error 500: {msg}")
        r.raise_for_status()
        return _unwrap(r.json())


async def _post(path: str, body: Dict[str, Any] = {}, params: Dict[str, Any] = {}) -> Any:
    api_key, base_url = _creds()
    all_params = {"key": api_key, "json": 1, **{k: v for k, v in params.items() if v is not None}}
    await asyncio.sleep(_RATE_LIMIT_DELAY)
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(f"{base_url}{path}", params=all_params, json=body)
        if r.status_code == 500:
            try:
                body_json = r.json()
                msg = body_json.get("errormessage") or "Internal server error"
            except Exception:
                msg = "Internal server error"
            raise ValueError(f"Error 500: {msg}")
        r.raise_for_status()
        return _unwrap(r.json())


def _flatten_xml(data: Any) -> Any:
    """Recursively flatten EcoFleet XML-to-JSON artifacts (___xmlNodeValues)."""
    if isinstance(data, dict):
        if "___xmlNodeValues" in data:
            result = []
            for item in data["___xmlNodeValues"]:
                keys = [k for k in item if not k.startswith("___")]
                result.append(item[keys[0]] if len(keys) == 1 else item)
            return result
        # Single-key dict wrapping xmlNodeValues (e.g. {"tasks": {___xmlNodeValues: [...]}})
        non_meta = [k for k in data if not k.startswith("___")]
        if len(non_meta) == 1:
            inner = data[non_meta[0]]
            if isinstance(inner, dict) and "___xmlNodeValues" in inner:
                return _flatten_xml(inner)
    return data


def _unwrap(data: Any) -> Any:
    """Unwrap standard EcoFleet API envelope: {"status": 0, "response": ...}"""
    if isinstance(data, dict) and "response" in data:
        status = data.get("status", 0)
        if status != 0:
            msg = data.get("errormessage") or data.get("error") or f"status={status}"
            raise ValueError(f"EcoFleet API error: {msg}")
        return _flatten_xml(data["response"])
    return data


def _error(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        try:
            detail = e.response.json()
        except Exception:
            detail = e.response.text
        if code == 401:
            return "Error 401: Invalid API key. Check ECOFLEET_API_KEY."
        if code == 403:
            return "Error 403: Access denied."
        if code == 404:
            return "Error 404: Resource not found. Check the ID."
        if code == 429:
            return "Error 429: Rate limit exceeded. Try again later."
        return f"Error {code}: {detail}"
    if isinstance(e, httpx.TimeoutException):
        return "Error: Request timed out after 30s."
    if isinstance(e, ValueError):
        msg = str(e)
        if msg.startswith("EcoFleet API error"):
            return msg
        return f"Config error: {e}"
    return f"Error: {type(e).__name__}: {e}"


def _fmt(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────
# Shared Pydantic models
# ─────────────────────────────────────────────

class ResponseFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"


class PaginationMixin(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    limit: Optional[int] = Field(default=20, ge=1, le=500, description="Max results (default 20)")
    offset: Optional[int] = Field(default=0, ge=0, description="Offset for pagination (default 0)")


# ═══════════════════════════════════════════════════════════
# VEHICLES
# ═══════════════════════════════════════════════════════════

class ListVehiclesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_list_vehicles",
    annotations={"title": "List EcoFleet Vehicles", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_vehicles(params: ListVehiclesInput) -> str:
    """List all vehicles in the EcoFleet organization.

    Fetches from GET /Api/Vehicles/get.
    Returns vehicle IDs, names, registration numbers, and group assignments.

    Returns:
        str: List of vehicles with basic info.
    """
    try:
        data = await _get("/Api/Vehicles/get")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", data.get("vehicles", []))
        if not items:
            return "No vehicles found."
        lines = ["## EcoFleet Vehicles", ""]
        for v in items:
            vid = v.get("id") or v.get("objectId", "")
            name = v.get("name") or v.get("objectName", "")
            reg = v.get("registrationNumber") or v.get("licensePlate", "")
            lines.append(f"- **{vid}** — {name} ({reg})")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetVehicleLastDataInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    object_id: Optional[str] = Field(default=None, description="Specific vehicle ID. Leave empty for all vehicles.")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_get_vehicle_last_data",
    annotations={"title": "Get Vehicle Last Known Position", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_vehicle_last_data(params: GetVehicleLastDataInput) -> str:
    """Get the last known position and status of vehicles in EcoFleet.

    Fetches from GET /Api/Vehicles/getLastData.
    Returns current location, speed, ignition status, driver info, and timestamp.

    Args:
        params: object_id — optional vehicle ID (empty = all vehicles)

    Returns:
        str: Current position and status for each vehicle.
    """
    try:
        p = {}
        if params.object_id:
            p["objectId"] = params.object_id
        data = await _get("/Api/Vehicles/getLastData", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No vehicle data found."
        lines = ["## Vehicle Last Known Positions", ""]
        for v in items:
            name = v.get("name") or v.get("objectName", "")
            lat = v.get("lat") or v.get("latitude", "")
            lng = v.get("lng") or v.get("longitude", "")
            speed = v.get("speed", "")
            ts = v.get("timestamp") or v.get("time", "")
            driver = v.get("driverName") or v.get("driver", "")
            lines.append(f"**{name}** | {lat},{lng} | {speed} km/h | {ts}" + (f" | {driver}" if driver else ""))
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetVehicleTripsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    object_id: str = Field(..., description="Vehicle ID (use ecofleet_list_vehicles to get IDs)")
    date_from: str = Field(..., description="Start datetime, format YYYY-MM-DD HH:MM:SS")
    date_to: str = Field(..., description="End datetime, format YYYY-MM-DD HH:MM:SS")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_get_vehicle_trips",
    annotations={"title": "Get Vehicle Trips", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_vehicle_trips(params: GetVehicleTripsInput) -> str:
    """Get trip history for a specific vehicle in EcoFleet.

    Fetches from GET /Api/Vehicles/getTrips.
    Returns journey records with start/end time, distance, duration, and addresses.

    Args:
        params: object_id, date_from, date_to (YYYY-MM-DD HH:MM:SS)

    Returns:
        str: List of trips with timestamps, distance, and locations.
    """
    try:
        data = await _get("/Api/Vehicles/getTrips", {
            "objectId": params.object_id,
            "begTimestamp": params.date_from,
            "endTimestamp": params.date_to,
        })
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return f"No trips found for vehicle {params.object_id} in the given period."
        lines = [f"## Trips for vehicle {params.object_id}", ""]
        for t in items:
            start = t.get("startTime") or t.get("from", "")
            end = t.get("endTime") or t.get("till", "")
            dist = t.get("distance", "")
            lines.append(f"- {start} → {end} | {dist} km")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetVehicleRawDataInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    object_id: str = Field(..., description="Vehicle ID")
    date_from: str = Field(..., description="Start datetime YYYY-MM-DD HH:MM:SS")
    date_to: str = Field(..., description="End datetime YYYY-MM-DD HH:MM:SS")
    response_format: ResponseFormat = Field(default=ResponseFormat.JSON)


@mcp.tool(
    name="ecofleet_get_vehicle_raw_data",
    annotations={"title": "Get Vehicle Raw GPS Data", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_vehicle_raw_data(params: GetVehicleRawDataInput) -> str:
    """Get raw historical GPS tracking data for a vehicle in EcoFleet.

    Fetches from GET /Api/Vehicles/getRawData.
    Returns timestamped GPS points with coordinates, speed, and sensor data.

    Args:
        params: object_id, date_from, date_to (YYYY-MM-DD HH:MM:SS)

    Returns:
        str: Raw GPS data points for the given period.
    """
    try:
        data = await _get("/Api/Vehicles/getRawData", {
            "objectId": params.object_id,
            "from": params.date_from,
            "till": params.date_to,
        })
        return _fmt(data)
    except Exception as e:
        return _error(e)


class AssignDriverInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    object_id: str = Field(..., description="Vehicle ID")
    driver_id: str = Field(..., description="Driver/user ID to assign")


@mcp.tool(
    name="ecofleet_assign_driver",
    annotations={"title": "Assign Driver to Vehicle", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_assign_driver(params: AssignDriverInput) -> str:
    """Assign a driver to a vehicle in EcoFleet.

    Posts to POST /Api/Vehicles/assignDriver.

    Args:
        params: object_id (vehicle), driver_id (user to assign)

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/Vehicles/assignDriver", {"objectId": params.object_id, "driverId": params.driver_id})
        return f"Driver {params.driver_id} assigned to vehicle {params.object_id}.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# TASKS / ORDERS
# ═══════════════════════════════════════════════════════════

class ListTasksInput(PaginationMixin):
    date_from: Optional[str] = Field(default=None, description="Filter tasks from datetime, format 'YYYY-MM-DD HH:MM:SS' (e.g. '2026-01-10 00:00:00')")
    date_to: Optional[str] = Field(default=None, description="Filter tasks to datetime, format 'YYYY-MM-DD HH:MM:SS' (e.g. '2026-01-14 23:59:59')")
    status: Optional[str] = Field(default=None, description="Task status filter (e.g. 'new', 'in_progress', 'done')")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_list_tasks",
    annotations={"title": "List EcoFleet Tasks/Orders", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_tasks(params: ListTasksInput) -> str:
    """List tasks/orders from EcoFleet with optional filters.

    Fetches task list with pagination.
    Returns task ID, title, status, assigned driver, and time window.

    Args:
        params: date_from, date_to, status, limit, offset

    Returns:
        str: List of tasks with key details.
    """
    try:
        p: Dict[str, Any] = {"limit": params.limit, "offset": params.offset}
        if params.date_from:
            p["begTimestamp"] = params.date_from
        if params.date_to:
            p["endTimestamp"] = params.date_to
        if params.status:
            p["status"] = params.status
        data = await _get("/Api/Tasks/get", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No tasks found."
        lines = ["## EcoFleet Tasks", ""]
        for t in items:
            tid = t.get("id", "")
            title = t.get("title") or t.get("name", "")
            status = t.get("status", "")
            driver = t.get("driverName") or t.get("assignee", "")
            lines.append(f"- **#{tid}** {title} | {status}" + (f" | {driver}" if driver else ""))
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetTaskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    task_id: str = Field(..., description="Task ID")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_get_task",
    annotations={"title": "Get EcoFleet Task Details", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_task(params: GetTaskInput) -> str:
    """Get full details of a specific task/order from EcoFleet.

    Returns complete task data: description, location, time window,
    assigned driver, forms, attachments, and subtasks.

    Args:
        params: task_id

    Returns:
        str: Full task details.
    """
    try:
        data = await _get("/Api/Tasks/getById", {"id": params.task_id})
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        task = data if isinstance(data, dict) else data.get("data", {})
        lines = [f"## Task #{params.task_id}", ""]
        for k, v in task.items():
            lines.append(f"**{k}**: {v}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class CreateTaskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: str = Field(..., description="Task title/name", min_length=1)
    address: Optional[str] = Field(default=None, description="Delivery/task address")
    time_from: Optional[str] = Field(default=None, description="Task start time YYYY-MM-DD HH:MM:SS")
    time_to: Optional[str] = Field(default=None, description="Task end time YYYY-MM-DD HH:MM:SS")
    driver_id: Optional[str] = Field(default=None, description="Driver ID to assign the task to")
    description: Optional[str] = Field(default=None, description="Task description/notes")
    customer_id: Optional[str] = Field(default=None, description="Customer ID to link the task to")


@mcp.tool(
    name="ecofleet_create_task",
    annotations={"title": "Create EcoFleet Task", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def ecofleet_create_task(params: CreateTaskInput) -> str:
    """Create a new task/order in EcoFleet.

    Posts to POST /Api/Tasks/add.
    Supports assignment to a driver with a time window.

    Args:
        params: title, address, time_from, time_to, driver_id, description, customer_id

    Returns:
        str: Created task ID and confirmation.
    """
    try:
        body: Dict[str, Any] = {"title": params.title}
        if params.address:
            body["address"] = params.address
        if params.time_from:
            body["timeFrom"] = params.time_from
        if params.time_to:
            body["timeTo"] = params.time_to
        if params.driver_id:
            body["driverId"] = params.driver_id
        if params.description:
            body["description"] = params.description
        if params.customer_id:
            body["customerId"] = params.customer_id
        data = await _post("/Api/Tasks/add", body)
        return f"Task created successfully.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class UpdateTaskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    task_id: str = Field(..., description="Task ID to update")
    title: Optional[str] = Field(default=None, description="New task title")
    address: Optional[str] = Field(default=None, description="New address")
    time_from: Optional[str] = Field(default=None, description="New start time YYYY-MM-DD HH:MM:SS")
    time_to: Optional[str] = Field(default=None, description="New end time YYYY-MM-DD HH:MM:SS")
    driver_id: Optional[str] = Field(default=None, description="New driver ID")
    description: Optional[str] = Field(default=None, description="New description")
    status: Optional[str] = Field(default=None, description="New status")


@mcp.tool(
    name="ecofleet_update_task",
    annotations={"title": "Update EcoFleet Task", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_update_task(params: UpdateTaskInput) -> str:
    """Update an existing task/order in EcoFleet. All provided fields are overwritten.

    Posts to POST /Api/Tasks/update.

    Args:
        params: task_id + any fields to update

    Returns:
        str: Confirmation or error.
    """
    try:
        body: Dict[str, Any] = {"id": params.task_id}
        if params.title:
            body["title"] = params.title
        if params.address:
            body["address"] = params.address
        if params.time_from:
            body["timeFrom"] = params.time_from
        if params.time_to:
            body["timeTo"] = params.time_to
        if params.driver_id:
            body["driverId"] = params.driver_id
        if params.description:
            body["description"] = params.description
        if params.status:
            body["status"] = params.status
        data = await _post("/Api/Tasks/update", body)
        return f"Task #{params.task_id} updated.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class DeleteTaskInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    task_id: str = Field(..., description="Task ID to delete")


@mcp.tool(
    name="ecofleet_delete_task",
    annotations={"title": "Delete EcoFleet Task", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_delete_task(params: DeleteTaskInput) -> str:
    """Delete a task/order from EcoFleet. This action is irreversible.

    Posts to POST /Api/Tasks/remove.

    Args:
        params: task_id

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/Tasks/remove", {"id": params.task_id})
        return f"Task #{params.task_id} deleted.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# CUSTOMERS
# ═══════════════════════════════════════════════════════════

class ListCustomersInput(PaginationMixin):
    search: Optional[str] = Field(default=None, description="Search by name, phone, or email")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_list_customers",
    annotations={"title": "List EcoFleet Customers", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_customers(params: ListCustomersInput) -> str:
    """List customers from EcoFleet with optional search.

    Returns customer ID, name, address, phone, and email.

    Args:
        params: search, limit, offset

    Returns:
        str: List of customers.
    """
    try:
        p: Dict[str, Any] = {"limit": params.limit, "offset": params.offset}
        if params.search:
            p["search"] = params.search
        data = await _get("/Api/Customers/get", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No customers found."
        lines = ["## EcoFleet Customers", ""]
        for c in items:
            cid = c.get("id", "")
            name = c.get("name") or c.get("title", "")
            phone = c.get("phone", "")
            email = c.get("email", "")
            lines.append(f"- **{cid}** — {name} | {phone} | {email}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class CreateCustomerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Customer name", min_length=1)
    address: Optional[str] = Field(default=None, description="Customer address")
    phone: Optional[str] = Field(default=None, description="Phone number")
    email: Optional[str] = Field(default=None, description="Email address")
    notes: Optional[str] = Field(default=None, description="Additional notes")


@mcp.tool(
    name="ecofleet_create_customer",
    annotations={"title": "Create EcoFleet Customer", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def ecofleet_create_customer(params: CreateCustomerInput) -> str:
    """Create a new customer in EcoFleet.

    Args:
        params: name, address, phone, email, notes

    Returns:
        str: Created customer ID and confirmation.
    """
    try:
        body: Dict[str, Any] = {"name": params.name}
        for field, key in [("address", "address"), ("phone", "phone"), ("email", "email"), ("notes", "notes")]:
            val = getattr(params, field)
            if val:
                body[key] = val
        data = await _post("/Api/Customers/add", body)
        return f"Customer created.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class DeleteCustomerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    customer_id: str = Field(..., description="Customer ID to delete")


@mcp.tool(
    name="ecofleet_delete_customer",
    annotations={"title": "Delete EcoFleet Customer", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_delete_customer(params: DeleteCustomerInput) -> str:
    """Delete a customer from EcoFleet. Irreversible.

    Args:
        params: customer_id

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/Customers/remove", {"id": params.customer_id})
        return f"Customer #{params.customer_id} deleted.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class GeocodeCustomerInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    address: str = Field(..., description="Address to geocode (e.g. 'Gedimino pr. 1, Vilnius')")


@mcp.tool(
    name="ecofleet_geocode_address",
    annotations={"title": "Geocode Address via EcoFleet", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_geocode_address(params: GeocodeCustomerInput) -> str:
    """Geocode an address to coordinates using EcoFleet's geocoding service.

    Args:
        params: address string

    Returns:
        str: Latitude and longitude for the given address.
    """
    try:
        data = await _get("/Api/Customers/geocode", {"address": params.address})
        return _fmt(data)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# LOGBOOK
# ═══════════════════════════════════════════════════════════

class GetLogbookInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    object_id: Optional[str] = Field(default=None, description="Vehicle ID (empty = all vehicles)")
    date_from: str = Field(..., description="Start date YYYY-MM-DD")
    date_to: str = Field(..., description="End date YYYY-MM-DD")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_get_logbook",
    annotations={"title": "Get EcoFleet Logbook", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_logbook(params: GetLogbookInput) -> str:
    """Get logbook/trip history from EcoFleet for compliance and reporting.

    Returns trip records with start/end, driver, distance, and approval status.

    Args:
        params: object_id (optional), date_from, date_to

    Returns:
        str: Logbook entries with status (approved/pending/rejected).
    """
    try:
        p: Dict[str, Any] = {"from": params.date_from, "till": params.date_to}
        if params.object_id:
            p["objectId"] = params.object_id
        data = await _get("/Api/Logbook/get", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No logbook entries found."
        lines = [f"## Logbook: {params.date_from} – {params.date_to}", ""]
        for t in items:
            tid = t.get("id", "")
            start = t.get("startTime") or t.get("from", "")
            end = t.get("endTime") or t.get("till", "")
            dist = t.get("distance", "")
            status = t.get("approvalStatus") or t.get("status", "")
            driver = t.get("driverName") or t.get("driver", "")
            lines.append(f"- **#{tid}** {start} → {end} | {dist} km | {status}" + (f" | {driver}" if driver else ""))
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class ApproveTripInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    trip_id: str = Field(..., description="Trip/logbook entry ID to approve")


@mcp.tool(
    name="ecofleet_approve_trip",
    annotations={"title": "Approve Logbook Trip", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_approve_trip(params: ApproveTripInput) -> str:
    """Approve a trip entry in the EcoFleet logbook.

    Args:
        params: trip_id

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/Logbook/approve", {"id": params.trip_id})
        return f"Trip #{params.trip_id} approved.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class LockTripInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    trip_id: str = Field(..., description="Trip ID to lock")
    comment: Optional[str] = Field(default=None, description="Optional comment for locking")


@mcp.tool(
    name="ecofleet_lock_trip",
    annotations={"title": "Lock Logbook Trip", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_lock_trip(params: LockTripInput) -> str:
    """Lock a trip entry in the EcoFleet logbook to prevent further edits.

    Args:
        params: trip_id, optional comment

    Returns:
        str: Confirmation or error.
    """
    try:
        body: Dict[str, Any] = {"id": params.trip_id}
        if params.comment:
            body["comment"] = params.comment
        data = await _post("/Api/Logbook/lock", body)
        return f"Trip #{params.trip_id} locked.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class RejectTripInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    trip_id: str = Field(..., description="Trip ID to reject")
    comment: Optional[str] = Field(default=None, description="Reason for rejection")


@mcp.tool(
    name="ecofleet_reject_trip",
    annotations={"title": "Reject Logbook Trip", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_reject_trip(params: RejectTripInput) -> str:
    """Reject a trip entry in the EcoFleet logbook with an optional comment.

    Args:
        params: trip_id, optional comment

    Returns:
        str: Confirmation or error.
    """
    try:
        body: Dict[str, Any] = {"id": params.trip_id}
        if params.comment:
            body["comment"] = params.comment
        data = await _post("/Api/Logbook/reject", body)
        return f"Trip #{params.trip_id} rejected.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# REPORTS
# ═══════════════════════════════════════════════════════════

class ListReportsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_list_reports",
    annotations={"title": "List Available EcoFleet Reports", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_reports(params: ListReportsInput) -> str:
    """List all available reports in EcoFleet.

    Fetches from GET /Api/Reports/listReports.
    Returns report IDs and names.

    REPORTS WORKFLOW (3 steps):
    1. ecofleet_list_reports → get report IDs
    2. ecofleet_get_report_conf(report_id) → get exact parameters for that report
    3. ecofleet_get_report(report_id, ...) → get actual data with correct params

    Returns:
        str: List of available report names and IDs.
    """
    try:
        data = await _get("/Api/Reports/listReports")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No reports found."
        lines = ["## Available EcoFleet Reports", ""]
        for r in items:
            rid = r.get("id") or r.get("reportId", "")
            name = r.get("name") or r.get("title", "")
            lines.append(f"- **{rid}** — {name}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetReportConfInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    report_id: str = Field(..., description="Report ID to get configuration for (e.g. 'triptype', 'trips')")


@mcp.tool(
    name="ecofleet_get_report_conf",
    annotations={"title": "Get EcoFleet Report Configuration", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_report_conf(params: GetReportConfInput) -> str:
    """Get input/output configuration for a specific EcoFleet report.

    ALWAYS call this before ecofleet_get_report to discover:
    - Exact parameter names required for this report
    - Parameter types (date, array_of_int, integer, string)
    - Date format requirements
    - Output columns and their data types

    Fetches from GET /Api/Reports/getReportConf.

    Args:
        params: report_id

    Returns:
        str: Report parameter schema and output column definitions.
    """
    try:
        data = await _get("/Api/Reports/getReportConf", {"id": params.report_id})
        title = data.get("title", params.report_id) if isinstance(data, dict) else params.report_id
        lines = [f"## Report Config: {title} (id: {params.report_id})", ""]

        if isinstance(data, dict):
            params_list = data.get("parameters", [])
            if params_list:
                lines.append("### Input Parameters")
                for p in params_list:
                    name = p.get("name", "")
                    ptype = p.get("type", "")
                    fmt = p.get("format", "")
                    nullable = p.get("allowNull", True)
                    fmt_str = f", format: `{fmt}`" if fmt else ""
                    null_str = " (optional)" if nullable else " (required)"
                    lines.append(f"- `{name}` — type: `{ptype}`{fmt_str}{null_str}")
                lines.append("")

            output_list = data.get("output", [])
            if output_list:
                lines.append("### Output Columns")
                for col in output_list:
                    ctitle = col.get("title", "")
                    cdata = col.get("data", "")
                    ctype = col.get("type", "")
                    unit = col.get("unit", "")
                    unit_str = f" [{unit}]" if unit else ""
                    lines.append(f"- `{cdata}` — {ctitle} ({ctype}{unit_str})")

        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetReportInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    report_id: str = Field(..., description="Report ID from ecofleet_list_reports (e.g. 'triptype', 'trips', 'places')")
    date_from: str = Field(..., description="Start datetime in format 'YYYY-MM-DD HH:MM:SS' (e.g. '2026-03-04 00:00:00')")
    date_to: str = Field(..., description="End datetime in format 'YYYY-MM-DD HH:MM:SS' (e.g. '2026-03-04 23:59:59')")
    object_ids: Optional[List[int]] = Field(default=None, description="List of vehicle IDs to filter (e.g. [23779, 23780]). Use ecofleet_list_vehicles to get IDs.")
    format: Optional[str] = Field(default=None, description="Output format: 'csv', 'xls', 'html', 'pdf'. Omit for JSON (default).")


@mcp.tool(
    name="ecofleet_get_report",
    annotations={"title": "Get EcoFleet Report Data", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_report(params: GetReportInput) -> str:
    """Get report data from EcoFleet for a specific period and report type.

    IMPORTANT: Two-step workflow required:
    1. Call ecofleet_get_report_conf with the report_id to discover exact parameters
    2. Call this tool with the correct parameters from step 1

    Fetches from GET /Api/Reports/getReport.
    Dates must be in 'YYYY-MM-DD HH:MM:SS' format (not just YYYY-MM-DD).
    Vehicle IDs are passed as array: objectIds[] (not single objectId).

    Args:
        params: report_id, date_from, date_to, object_ids (list, optional), format

    Returns:
        str: Report data in JSON (default) or requested format.
    """
    try:
        p: Dict[str, Any] = {
            "id": params.report_id,
            "begTimestamp": params.date_from,
            "endTimestamp": params.date_to,
        }
        if params.object_ids:
            for oid in params.object_ids:
                p.setdefault("objectIds[]", [])
                if not isinstance(p["objectIds[]"], list):
                    p["objectIds[]"] = [p["objectIds[]"]]
                p["objectIds[]"].append(oid)
        if params.format:
            p["format"] = params.format
        data = await _get("/Api/Reports/getReport", p)
        if isinstance(data, dict) and "data" in data:
            rows = data["data"]
            title = data.get("title", params.report_id)
            return f"## {title}\n\n" + _fmt(rows)
        return _fmt(data)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# WORK SCHEDULE
# ═══════════════════════════════════════════════════════════

class GetWorkScheduleInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_id: str = Field(..., description="Employee/user ID")
    date_from: str = Field(..., description="Start date YYYY-MM-DD")
    date_to: str = Field(..., description="End date YYYY-MM-DD")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_get_work_schedule",
    annotations={"title": "Get Employee Work Schedule", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_work_schedule(params: GetWorkScheduleInput) -> str:
    """Get the work schedule/shifts for an employee in EcoFleet.

    Fetches from GET /Api/WorkSchedule/get.

    Args:
        params: user_id, date_from, date_to

    Returns:
        str: Shift schedule with start/end times.
    """
    try:
        data = await _get("/Api/WorkSchedule/get", {
            "userId": params.user_id,
            "from": params.date_from,
            "till": params.date_to,
        })
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return f"No schedule found for user {params.user_id}."
        lines = [f"## Work Schedule for user {params.user_id}", ""]
        for s in items:
            start = s.get("startTime") or s.get("from", "")
            end = s.get("endTime") or s.get("till", "")
            lines.append(f"- {start} → {end}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetAllSchedulesInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    date_from: str = Field(..., description="Start date YYYY-MM-DD")
    date_to: str = Field(..., description="End date YYYY-MM-DD")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_get_all_schedules",
    annotations={"title": "Get All Employee Schedules", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_all_schedules(params: GetAllSchedulesInput) -> str:
    """Get work schedules for all staff in EcoFleet for a date range.

    Fetches from POST /Api/WorkSchedule/getAll.

    Args:
        params: date_from, date_to

    Returns:
        str: All employee schedules grouped by user.
    """
    try:
        data = await _post("/Api/WorkSchedule/getAll", {"from": params.date_from, "till": params.date_to})
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No schedules found."
        lines = [f"## All Work Schedules: {params.date_from} – {params.date_to}", ""]
        for s in items:
            user = s.get("userName") or s.get("userId", "")
            start = s.get("startTime") or s.get("from", "")
            end = s.get("endTime") or s.get("till", "")
            lines.append(f"- **{user}**: {start} → {end}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class AddScheduleInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_id: str = Field(..., description="Employee/user ID")
    date_from: str = Field(..., description="Shift start YYYY-MM-DD HH:MM:SS")
    date_to: str = Field(..., description="Shift end YYYY-MM-DD HH:MM:SS")


@mcp.tool(
    name="ecofleet_add_schedule",
    annotations={"title": "Add Work Schedule Entry", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def ecofleet_add_schedule(params: AddScheduleInput) -> str:
    """Add a new shift/schedule entry for an employee in EcoFleet.

    Posts to POST /Api/WorkSchedule/add.

    Args:
        params: user_id, date_from, date_to

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/WorkSchedule/add", {
            "userId": params.user_id,
            "from": params.date_from,
            "till": params.date_to,
        })
        return f"Schedule added for user {params.user_id}.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class RemoveScheduleInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    schedule_id: str = Field(..., description="Schedule entry ID to remove")


@mcp.tool(
    name="ecofleet_remove_schedule",
    annotations={"title": "Remove Work Schedule Entry", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_remove_schedule(params: RemoveScheduleInput) -> str:
    """Remove a shift entry from EcoFleet work schedule. Irreversible.

    Posts to POST /Api/WorkSchedule/remove.

    Args:
        params: schedule_id

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/WorkSchedule/remove", {"id": params.schedule_id})
        return f"Schedule entry {params.schedule_id} removed.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class ClearScheduleRangeInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_id: str = Field(..., description="Employee/user ID")
    date_from: str = Field(..., description="Range start YYYY-MM-DD")
    date_to: str = Field(..., description="Range end YYYY-MM-DD")


@mcp.tool(
    name="ecofleet_clear_schedule_range",
    annotations={"title": "Clear Work Schedule Range", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_clear_schedule_range(params: ClearScheduleRangeInput) -> str:
    """Remove ALL shift entries for an employee within a date range in EcoFleet. Irreversible.

    Posts to POST /Api/WorkSchedule/clearRange.

    Args:
        params: user_id, date_from, date_to

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/WorkSchedule/clearRange", {
            "userId": params.user_id,
            "from": params.date_from,
            "till": params.date_to,
        })
        return f"Schedule cleared for user {params.user_id} from {params.date_from} to {params.date_to}.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# PEOPLE / USERS
# ═══════════════════════════════════════════════════════════

class ListUsersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_list_users",
    annotations={"title": "List EcoFleet Users/Drivers", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_users(params: ListUsersInput) -> str:
    """List all users (drivers and staff) in the EcoFleet organization.

    Returns user ID, name, email, role, and active status.

    Returns:
        str: List of users with roles and contact info.
    """
    try:
        data = await _get("/Api/People/get")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No users found."
        lines = ["## EcoFleet Users", ""]
        for u in items:
            uid = u.get("id") or u.get("userId", "")
            name = u.get("name") or u.get("fullName", "")
            email = u.get("email", "")
            role = u.get("role") or u.get("roleName", "")
            lines.append(f"- **{uid}** — {name} | {email}" + (f" | {role}" if role else ""))
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class CreateUserInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(..., description="Full name", min_length=1)
    email: str = Field(..., description="Email address (used for login)")
    role_id: Optional[str] = Field(default=None, description="Role ID to assign")
    phone: Optional[str] = Field(default=None, description="Phone number")


@mcp.tool(
    name="ecofleet_create_user",
    annotations={"title": "Create EcoFleet User", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def ecofleet_create_user(params: CreateUserInput) -> str:
    """Create a new user (driver or staff) in EcoFleet.

    Args:
        params: name, email, role_id, phone

    Returns:
        str: Created user ID and confirmation.
    """
    try:
        body: Dict[str, Any] = {"name": params.name, "email": params.email}
        if params.role_id:
            body["roleId"] = params.role_id
        if params.phone:
            body["phone"] = params.phone
        data = await _post("/Api/People/add", body)
        return f"User created.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class UpdateUserInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_id: str = Field(..., description="User ID to update")
    name: Optional[str] = Field(default=None, description="New full name")
    email: Optional[str] = Field(default=None, description="New email address")
    role_id: Optional[str] = Field(default=None, description="New role ID")
    phone: Optional[str] = Field(default=None, description="New phone number")


@mcp.tool(
    name="ecofleet_update_user",
    annotations={"title": "Update EcoFleet User", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_update_user(params: UpdateUserInput) -> str:
    """Update an existing user's profile in EcoFleet.

    Args:
        params: user_id + any fields to update

    Returns:
        str: Confirmation or error.
    """
    try:
        body: Dict[str, Any] = {"id": params.user_id}
        for field, key in [("name", "name"), ("email", "email"), ("role_id", "roleId"), ("phone", "phone")]:
            val = getattr(params, field)
            if val:
                body[key] = val
        data = await _post("/Api/People/update", body)
        return f"User {params.user_id} updated.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class DeleteUserInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    user_id: str = Field(..., description="User ID to delete")


@mcp.tool(
    name="ecofleet_delete_user",
    annotations={"title": "Delete EcoFleet User", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_delete_user(params: DeleteUserInput) -> str:
    """Delete a user from EcoFleet. Irreversible.

    Args:
        params: user_id

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/People/remove", {"id": params.user_id})
        return f"User {params.user_id} deleted.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# ON DUTY
# ═══════════════════════════════════════════════════════════

class DutyInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    driver_id: str = Field(..., description="Driver/user ID")


@mcp.tool(
    name="ecofleet_set_on_duty",
    annotations={"title": "Set Driver On Duty", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_set_on_duty(params: DutyInput) -> str:
    """Mark a driver as on duty (working shift started) in EcoFleet.

    Posts to POST /Api/OnDuty/setOnDuty.

    Args:
        params: driver_id

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/OnDuty/setOnDuty", {"driverId": params.driver_id})
        return f"Driver {params.driver_id} marked as ON DUTY.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


@mcp.tool(
    name="ecofleet_set_off_duty",
    annotations={"title": "Set Driver Off Duty", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_set_off_duty(params: DutyInput) -> str:
    """Mark a driver as off duty (working shift ended) in EcoFleet.

    Posts to POST /Api/OnDuty/setOffDuty.

    Args:
        params: driver_id

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/OnDuty/setOffDuty", {"driverId": params.driver_id})
        return f"Driver {params.driver_id} marked as OFF DUTY.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# PLACES
# ═══════════════════════════════════════════════════════════

class ListPlacesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_list_places",
    annotations={"title": "List EcoFleet Organization Places", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_places(params: ListPlacesInput) -> str:
    """List all places (zones, points of interest) in the EcoFleet organization.

    Fetches from GET /Api/Places/get.
    Returns place ID, name, coordinates, and type.

    Returns:
        str: List of places with location info.
    """
    try:
        data = await _get("/Api/Places/get")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No places found."
        lines = ["## EcoFleet Places", ""]
        for p in items:
            pid = p.get("id", "")
            name = p.get("name") or p.get("title", "")
            ptype = p.get("type", "")
            lines.append(f"- **{pid}** — {name}" + (f" ({ptype})" if ptype else ""))
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# EXPENSES
# ═══════════════════════════════════════════════════════════

class ListExpensesInput(PaginationMixin):
    date_from: Optional[str] = Field(default=None, description="Filter from date YYYY-MM-DD")
    date_to: Optional[str] = Field(default=None, description="Filter to date YYYY-MM-DD")
    object_id: Optional[str] = Field(default=None, description="Vehicle ID to filter expenses")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_list_expenses",
    annotations={"title": "List EcoFleet Expenses", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_expenses(params: ListExpensesInput) -> str:
    """List fuel and cost expenses from EcoFleet.

    Returns expense records with amount, vehicle, provider, and date.

    Args:
        params: date_from, date_to, object_id, limit, offset

    Returns:
        str: List of expenses with amounts and vehicle info.
    """
    try:
        p: Dict[str, Any] = {"limit": params.limit, "offset": params.offset}
        if params.date_from:
            p["from"] = params.date_from
        if params.date_to:
            p["till"] = params.date_to
        if params.object_id:
            p["objectId"] = params.object_id
        data = await _get("/Api/Expenses/get", p)
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No expenses found."
        lines = ["## EcoFleet Expenses", ""]
        for e in items:
            eid = e.get("id", "")
            vehicle = e.get("vehicleName") or e.get("objectName", "")
            amount = e.get("amount") or e.get("cost", "")
            date = e.get("date", "")
            lines.append(f"- **#{eid}** {date} | {vehicle} | {amount}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class AddExpenseInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    object_id: str = Field(..., description="Vehicle ID")
    amount: float = Field(..., description="Expense amount", gt=0)
    date: str = Field(..., description="Expense date YYYY-MM-DD")
    description: Optional[str] = Field(default=None, description="Expense description or type")
    liters: Optional[float] = Field(default=None, description="Fuel amount in liters (for fuel expenses)")


@mcp.tool(
    name="ecofleet_add_expense",
    annotations={"title": "Add EcoFleet Expense", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def ecofleet_add_expense(params: AddExpenseInput) -> str:
    """Add a new expense (fuel or cost) record in EcoFleet.

    Args:
        params: object_id, amount, date, description, liters (optional for fuel)

    Returns:
        str: Created expense ID and confirmation.
    """
    try:
        body: Dict[str, Any] = {"objectId": params.object_id, "amount": params.amount, "date": params.date}
        if params.description:
            body["description"] = params.description
        if params.liters:
            body["liters"] = params.liters
        data = await _post("/Api/Expenses/add", body)
        return f"Expense added.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class DeleteExpenseInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    expense_id: str = Field(..., description="Expense ID to delete")


@mcp.tool(
    name="ecofleet_delete_expense",
    annotations={"title": "Delete EcoFleet Expense", "readOnlyHint": False, "destructiveHint": True, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_delete_expense(params: DeleteExpenseInput) -> str:
    """Delete an expense record from EcoFleet. Irreversible.

    Args:
        params: expense_id

    Returns:
        str: Confirmation or error.
    """
    try:
        data = await _post("/Api/Expenses/remove", {"id": params.expense_id})
        return f"Expense {params.expense_id} deleted.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# ORGANIZATION
# ═══════════════════════════════════════════════════════════

class OrgInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_list_roles",
    annotations={"title": "List EcoFleet Organization Roles", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_roles(params: OrgInput) -> str:
    """List all user roles in the EcoFleet organization.

    Returns role IDs and names needed for user creation/assignment.

    Returns:
        str: List of roles.
    """
    try:
        data = await _get("/Api/Organization/getRoles")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No roles found."
        lines = ["## EcoFleet Roles", ""]
        for r in items:
            lines.append(f"- **{r.get('id', '')}** — {r.get('name') or r.get('title', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


@mcp.tool(
    name="ecofleet_list_departments",
    annotations={"title": "List EcoFleet Departments", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_list_departments(params: OrgInput) -> str:
    """List all departments in the EcoFleet organization.

    Returns department IDs and names.

    Returns:
        str: List of departments.
    """
    try:
        data = await _get("/Api/Organization/getDepartments")
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No departments found."
        lines = ["## EcoFleet Departments", ""]
        for d in items:
            lines.append(f"- **{d.get('id', '')}** — {d.get('name') or d.get('title', '')}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


class GetActionLogInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    date_from: str = Field(..., description="Start date YYYY-MM-DD")
    date_to: str = Field(..., description="End date YYYY-MM-DD")
    response_format: ResponseFormat = Field(default=ResponseFormat.MARKDOWN)


@mcp.tool(
    name="ecofleet_get_action_log",
    annotations={"title": "Get EcoFleet Action Log", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_action_log(params: GetActionLogInput) -> str:
    """Get the organization action log from EcoFleet (audit trail of user actions).

    Returns timestamped records of actions performed by users.

    Args:
        params: date_from, date_to

    Returns:
        str: Action log entries with timestamps, users, and action types.
    """
    try:
        data = await _get("/Api/Organization/getActionLog", {"from": params.date_from, "till": params.date_to})
        if params.response_format == ResponseFormat.JSON:
            return _fmt(data)
        items = data if isinstance(data, list) else data.get("data", [])
        if not items:
            return "No action log entries found."
        lines = [f"## Action Log: {params.date_from} – {params.date_to}", ""]
        for a in items:
            ts = a.get("timestamp") or a.get("time", "")
            user = a.get("userName") or a.get("user", "")
            action = a.get("action") or a.get("type", "")
            lines.append(f"- {ts} | {user} | {action}")
        return "\n".join(lines)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# MESSAGES (Garmin)
# ═══════════════════════════════════════════════════════════

class SendTextMessageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    device_id: str = Field(..., description="Garmin device ID or vehicle ID")
    message: str = Field(..., description="Text message to send to the driver", min_length=1, max_length=500)


@mcp.tool(
    name="ecofleet_send_text_message",
    annotations={"title": "Send Garmin Text Message to Driver", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def ecofleet_send_text_message(params: SendTextMessageInput) -> str:
    """Send a text message to a driver via Garmin device in EcoFleet.

    Posts to POST /Api/Messages/Garmin/sendTextMessage.

    Args:
        params: device_id, message (max 500 chars)

    Returns:
        str: Message ID and delivery status.
    """
    try:
        data = await _post("/Api/Messages/Garmin/sendTextMessage", {
            "deviceId": params.device_id,
            "message": params.message,
        })
        return f"Message sent to device {params.device_id}.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class SendStopMessageInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    device_id: str = Field(..., description="Garmin device ID or vehicle ID")
    address: str = Field(..., description="Destination address for the stop")
    lat: Optional[float] = Field(default=None, description="Destination latitude")
    lng: Optional[float] = Field(default=None, description="Destination longitude")
    message: Optional[str] = Field(default=None, description="Optional message text for the stop")


@mcp.tool(
    name="ecofleet_send_stop_message",
    annotations={"title": "Send Garmin Stop/Waypoint to Driver", "readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True},
)
async def ecofleet_send_stop_message(params: SendStopMessageInput) -> str:
    """Send a stop/waypoint message to a driver's Garmin device in EcoFleet.

    Posts to POST /Api/Messages/Garmin/sendStopMessage.
    The driver receives a navigation point on their device.

    Args:
        params: device_id, address, lat (optional), lng (optional), message (optional)

    Returns:
        str: Message ID and delivery status.
    """
    try:
        body: Dict[str, Any] = {"deviceId": params.device_id, "address": params.address}
        if params.lat is not None:
            body["lat"] = params.lat
        if params.lng is not None:
            body["lng"] = params.lng
        if params.message:
            body["message"] = params.message
        data = await _post("/Api/Messages/Garmin/sendStopMessage", body)
        return f"Stop message sent to device {params.device_id}.\n{_fmt(data)}"
    except Exception as e:
        return _error(e)


class GetMessageStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    message_id: str = Field(..., description="Message ID returned by send_text_message or send_stop_message")


@mcp.tool(
    name="ecofleet_get_message_status",
    annotations={"title": "Get Garmin Message Delivery Status", "readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True},
)
async def ecofleet_get_message_status(params: GetMessageStatusInput) -> str:
    """Check the delivery status of a Garmin message sent via EcoFleet.

    Fetches from GET /Api/Messages/Garmin/getMessageStatus.

    Args:
        params: message_id

    Returns:
        str: Message delivery status (sent, delivered, read, failed).
    """
    try:
        data = await _get("/Api/Messages/Garmin/getMessageStatus", {"messageId": params.message_id})
        return _fmt(data)
    except Exception as e:
        return _error(e)


# ═══════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════

if __name__ == "__main__":
    mcp.run()
