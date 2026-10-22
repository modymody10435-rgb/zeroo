from __future__ import annotations

import csv
import io
import sqlite3
from contextlib import asynccontextmanager
from typing import Any, Callable

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server import config, database, security, services


class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str
    password: str
    role: str = "user"


class PasswordIn(BaseModel):
    new_password: str


class RoleIn(BaseModel):
    role: str


@asynccontextmanager
async def lifespan(_: FastAPI):
    database.init_db()
    yield


app = FastAPI(
    title=config.APP_TITLE,
    version=config.APP_VERSION,
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
    openapi_url="/api/openapi.json",
)

if config.TRUSTED_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.TRUSTED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-Requested-With"],
    )


@app.middleware("http")
async def security_middleware(request: Request, call_next: Callable):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        if request.url.path.startswith("/api/"):
            if request.headers.get("x-requested-with") != "XMLHttpRequest":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "طلب غير مصرح به."},
                )
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


def get_conn():
    with database.get_db() as conn:
        yield conn


def current_user(
    request: Request, conn: sqlite3.Connection = Depends(get_conn)
) -> dict[str, Any]:
    token = request.cookies.get(config.COOKIE_NAME, "")
    user = security.session_user(conn, token)
    if user is None:
        raise HTTPException(status_code=401, detail="الجلسة منتهية. سجّل الدخول مجدداً.")
    return user


def admin_user(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="هذه العملية تتطلب صلاحية مدير.")
    return user


def run(func: Callable, *args: Any, **kwargs: Any) -> Any:
    try:
        return func(*args, **kwargs)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": config.APP_TITLE, "version": config.APP_VERSION}


@app.get("/api/meta")
def meta() -> dict[str, Any]:
    payload = services.meta_payload()
    payload["app_title"] = config.APP_TITLE
    payload["version"] = config.APP_VERSION
    return payload


@app.post("/api/auth/login")
def login(
    payload: LoginIn,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    user = security.find_user(conn, payload.username)
    if user is None or not security.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="اسم المستخدم أو كلمة المرور غير صحيحة.")
    with conn:
        token = security.create_session(conn, int(user["id"]))
    response.set_cookie(
        key=config.COOKIE_NAME,
        value=token,
        max_age=config.SESSION_DAYS * 24 * 3600,
        httponly=True,
        secure=config.COOKIE_SECURE,
        samesite=config.COOKIE_SAMESITE,
        path="/",
    )
    return {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "created_at": user["created_at"],
    }


@app.post("/api/auth/logout")
def logout(
    request: Request,
    response: Response,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    token = request.cookies.get(config.COOKIE_NAME, "")
    if token:
        with conn:
            security.delete_session(conn, token)
    response.delete_cookie(config.COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
    return user


@app.get("/api/dashboard")
def dashboard(
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return services.dashboard_metrics(conn)


@app.get("/api/products")
def products(
    category: str = "",
    search: str = "",
    low: bool = False,
    decommissioned: bool | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    items = services.list_products(
        conn,
        category=category,
        search=search,
        low_only=low,
        decommissioned=decommissioned,
    )
    return {"items": items, "count": len(items)}


@app.get("/api/products/{code}")
def product_detail(
    code: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    item = services.get_product(conn, code)
    if item is None:
        raise HTTPException(status_code=404, detail="الصنف غير موجود.")
    return item


@app.post("/api/products")
def create_product(
    payload: dict[str, Any] = Body(...),
    conn: sqlite3.Connection = Depends(get_conn),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.create_product, conn, payload, user["username"])


@app.put("/api/products/{code}")
def update_product(
    code: str,
    payload: dict[str, Any] = Body(...),
    conn: sqlite3.Connection = Depends(get_conn),
    user: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.update_product, conn, code, payload, user["username"])


@app.delete("/api/products/{code}")
def delete_product(
    code: str,
    force: bool = True,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.delete_product, conn, code, force)


@app.post("/api/products/{code}/decommission")
def decommission_product(
    code: str,
    payload: dict[str, Any] = Body(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(
        services.decommission_device,
        conn,
        payload.get("source", ""),
        code,
        payload.get("decommission_date", ""),
        payload.get("reason", ""),
        payload.get("person", ""),
    )


@app.get("/api/decommissioned")
def decommissioned(
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    items = services.list_decommissioned(conn)
    return {"items": items, "count": len(items)}


@app.get("/api/products/{code}/pending")
def pending_product(
    code: str,
    current_order_no: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return {
        "items": services.pending_for_product(conn, code, current_order_no)
    }


@app.post("/api/withdrawals")
def create_withdrawal(
    payload: dict[str, Any] = Body(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(
        services.withdraw_product,
        conn,
        product_code=payload.get("product_code", ""),
        product_name=payload.get("product_name", ""),
        qty=services.number(payload.get("qty")),
        person=payload.get("person", ""),
        withdraw_date=payload.get("withdraw_date", ""),
        supervisor=payload.get("supervisor", ""),
        notes=payload.get("notes", ""),
        order_no=payload.get("order_no", ""),
        item_id=payload.get("item_id", ""),
    )


@app.get("/api/withdrawals")
def withdrawals(
    category: str = "",
    search: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 500,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    items = services.list_withdrawals(
        conn,
        category=category,
        search=search,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    return {"items": items, "count": len(items)}


@app.delete("/api/withdrawals/{withdrawal_id}")
def delete_withdrawal(
    withdrawal_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.delete_withdrawal, conn, withdrawal_id)


@app.get("/api/orders")
def orders(
    status: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    items = services.list_orders(conn, status=status)
    return {"items": items, "count": len(items)}


@app.post("/api/orders")
def create_order(
    payload: dict[str, Any] = Body(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(
        services.create_order,
        conn,
        payload.get("order_date", ""),
        payload.get("factory_name", ""),
        payload.get("responsible_person", ""),
        payload.get("notes", ""),
    )


@app.get("/api/orders/{order_no}")
def order_detail(
    order_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    order = services.get_order(conn, order_no)
    if order is None:
        raise HTTPException(status_code=404, detail="الطلبية غير موجودة.")
    return order


@app.post("/api/orders/{order_no}/items")
def add_order_item(
    order_no: str,
    payload: dict[str, Any] = Body(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(
        services.add_order_item,
        conn,
        order_no,
        payload.get("product_code", ""),
        payload.get("product_name", ""),
        services.number(payload.get("required_qty")),
        payload.get("unit", ""),
    )


@app.delete("/api/orders/{order_no}/items/{item_id}")
def remove_order_item(
    order_no: str,
    item_id: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.remove_order_item, conn, order_no, item_id)


@app.post("/api/orders/{order_no}/complete")
def complete_order(
    order_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.set_order_status, conn, order_no, services.ORDER_STATUS_COMPLETED)


@app.post("/api/orders/{order_no}/reopen")
def reopen_order(
    order_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.set_order_status, conn, order_no, services.ORDER_STATUS_OPEN)


@app.delete("/api/orders/{order_no}")
def delete_order(
    order_no: str,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.delete_order, conn, order_no)


@app.get("/api/authority")
def authority(
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return services.authority_snapshot(conn)


@app.post("/api/authority/receipts")
def authority_receipt(
    payload: dict[str, Any] = Body(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(
        services.receive_authority,
        conn,
        item_name=payload.get("item_name", ""),
        item_code=payload.get("item_code", ""),
        qty=services.number(payload.get("qty")),
        receipt_date=payload.get("receipt_date", ""),
        receiver=payload.get("receiver", ""),
        notes=payload.get("notes", ""),
    )


@app.post("/api/authority/withdrawals")
def authority_withdrawal(
    payload: dict[str, Any] = Body(...),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(
        services.withdraw_authority,
        conn,
        item_name=payload.get("item_name", ""),
        item_code=payload.get("item_code", ""),
        qty=services.number(payload.get("qty")),
        username=payload.get("username", ""),
        withdrawal_date=payload.get("withdrawal_date", ""),
        notes=payload.get("notes", ""),
    )


@app.delete("/api/authority/items")
def authority_delete_item(
    item_name: str = Query(...),
    item_code: str = Query(""),
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return run(services.delete_authority_item, conn, item_name, item_code)


@app.get("/api/reports/summary")
def reports_summary(
    date_from: str = "",
    date_to: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    return services.report_summary(conn, date_from, date_to)


@app.get("/api/reports/movements")
def reports_movements(
    date_from: str = "",
    date_to: str = "",
    category: str = "",
    search: str = "",
    movement_type: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    items = services.report_movements(
        conn,
        date_from=date_from,
        date_to=date_to,
        category=category,
        search=search,
        movement_type=movement_type,
    )
    return {"items": items, "count": len(items)}


@app.get("/api/reports/withdrawals")
def reports_withdrawals(
    date_from: str = "",
    date_to: str = "",
    category: str = "",
    search: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    items = services.report_withdrawals(
        conn,
        date_from=date_from,
        date_to=date_to,
        category=category,
        search=search,
    )
    return {"items": items, "count": len(items)}


@app.get("/api/reports/low-stock")
def reports_low_stock(
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> dict[str, Any]:
    items = services.list_products(conn, low_only=True)
    return {"items": items, "count": len(items)}


def _csv_response(filename: str, headers: list[str], rows: list[list[Any]]) -> StreamingResponse:
    buffer = io.StringIO()
    buffer.write("\ufeff")
    writer = csv.writer(buffer)
    writer.writerow(headers)
    writer.writerows(rows)
    data = buffer.getvalue().encode("utf-8")
    return StreamingResponse(
        iter([data]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/reports/export.csv")
def export_csv(
    kind: str = "movements",
    date_from: str = "",
    date_to: str = "",
    category: str = "",
    search: str = "",
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(current_user),
) -> StreamingResponse:
    if kind == "withdrawals":
        items = services.report_withdrawals(
            conn, date_from=date_from, date_to=date_to, category=category, search=search
        )
        return _csv_response(
            "withdrawals.csv",
            ["معرف السحب", "التاريخ", "الكود", "الصنف", "التصنيف", "الكمية", "الساحب", "المسؤول", "ملاحظات"],
            [
                [
                    item.get("withdrawal_id", ""),
                    item.get("withdraw_date", ""),
                    item.get("product_code", ""),
                    item.get("product_name", ""),
                    item.get("category", ""),
                    item.get("qty", 0),
                    item.get("withdrawn_by", ""),
                    item.get("supervisor_name", ""),
                    item.get("notes", ""),
                ]
                for item in items
            ],
        )
    if kind == "low-stock":
        items = services.list_products(conn, low_only=True)
        return _csv_response(
            "low_stock.csv",
            ["الكود", "الصنف", "التصنيف", "الرصيد", "الحد الأدنى", "الوحدة", "الموقع"],
            [
                [
                    item.get("product_code", ""),
                    item.get("product_name", ""),
                    item.get("category", ""),
                    item.get("current_stock", 0),
                    item.get("min_stock", 0),
                    item.get("unit", ""),
                    item.get("storage_location", ""),
                ]
                for item in items
            ],
        )
    items = services.report_movements(
        conn,
        date_from=date_from,
        date_to=date_to,
        category=category,
        search=search,
    )
    return _csv_response(
        "movements.csv",
        ["رقم الحركة", "التاريخ", "النوع", "الكود", "الصنف", "التصنيف", "الكمية", "الرصيد", "الشخص", "ملاحظات"],
        [
            [
                item.get("movement_no", ""),
                item.get("movement_date", ""),
                item.get("movement_type", ""),
                item.get("product_code", ""),
                item.get("product_name", ""),
                item.get("category", ""),
                item.get("qty", 0),
                item.get("balance_after", 0),
                item.get("person", ""),
                item.get("notes", ""),
            ]
            for item in items
        ],
    )


@app.get("/api/users")
def users(
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    items = services.list_users(conn)
    return {"items": items, "count": len(items)}


@app.post("/api/users")
def create_user(
    payload: UserIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    return run(services.add_user, conn, payload.username, payload.password, payload.role)


@app.delete("/api/users/{username}")
def remove_user(
    username: str,
    conn: sqlite3.Connection = Depends(get_conn),
    user: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    return run(services.delete_user, conn, username, user["username"])


@app.post("/api/users/{username}/password")
def change_password(
    username: str,
    payload: PasswordIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    return run(services.reset_password, conn, username, payload.new_password)


@app.put("/api/users/{username}/role")
def change_role(
    username: str,
    payload: RoleIn,
    conn: sqlite3.Connection = Depends(get_conn),
    _: dict[str, Any] = Depends(admin_user),
) -> dict[str, Any]:
    return run(services.set_user_role, conn, username, payload.role)


if config.FRONTEND_DIR.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(config.FRONTEND_DIR / "assets")),
        name="assets",
    )


@app.get("/")
def index() -> FileResponse:
    target = config.FRONTEND_DIR / "index.html"
    if not target.is_file():
        raise HTTPException(status_code=503, detail="واجهة التطبيق غير مثبتة.")
    return FileResponse(target)


@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="المسار غير موجود.")
    target = config.FRONTEND_DIR / "index.html"
    if not target.is_file():
        raise HTTPException(status_code=503, detail="واجهة التطبيق غير مثبتة.")
    return FileResponse(target)
