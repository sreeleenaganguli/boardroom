import csv
import hashlib
import io
import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import close_db, get_db, init_db
from app.models import (
    AIModel, AIProvider, AnalyticsRun, AuditLog, ChatMessage, Conversation,
    Dataset, Organization, Permission, QualityReport, Report, Role,
    RolePermission, SchemaApproval, SemanticModel, UsageLedger, User, UserRole, Workspace,
)
from app.security.auth import (
    create_access_token, create_refresh_token, get_current_user,
    get_password_hash, verify_password,
)
from app.security.permissions import get_user_permissions
from app.security.sql_sandbox import SQLSandboxError, add_limit, validate_sql
from app.utils.duckdb_manager import get_duckdb


app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    organization_name: str = "Default Organization"


class QueryRequest(BaseModel):
    workspace_id: str
    dataset_id: str
    question: str
    model_id: Optional[str] = None
    conversation_id: Optional[str] = None


class SQLRequest(BaseModel):
    workspace_id: str
    dataset_id: str
    sql: str


class ReportRequest(BaseModel):
    workspace_id: str
    title: str
    description: Optional[str] = None
    content: dict[str, Any]


class GenerateReportRequest(BaseModel):
    conversation_id: str
    message_id: str
    model_id: str
    title: Optional[str] = None


class RoleAssignmentRequest(BaseModel):
    role_id: str


class BudgetRequest(BaseModel):
    workspace_id: str
    monthly_limit: float
    alert_threshold: float = 0.8


class ScenarioRequest(BaseModel):
    dataset_id: str
    metric_key: str
    change_percent: float


class SchemaApprovalRequest(BaseModel):
    columns: list[dict[str, Any]]
    primary_date_column: str | None = None
    domain: str | None = None


async def audit(db: AsyncSession, user: User, action: str, resource_type: str,
                resource_id: str | None = None, details: dict | None = None):
    db.add(AuditLog(user_id=user.id, action=action, resource_type=resource_type,
                    resource_id=resource_id, details=details or {}))
    await db.flush()


@app.on_event("startup")
async def startup():
    await init_db()
    await seed_platform()
    await rehydrate_datasets()


@app.on_event("shutdown")
async def shutdown():
    get_duckdb().close()
    await close_db()


async def seed_platform():
    async for db in get_db():
        organization = (await db.execute(select(Organization).limit(1))).scalar_one_or_none()
        if organization is None:
            organization = Organization(name="Default Organization", slug="default")
            db.add(organization)
            await db.flush()

        if not (await db.execute(select(User).limit(1))).scalar_one_or_none():
            admin = User(
                email="admin@boardroom.local",
                hashed_password=get_password_hash("admin123"),
                full_name="Platform Administrator",
                is_superuser=True,
                organization_id=organization.id,
            )
            db.add(admin)
            await db.flush()
            workspace = Workspace(name="Executive Workspace", slug="executive",
                                  organization_id=organization.id)
            db.add(workspace)
            await db.flush()

        permissions = [
            ("dataset", "upload"), ("dataset", "view"), ("dataset", "delete"),
            ("dataset", "share"), ("dataset", "transform"), ("dataset", "export"),
            ("schema", "view"), ("schema", "edit"), ("schema", "confirm"),
            ("analytics", "query"), ("analytics", "advanced"), ("analytics", "export"),
            ("insights", "view"), ("insights", "generate"),
            ("report", "create"), ("report", "view"), ("report", "edit"),
            ("report", "export"), ("report", "share"),
            ("model", "view"), ("model", "select"), ("model", "configure"),
            ("finops", "view"), ("finops", "configure"),
            ("admin", "users"), ("admin", "roles"), ("admin", "audit"),
        ]
        existing = set(
            f"{p.resource}:{p.action}"
            for p in (await db.execute(select(Permission))).scalars().all()
        )
        for resource, action in permissions:
            key = f"{resource}:{action}"
            if key not in existing:
                db.add(Permission(resource=resource, action=action,
                                  description=f"{action} {resource} resources"))

        for provider_name, display_name in [
            ("openai", "OpenAI"), ("anthropic", "Anthropic"),
            ("google", "Google"), ("local", "Local"),
        ]:
            if not (await db.execute(select(AIProvider).where(AIProvider.name == provider_name))).scalar_one_or_none():
                db.add(AIProvider(name=provider_name, display_name=display_name,
                                  requires_api_key=provider_name != "local"))

        role_names = [
            ("Super Administrator", "Full platform access"),
            ("Administrator", "Organization administration"),
            ("Data Engineer", "Data ingestion and transformation"),
            ("Data Analyst", "Advanced analytics and reporting"),
            ("Business Analyst", "Permitted dataset analytics"),
            ("Executive / Viewer", "Read approved reports and dashboards"),
            ("FinOps Manager", "Cost and budget management"),
        ]
        for name, description in role_names:
            if not (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none():
                db.add(Role(name=name, description=description, is_system_role=True))
        await db.flush()

        role_grants = {
            "Administrator": [
                "dataset:upload", "dataset:view", "dataset:delete", "dataset:share",
                "dataset:transform", "schema:view", "schema:edit", "schema:confirm",
                "analytics:query", "analytics:advanced", "analytics:export",
                "insights:view", "insights:generate", "report:create", "report:view",
                "report:edit", "report:export", "report:share", "model:view",
                "model:select", "model:configure", "finops:view", "finops:configure",
                "admin:users", "admin:roles", "admin:audit",
            ],
            "Data Engineer": [
                "dataset:upload", "dataset:view", "dataset:transform", "dataset:export",
                "schema:view", "schema:edit", "schema:confirm",
            ],
            "Data Analyst": [
                "dataset:view", "schema:view", "analytics:query", "analytics:advanced",
                "analytics:export", "insights:view", "insights:generate", "report:create",
                "report:view", "report:edit", "report:export", "model:view", "model:select",
            ],
            "Business Analyst": [
                "dataset:view", "schema:view", "analytics:query", "insights:view", "report:view",
            ],
            "Executive / Viewer": ["dataset:view", "insights:view", "report:view"],
            "FinOps Manager": ["finops:view", "finops:configure"],
        }
        permission_rows = (await db.execute(select(Permission))).scalars().all()
        permissions_by_key = {f"{item.resource}:{item.action}": item for item in permission_rows}
        roles_by_name = {
            role.name: role
            for role in (await db.execute(select(Role))).scalars().all()
        }
        current_grants = {
            (grant.role_id, grant.permission_id)
            for grant in (await db.execute(select(RolePermission))).scalars().all()
        }
        for role_name, grants in role_grants.items():
            role = roles_by_name.get(role_name)
            if not role:
                continue
            for grant_key in grants:
                permission = permissions_by_key.get(grant_key)
                if permission and (role.id, permission.id) not in current_grants:
                    db.add(RolePermission(role_id=role.id, permission_id=permission.id))

        for provider_name, display_name, model_name, model_display, context, input_price, output_price in [
            ("openai", "OpenAI", "gpt-4-turbo-preview", "GPT-4 Turbo", 128000, 0.01, 0.03),
            ("openai", "OpenAI", "gpt-4o-mini", "GPT-4o Mini", 128000, 0.00015, 0.0006),
            ("anthropic", "Anthropic", "claude-3-5-sonnet", "Claude 3.5 Sonnet", 200000, 0.003, 0.015),
            ("google", "Google", "gemini-1.5-pro", "Gemini 1.5 Pro", 2000000, 0.0035, 0.0105),
            ("local", "Local", "llama-3", "Llama 3 Local", 8192, 0.0, 0.0),
        ]:
            provider = (await db.execute(select(AIProvider).where(AIProvider.name == provider_name))).scalar_one_or_none()
            if provider and not (await db.execute(select(AIModel).where(AIModel.name == model_name))).scalar_one_or_none():
                db.add(AIModel(provider_id=provider.id, name=model_name, display_name=model_display,
                               model_type="chat", context_window=context,
                               input_price_per_1k=input_price, output_price_per_1k=output_price,
                               is_active=True, capabilities={"chat": True, "analytics": True}))
        await db.commit()
        break


@app.get("/api/v1/health")
async def health(db: AsyncSession = Depends(get_db)):
    await db.execute(select(User).limit(1))
    return {"status": "healthy", "database": "connected", "version": settings.APP_VERSION}


@app.post("/api/v1/auth/register")
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(User).where(User.email == payload.email.lower()))).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    slug = payload.organization_name.lower().strip().replace(" ", "-")
    org = Organization(name=payload.organization_name, slug=f"{slug}-{uuid.uuid4().hex[:6]}")
    db.add(org)
    await db.flush()
    user = User(email=payload.email.lower(), hashed_password=get_password_hash(payload.password),
                full_name=payload.full_name, organization_id=org.id)
    db.add(user)
    await db.flush()
    workspace = Workspace(name="My Workspace", slug="my-workspace", organization_id=org.id)
    db.add(workspace)
    analyst_role = (await db.execute(
        select(Role).where(Role.name == "Business Analyst")
    )).scalar_one_or_none()
    if analyst_role:
        db.add(UserRole(user_id=user.id, role_id=analyst_role.id))
    await db.commit()
    return {"access_token": create_access_token({"sub": user.id}),
            "refresh_token": create_refresh_token({"sub": user.id}),
            "token_type": "bearer", "user": {"id": user.id, "email": user.email,
                                             "full_name": user.full_name}}


@app.post("/api/v1/auth/login")
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = (await db.execute(select(User).where(User.email == payload.email.lower()))).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    user.last_login = datetime.now(timezone.utc)
    await db.commit()
    return {"access_token": create_access_token({"sub": user.id}),
            "refresh_token": create_refresh_token({"sub": user.id}),
            "token_type": "bearer", "user": {"id": user.id, "email": user.email,
                                             "full_name": user.full_name,
                                             "is_superuser": user.is_superuser}}


@app.get("/api/v1/auth/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    permissions = await get_user_permissions(user, db)
    return {"id": user.id, "email": user.email, "full_name": user.full_name,
            "is_superuser": user.is_superuser, "organization_id": user.organization_id,
            "permissions": permissions}


@app.get("/api/v1/workspaces")
async def workspaces(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workspace).where(
        Workspace.organization_id == user.organization_id
    ))
    return [{"id": w.id, "name": w.name, "slug": w.slug} for w in result.scalars().all()]


def safe_table_name(dataset_id: str) -> str:
    return f"dataset_{dataset_id.replace('-', '_')}"


async def get_authorized_dataset(
    dataset_id: str,
    user: User,
    db: AsyncSession,
    require_write: bool = False,
) -> Dataset:
    dataset = (await db.execute(select(Dataset).where(Dataset.id == dataset_id))).scalar_one_or_none()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    workspace = (await db.execute(select(Workspace).where(Workspace.id == dataset.workspace_id))).scalar_one_or_none()
    if not workspace or workspace.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Dataset is outside your organization")
    if require_write and not user.is_superuser:
        permissions = await get_user_permissions(user, db)
        if "dataset:transform" not in permissions:
            raise HTTPException(status_code=403, detail="Permission denied: dataset:transform")
    return dataset


async def rehydrate_datasets():
    """Restore analytical tables from authorized uploaded files after an API restart."""
    async for db in get_db():
        datasets = (await db.execute(select(Dataset).where(Dataset.status == "ready"))).scalars().all()
        for dataset in datasets:
            source = Path(dataset.file_path)
            if not source.exists():
                continue
            try:
                table = safe_table_name(dataset.id)
                if dataset.file_type == "csv":
                    profile_csv(source, table)
                elif dataset.file_type in {"sqlite", "sqlite3", "db"}:
                    profile_sqlite(source, table)
            except Exception as exc:
                # The dataset remains visible; analytical endpoints will surface a clear unavailable state.
                print(f"Dataset rehydration failed for {dataset.id}: {exc}")
                continue


def executive_metric_columns(columns: list[SemanticModel]) -> dict[str, str]:
    """Map only semantically plausible business measures; calculations remain deterministic."""
    measures = {c.column_name.lower(): c.column_name for c in columns if c.semantic_type == "measure"}
    def match(*tokens: str) -> str | None:
        for low, actual in measures.items():
            if any(token in low for token in tokens):
                return actual
        return None
    return {
        "revenue": match("revenue", "sales", "net_sales", "amount", "mrr"),
        "profit": match("profit", "margin_amount", "net_income"),
        "cost": match("cost", "expense", "spend"),
        "returns": match("return", "refund"),
    }


def detect_business_domain(columns: list[SemanticModel]) -> str:
    names = " ".join(c.column_name.lower() for c in columns)
    if any(word in names for word in ("subscription", "mrr", "arr", "plan", "churn")):
        return "SaaS subscriptions"
    if any(word in names for word in ("order", "product", "return", "shipping", "discount")):
        return "E-commerce"
    if any(word in names for word in ("expense", "profit", "budget", "variance")):
        return "Financial performance"
    if any(word in names for word in ("processing", "throughput", "duration", "efficiency")):
        return "Operational performance"
    return "General business analytics"


def _number(value: Any) -> float | None:
    try:
        value = float(value)
        return value if value == value and value not in (float("inf"), float("-inf")) else None
    except (TypeError, ValueError):
        return None


def build_executive_analysis(frame, columns: list[SemanticModel], dataset: Dataset, quality: QualityReport | None) -> dict[str, Any]:
    """Build a traceable report from the loaded table without an LLM or arbitrary scoring."""
    import pandas as pd
    metrics = executive_metric_columns(columns)
    domain = detect_business_domain(columns)
    date_column = next((c.column_name for c in columns if c.semantic_type == "datetime"), None)
    categories = [c.column_name for c in columns if c.semantic_type == "category" and c.unique_count and c.unique_count <= 40]
    numeric = [c.column_name for c in columns if c.semantic_type == "measure" and c.column_name in frame.columns]
    kpis: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    trends: list[dict[str, Any]] = []
    revenue_col = metrics.get("revenue")
    if revenue_col and revenue_col in frame:
        values = pd.to_numeric(frame[revenue_col], errors="coerce")
        total = float(values.sum(skipna=True))
        kpis.append({"key": "revenue", "label": "Total Revenue", "value": total, "unit": "currency", "calculation": f"SUM({revenue_col})", "interpretation": "Verified sum of available revenue records."})
        evidence.append({"title": "Revenue base", "type": "VERIFIED FACT", "finding": f"Total {revenue_col} is {total:,.2f}.", "metric": total, "calculation": f"SELECT SUM({quote_identifier(revenue_col)}) FROM {quote_identifier(safe_table_name(dataset.id))}", "severity": "informational"})
    if metrics.get("profit") in frame:
        col = metrics["profit"]; value = float(pd.to_numeric(frame[col], errors="coerce").sum(skipna=True))
        kpis.append({"key": "profit", "label": "Total Profit", "value": value, "unit": "currency", "calculation": f"SUM({col})", "interpretation": "Verified sum of available profit records."})
        if revenue_col:
            revenue = next((x["value"] for x in kpis if x["key"] == "revenue"), 0)
            if revenue:
                kpis.append({"key": "margin", "label": "Profit Margin", "value": value / revenue * 100, "unit": "percent", "calculation": f"SUM({col}) / SUM({revenue_col})", "interpretation": "Profit divided by revenue; not a target comparison."})
    order_col = next((c.column_name for c in columns if "order" in c.column_name.lower() and c.semantic_type in {"identifier", "category"}), None)
    customer_col = next((c.column_name for c in columns if any(x in c.column_name.lower() for x in ("customer", "client", "account")) and c.semantic_type in {"identifier", "category"}), None)
    for key, label, column in (("orders", "Orders", order_col), ("customers", "Customers", customer_col)):
        if column and column in frame:
            value = int(frame[column].nunique(dropna=True))
            kpis.append({"key": key, "label": label, "value": value, "unit": "count", "calculation": f"COUNT(DISTINCT {column})", "interpretation": "Verified distinct non-null identifiers."})
    if revenue_col and order_col:
        orders = next((x["value"] for x in kpis if x["key"] == "orders"), 0)
        if orders:
            kpis.append({"key": "aov", "label": "Average Order Value", "value": next(x["value"] for x in kpis if x["key"] == "revenue") / orders, "unit": "currency", "calculation": f"SUM({revenue_col}) / COUNT(DISTINCT {order_col})", "interpretation": "Revenue per distinct order."})
    if metrics.get("returns") in frame and order_col:
        returned = pd.to_numeric(frame[metrics["returns"]], errors="coerce").fillna(0).gt(0).sum()
        orders = next((x["value"] for x in kpis if x["key"] == "orders"), 0)
        if orders:
            kpis.append({"key": "return_rate", "label": "Return Rate", "value": returned / orders * 100, "unit": "percent", "calculation": f"COUNT({metrics['returns']} > 0) / COUNT(DISTINCT {order_col})", "interpretation": "Share of distinct orders with a positive return value."})
    if date_column and revenue_col:
        parsed = pd.to_datetime(frame[date_column], errors="coerce", utc=True)
        valid = frame.loc[parsed.notna()].copy(); valid["__period"] = parsed[parsed.notna()].dt.to_period("M").astype(str)
        valid["__metric"] = pd.to_numeric(valid[revenue_col], errors="coerce")
        monthly = valid.groupby("__period", as_index=False)["__metric"].sum().sort_values("__period")
        trends = [
            {"period": str(period), "value": float(value)}
            for period, value in zip(monthly["__period"], monthly["__metric"])
        ]
        if len(monthly) >= 2:
            current, previous = float(monthly.iloc[-1]["__metric"]), float(monthly.iloc[-2]["__metric"])
            change = current - previous; pct = change / abs(previous) * 100 if previous else None
            kpis[0].update({"previous_value": previous, "change": change, "change_percent": pct})
            severity = "high" if pct is not None and pct < -10 else "informational"
            evidence.append({"title": "Latest period change", "type": "VERIFIED FACT", "finding": f"{monthly.iloc[-1]['__period']} revenue changed {pct:+.1f}% versus {monthly.iloc[-2]['__period']} ({change:+,.2f})." if pct is not None else "Previous period was zero; percentage change is unavailable.", "metric": change, "calculation": f"Monthly SUM({revenue_col}); latest minus prior month", "severity": severity})
            if categories:
                segment = categories[0]
                valid["__segment"] = valid[segment].fillna("Unknown").astype(str)
                pivot = valid.groupby(["__period", "__segment"])["__metric"].sum().unstack(fill_value=0)
                if len(pivot.index) >= 2:
                    drivers = (pivot.iloc[-1] - pivot.iloc[-2]).sort_values(key=lambda s: s.abs(), ascending=False).head(5)
                    total = float(drivers.sum())
                    evidence.append({"title": f"What changed by {segment}", "type": "VERIFIED FACT", "finding": f"Top measured contributors reconcile to {total:+,.2f} of the {change:+,.2f} period change; any difference is explicitly residual.", "metric": total, "drivers": [{"segment": str(k), "contribution": float(v)} for k, v in drivers.items()], "residual": change-total, "calculation": f"SUM({revenue_col}) by month and {segment}; current minus previous", "severity": severity})
    anomalies=[]
    for col in numeric[:6]:
        series=pd.to_numeric(frame[col], errors="coerce").dropna()
        if len(series) >= 8:
            q1,q3=series.quantile(.25),series.quantile(.75); iqr=q3-q1
            if iqr > 0:
                out=series[(series < q1-1.5*iqr) | (series > q3+1.5*iqr)]
                if len(out): anomalies.append({"column":col,"count":int(len(out)),"baseline":{"q1":float(q1),"q3":float(q3)},"method":"IQR (1.5×)","severity":"high" if len(out)/len(series)>.05 else "medium","examples":[float(v) for v in out.head(3)]})
    quality_score = quality.overall_score if quality else None
    dimensions=[]
    if revenue_col and trends and len(trends)>=2:
        latest_change = kpis[0].get("change_percent")
        if latest_change is not None: dimensions.append({"name":"Revenue performance","score":max(0,min(100,50+latest_change*2)),"basis":"Latest monthly revenue change relative to 50 baseline"})
    if any(x["key"]=="margin" for x in kpis): dimensions.append({"name":"Profitability","score":max(0,min(100,next(x["value"] for x in kpis if x["key"]=="margin"))),"basis":"Profit margin percentage"})
    if quality_score is not None: dimensions.append({"name":"Data reliability","score":quality_score,"basis":"Latest data-quality scan"})
    health_score = round(sum(x["score"] for x in dimensions)/len(dimensions),1) if dimensions else None
    alerts=[]
    for item in evidence:
        if item["severity"] == "high": alerts.append({"severity":"High","title":item["title"],"detail":item["finding"]})
    for anomaly in anomalies[:3]: alerts.append({"severity":anomaly["severity"].title(),"title":f"Unusual {anomaly['column']} values","detail":f"{anomaly['count']} IQR outlier(s); investigate before treating as a business issue."})
    if quality_score is not None and quality_score < 85: alerts.append({"severity":"Medium","title":"Data reliability needs review","detail":f"Latest data quality score is {quality_score:.1f}% and may affect interpretation."})
    brief = f"{domain} analysis covers {len(frame):,} records. " + (f"The verified revenue base is {next(x['value'] for x in kpis if x['key']=='revenue'):,.2f}. " if any(x['key']=='revenue' for x in kpis) else "No supported revenue measure was detected. ") + (evidence[1]["finding"] if len(evidence)>1 else "Review the KPI calculations and data-quality status before acting.")
    return {"dataset":{"name":dataset.name,"records":len(frame),"domain":domain,"generated_at":datetime.now(timezone.utc).isoformat(),"date_column":date_column},"kpis":kpis,"trend":trends,"evidence":evidence,"anomalies":anomalies,"alerts":alerts,"health":{"score":health_score,"dimensions":dimensions,"methodology":"Arithmetic average of applicable, disclosed dimensions; data reliability is reported separately from business performance."},"quality":{"score":quality_score,"status":"scanned" if quality else "not scanned"},"briefing":brief,"methodology":"Verified facts are calculated directly from the uploaded dataset. Statistical findings use stated methods. Interpretations are not causal claims."}


def build_deep_dive(frame, columns: list[SemanticModel], dataset: Dataset) -> dict[str, Any]:
    """Generic, reproducible descriptive analytics for the analytical workspace."""
    import pandas as pd
    numeric = [c.column_name for c in columns if c.semantic_type == "measure" and c.column_name in frame.columns]
    categories = [c.column_name for c in columns if c.semantic_type == "category" and c.column_name in frame.columns and 1 < (c.unique_count or 0) <= 30]
    metrics = executive_metric_columns(columns)
    primary = metrics.get("revenue") or (numeric[0] if numeric else None)
    statistics=[]
    for column in numeric[:10]:
        series=pd.to_numeric(frame[column],errors="coerce").dropna()
        if len(series):
            statistics.append({"column":column,"count":int(len(series)),"missing":int(len(frame)-len(series)),"mean":float(series.mean()),"median":float(series.median()),"std_dev":float(series.std()) if len(series)>1 else 0,"p25":float(series.quantile(.25)),"p75":float(series.quantile(.75)),"min":float(series.min()),"max":float(series.max())})
    segments=[]
    if primary:
        metric_series=pd.to_numeric(frame[primary],errors="coerce")
        for category in categories[:4]:
            grouped=frame.assign(__metric=metric_series).groupby(category,dropna=False)["__metric"].agg(["sum","mean","count"]).reset_index().sort_values("sum",ascending=False).head(12)
            segments.append({"dimension":category,"metric":primary,"rows":[{"segment":"Unknown" if pd.isna(row[category]) else str(row[category]),"value":float(row["sum"] or 0),"average":float(row["mean"] or 0),"records":int(row["count"])} for _,row in grouped.iterrows()]})
    correlations=[]
    if len(numeric)>=2:
        matrix=frame[numeric[:8]].apply(pd.to_numeric,errors="coerce").corr()
        for left_index,left in enumerate(matrix.columns):
            for right in matrix.columns[left_index+1:]:
                coefficient=matrix.loc[left,right]
                if pd.notna(coefficient) and abs(coefficient)>=.35: correlations.append({"left":left,"right":right,"coefficient":float(coefficient),"strength":"strong" if abs(coefficient)>=.7 else "moderate","note":"Correlation describes association only; it does not establish causation."})
        correlations.sort(key=lambda item:abs(item["coefficient"]),reverse=True)
    date_column=next((c.column_name for c in columns if c.semantic_type=="datetime"),None)
    forecast={"available":False,"reason":"A dated numeric measure with at least 12 valid monthly observations is required."}
    if date_column and primary:
        dates=pd.to_datetime(frame[date_column],errors="coerce",utc=True)
        observations=int(dates.notna().sum())
        months=int(dates[dates.notna()].dt.to_period("M").nunique()) if observations else 0
        if months>=12: forecast={"available":False,"reason":"Historical coverage is sufficient, but forecasting is intentionally not run until a validated model and holdout evaluation are selected.","observations":months,"measure":primary}
        else: forecast={"available":False,"reason":f"Only {months} valid monthly observations are available; at least 12 are required for forecast validation.","observations":months,"measure":primary}
    return {"statistics":statistics,"segments":segments,"correlations":correlations[:12],"forecast":forecast,"methodology":"Descriptive statistics use non-null numeric values. Segment values are aggregated sums. Correlations are Pearson coefficients over paired numeric values."}


@app.get("/api/v1/executive/datasets/{dataset_id}")
async def executive_dataset_analysis(dataset_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    dataset = await get_authorized_dataset(dataset_id, user, db)
    table = safe_table_name(dataset.id)
    if not get_duckdb().table_exists(table): raise HTTPException(status_code=409, detail="Dataset is not loaded in the analytics engine")
    columns = (await db.execute(select(SemanticModel).where(SemanticModel.dataset_id == dataset.id))).scalars().all()
    from sqlalchemy import desc
    quality = (await db.execute(select(QualityReport).where(QualityReport.dataset_id == dataset.id).order_by(desc(QualityReport.created_at)).limit(1))).scalar_one_or_none()
    frame = get_duckdb().query_df(f"SELECT * FROM {quote_identifier(table)}")
    return build_executive_analysis(frame, columns, dataset, quality)


@app.get("/api/v1/executive/datasets/{dataset_id}/deep-dive")
async def executive_deep_dive(dataset_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    dataset = await get_authorized_dataset(dataset_id, user, db)
    table=safe_table_name(dataset.id)
    if not get_duckdb().table_exists(table): raise HTTPException(status_code=409, detail="Dataset is not loaded in the analytics engine")
    columns=(await db.execute(select(SemanticModel).where(SemanticModel.dataset_id==dataset.id))).scalars().all()
    return build_deep_dive(get_duckdb().query_df(f"SELECT * FROM {quote_identifier(table)}"),columns,dataset)


@app.post("/api/v1/executive/scenario")
async def executive_scenario(payload: ScenarioRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    dataset = await get_authorized_dataset(payload.dataset_id, user, db)
    analysis = await executive_dataset_analysis(dataset.id, user, db)
    metric = next((item for item in analysis["kpis"] if item["key"] == payload.metric_key), None)
    if not metric: raise HTTPException(status_code=422, detail="That KPI is not available for this dataset")
    baseline=float(metric["value"]); simulated=baseline*(1+payload.change_percent/100)
    return {"metric":metric["label"],"baseline":baseline,"change_percent":payload.change_percent,"simulated":simulated,"difference":simulated-baseline,"assumptions":"Linear mathematical sensitivity applied to the selected KPI; this is not a forecast and does not validate operational dependencies."}


def build_premium_executive_pdf(analysis: dict[str, Any]) -> io.BytesIO:
    """Render the executive report as a visual document, using the same verified data as the UI."""
    from reportlab.graphics.charts.barcharts import VerticalBarChart
    from reportlab.graphics.charts.lineplots import LinePlot
    from reportlab.graphics.shapes import Drawing, String
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from xml.sax.saxutils import escape
    dataset=analysis["dataset"]; buffer=io.BytesIO(); styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="CoverTitle",parent=styles["Title"],fontSize=29,leading=35,alignment=TA_CENTER,textColor=colors.HexColor("#111D35")))
    styles.add(ParagraphStyle(name="Kicker",parent=styles["Heading2"],fontSize=10,leading=14,alignment=TA_CENTER,textColor=colors.HexColor("#5D7CFB"),spaceAfter=8))
    styles.add(ParagraphStyle(name="Narrative",parent=styles["BodyText"],leading=15,textColor=colors.HexColor("#334155")))
    def footer(canvas, doc):
        canvas.saveState(); canvas.setStrokeColor(colors.HexColor("#DCE2ED")); canvas.line(doc.leftMargin,.48*inch,letter[0]-doc.rightMargin,.48*inch); canvas.setFillColor(colors.HexColor("#64748B")); canvas.setFont("Helvetica",8); canvas.drawString(doc.leftMargin,.32*inch,"BOARDROOM | Executive Decision Intelligence"); canvas.drawRightString(letter[0]-doc.rightMargin,.32*inch,f"Page {doc.page}"); canvas.restoreState()
    story=[Spacer(1,1.1*inch),Paragraph("BOARDROOM",styles["Kicker"]),Paragraph("Executive Decision<br/>Report",styles["CoverTitle"]),Spacer(1,.3*inch),Paragraph(escape(dataset["name"]),ParagraphStyle("ds",parent=styles["Heading2"],alignment=TA_CENTER,textColor=colors.HexColor("#334155"))),Paragraph(escape(f"{dataset['domain']} | {dataset['records']:,} records analyzed"),ParagraphStyle("meta",parent=styles["BodyText"],alignment=TA_CENTER,textColor=colors.HexColor("#64748B"))),Spacer(1,3.5*inch),Paragraph("From Raw Data to Executive Decisions",styles["Kicker"]),Paragraph("Verified calculations. Transparent evidence. Leadership-ready actions.",ParagraphStyle("tag",parent=styles["BodyText"],alignment=TA_CENTER,textColor=colors.HexColor("#64748B"))),PageBreak()]
    story.extend([Paragraph("Executive briefing",styles["Heading1"]),Paragraph(escape(analysis["briefing"]),styles["Narrative"]),Spacer(1,.18*inch),Paragraph("Verified KPI scorecard",styles["Heading2"])])
    kpi_rows=[]
    for index in range(0,len(analysis["kpis"]),2):
        cells=[]
        for item in analysis["kpis"][index:index+2]:
            suffix="%" if item["unit"]=="percent" else ""; trend=f"<br/><font color='#067647'>{item['change_percent']:+.1f}% vs previous period</font>" if item.get("change_percent") is not None else ""
            cells.append(Paragraph(f"<b>{escape(item['label'])}</b><br/><font size=17 color='#111D35'><b>{item['value']:,.2f}{suffix}</b></font>{trend}<br/><font size=7 color='#64748B'>{escape(item['calculation'])}</font>",styles["Narrative"]))
        kpi_rows.append(cells+[""]*(2-len(cells)))
    cards=Table(kpi_rows,colWidths=[3.35*inch,3.35*inch]); cards.setStyle(TableStyle([("BOX",(0,0),(-1,-1),.5,colors.HexColor("#DCE2ED")),("INNERGRID",(0,0),(-1,-1),.5,colors.HexColor("#DCE2ED")),("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#F8FAFC")),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),("TOPPADDING",(0,0),(-1,-1),10),("BOTTOMPADDING",(0,0),(-1,-1),10)])); story.extend([cards,PageBreak(),Paragraph("Performance trends",styles["Heading1"])])
    trend=analysis["trend"][-24:]
    if trend:
        values=[float(item["value"]) for item in trend]; drawing=Drawing(500,260); drawing.add(String(0,242,"Verified monthly revenue trend",fontName="Helvetica-Bold",fontSize=10,fillColor=colors.HexColor("#111D35"))); plot=LinePlot(); plot.x,plot.y,plot.width,plot.height=46,38,430,185; plot.data=[list(enumerate(values))]; plot.xValueAxis.valueMin=0; plot.xValueAxis.valueMax=max(1,len(values)-1); plot.xValueAxis.valueStep=max(1,len(values)//6); plot.yValueAxis.valueMin=min(0,min(values)); plot.yValueAxis.valueMax=max(values)*1.1 or 1; plot.yValueAxis.valueStep=max(1,(plot.yValueAxis.valueMax-plot.yValueAxis.valueMin)/5); plot.lines[0].strokeColor=colors.HexColor("#315EFB"); plot.lines[0].strokeWidth=2.5; drawing.add(plot)
        for index,item in enumerate(trend):
            if index in {0,len(trend)-1} or index%max(1,len(trend)//5)==0: drawing.add(String(46+430*index/max(1,len(trend)-1),17,item["period"],fontSize=6,textAnchor="middle",fillColor=colors.HexColor("#64748B")))
        story.extend([Paragraph("Monthly aggregation of the verified primary revenue measure.",styles["Narrative"]),Spacer(1,.1*inch),drawing])
    story.extend([Spacer(1,.14*inch),Paragraph("What changed and why",styles["Heading1"])])
    driver=next((item for item in analysis["evidence"] if item.get("drivers")),None)
    if driver:
        values=[float(item["contribution"]) for item in driver["drivers"]]; drawing=Drawing(500,245); drawing.add(String(0,228,"Measured segment contributions to the period change",fontName="Helvetica-Bold",fontSize=10,fillColor=colors.HexColor("#111D35"))); chart=VerticalBarChart(); chart.x,chart.y,chart.width,chart.height=44,38,435,165; chart.data=[values]; chart.categoryAxis.categoryNames=[str(item["segment"])[:14] for item in driver["drivers"]]; chart.categoryAxis.labels.angle=25; chart.categoryAxis.labels.dy=-8; chart.valueAxis.valueMin=min(0,min(values)); chart.valueAxis.valueMax=max(values)*1.15 or 1; chart.valueAxis.valueStep=max(1,(chart.valueAxis.valueMax-chart.valueAxis.valueMin)/5); chart.bars[0].fillColor=colors.HexColor("#5D7CFB"); drawing.add(chart); story.extend([Paragraph(escape(driver["finding"]),styles["Narrative"]),Spacer(1,.08*inch),drawing,Paragraph(escape(f"Evidence calculation: {driver['calculation']}"),styles["Code"])])
    story.append(PageBreak()); story.append(Paragraph("Insights, risks and evidence",styles["Heading1"]))
    for item in analysis["evidence"]:
        story.append(KeepTogether([Paragraph(escape(f"{item['title']} | {item['type']}"),styles["Heading3"]),Paragraph(escape(item["finding"]),styles["Narrative"]),Paragraph(escape(f"Evidence: {item['calculation']}"),styles["Code"]),Spacer(1,.09*inch)]))
    story.append(Paragraph("Anomaly and risk radar",styles["Heading2"]))
    rows=[["Severity","Measure","Method","Signals"]]+[[item["severity"].title(),item["column"],item["method"],str(item["count"])] for item in analysis["anomalies"]]
    if len(rows)==1: rows.append(["Informational","No material anomaly","IQR (1.5x)","0"])
    risks=Table(rows,colWidths=[1*inch,1.7*inch,2.6*inch,1.1*inch],repeatRows=1); risks.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#111D35")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#DCE2ED")),("FONTSIZE",(0,0),(-1,-1),8),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F8FAFC")])]))
    story.extend([risks,Spacer(1,.2*inch),Paragraph("Methodology and limitations",styles["Heading1"]),Paragraph(escape(analysis["methodology"]),styles["Narrative"]),Paragraph("Scenario analyses are mathematical sensitivities, not forecasts.",styles["Narrative"])])
    document=SimpleDocTemplate(buffer,pagesize=letter,title="Executive Decision Report",rightMargin=.65*inch,leftMargin=.65*inch,topMargin=.68*inch,bottomMargin=.65*inch); document.build(story,onFirstPage=footer,onLaterPages=footer); buffer.seek(0); return buffer


@app.get("/api/v1/executive/datasets/{dataset_id}/export")
async def export_executive_analysis(dataset_id: str, format: str = Query("markdown", pattern="^(markdown|pdf)$"), user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Export the same calculated executive evidence shown in the Decision Center."""
    analysis = await executive_dataset_analysis(dataset_id, user, db)
    dataset = analysis["dataset"]
    lines = [f"# Executive Decision Report: {dataset['name']}", "", f"**Domain:** {dataset['domain']}  ", f"**Records analyzed:** {dataset['records']:,}  ", f"**Generated:** {dataset['generated_at']}", "", "## Executive briefing", "", analysis["briefing"], "", "## Verified KPIs", "", "| KPI | Value | Calculation |", "| --- | ---: | --- |"]
    for item in analysis["kpis"]:
        suffix = "%" if item["unit"] == "percent" else ""
        lines.append(f"| {item['label']} | {item['value']:,.2f}{suffix} | `{item['calculation']}` |")
    lines.extend(["", "## What changed & why", ""])
    for item in analysis["evidence"]:
        lines.extend([f"### {item['title']} — {item['type']}", item["finding"], "", f"**Evidence calculation:** `{item['calculation']}`", ""])
    lines.extend(["## Anomaly & risk radar", ""])
    for item in analysis["anomalies"]:
        lines.append(f"- **{item['column']}** ({item['severity']}): {item['count']} IQR outlier(s), baseline Q1 {item['baseline']['q1']:.3g}, Q3 {item['baseline']['q3']:.3g}.")
    lines.extend(["", "## Methodology & limitations", "", analysis["methodology"], "", "Scenario results, when used, are mathematical sensitivities rather than forecasts."])
    markdown = "\n".join(lines)
    safe_name = "".join(ch for ch in dataset["name"] if ch.isascii() and (ch.isalnum() or ch in " ._-")) or "executive_report"
    if format == "markdown":
        return StreamingResponse(io.BytesIO(markdown.encode("utf-8")), media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="{safe_name}.md"'})
    return StreamingResponse(
        build_premium_executive_pdf(analysis),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'},
    )
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak
    from xml.sax.saxutils import escape
    buffer = io.BytesIO(); styles = getSampleStyleSheet()
    story = [Spacer(1, 1.25*inch), Paragraph("BOARDROOM", styles["Title"]), Paragraph("Executive Decision Report", styles["Title"]), Spacer(1,.25*inch), Paragraph(escape(dataset["name"]), styles["Heading1"]), Paragraph(escape(f"{dataset['domain']} · {dataset['records']:,} records analyzed"), styles["BodyText"]), Spacer(1,3*inch), Paragraph("From Raw Data to Executive Decisions", styles["Heading2"]), PageBreak(), Paragraph("Executive briefing", styles["Heading1"]), Paragraph(escape(analysis["briefing"]), styles["BodyText"]), Spacer(1,.2*inch), Paragraph("Verified KPI scorecard", styles["Heading2"])]
    table_rows = [["KPI", "Value", "Underlying calculation"]] + [[x["label"], f"{x['value']:,.2f}{'%' if x['unit']=='percent' else ''}", x["calculation"]] for x in analysis["kpis"]]
    table = Table(table_rows, colWidths=[1.45*inch, 1.15*inch, 3.7*inch], repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#111d35")),("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),.25,colors.HexColor("#dce2ed")),("FONTSIZE",(0,0),(-1,-1),8),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f7f9fc")])]))
    story.extend([table, Spacer(1,.25*inch), Paragraph("What changed & why", styles["Heading1"])])
    for item in analysis["evidence"]:
        story.extend([Paragraph(escape(f"{item['title']} · {item['type']}"), styles["Heading3"]), Paragraph(escape(item["finding"]), styles["BodyText"]), Paragraph(escape(f"Evidence: {item['calculation']}"), styles["Code"]), Spacer(1,.1*inch)])
    story.extend([Paragraph("Methodology & limitations", styles["Heading1"]), Paragraph(escape(analysis["methodology"]), styles["BodyText"])])
    document=SimpleDocTemplate(buffer,pagesize=letter,title="Executive Decision Report",rightMargin=.65*inch,leftMargin=.65*inch,topMargin=.65*inch,bottomMargin=.65*inch)
    document.build(story); buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{safe_name}.pdf"'})


def infer_semantic_type(name: str, dtype: str, values: list[Any]) -> str:
    low = name.lower()
    if any(token in low for token in ("email", "e_mail")):
        return "email"
    if any(token in low for token in ("phone", "mobile", "tel")):
        return "phone"
    if any(token in low for token in ("date", "time", "timestamp", "created", "updated")):
        return "datetime"
    if any(token in low for token in ("id", "uuid", "code")):
        return "identifier"
    if "bool" in dtype.lower():
        return "boolean"
    if any(token in dtype.lower() for token in ("int", "decimal", "double", "float")):
        return "measure"
    if values and all(isinstance(v, (int, float, bool)) for v in values):
        return "measure"
    return "category"


def profile_csv(path: Path, table_name: str) -> tuple[int, list[dict[str, Any]]]:
    import pandas as pd
    df = pd.read_csv(path)
    df.columns = [
        f"column_{index + 1}" if not str(column).strip()
        else str(column).strip().replace(" ", "_").replace("-", "_")
        for index, column in enumerate(df.columns)
    ]
    df = df.loc[:, ~df.columns.duplicated()]
    duck = get_duckdb()
    duck.register_dataframe(table_name, df)
    schema = duck.get_table_schema(table_name)
    rows = len(df)
    profiles = []
    for column in schema:
        name = column["column_name"]
        values = df[name].dropna().head(100).tolist()
        numeric = df[name].dropna()
        profile = {
            "column_name": name,
            "data_type": column["data_type"],
            "semantic_type": infer_semantic_type(name, column["data_type"], values),
            "is_nullable": bool(df[name].isna().any()),
            "unique_count": int(df[name].nunique(dropna=True)),
            "null_count": int(df[name].isna().sum()),
            "sample_values": values[:10],
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std_dev": None,
            "top_values": df[name].value_counts(dropna=True).head(10).to_dict(),
        }
        import pandas as pandas_api
        if pandas_api.api.types.is_numeric_dtype(df[name]):
            profile["min"] = float(numeric.min()) if len(numeric) else None
            profile["max"] = float(numeric.max()) if len(numeric) else None
            profile["mean"] = float(numeric.mean()) if len(numeric) else None
            profile["median"] = float(numeric.median()) if len(numeric) else None
            profile["std_dev"] = float(numeric.std()) if len(numeric) else None
        profiles.append(profile)
    return rows, profiles


def profile_sqlite(path: Path, table_name: str, requested_table: str | None = None) -> tuple[int, list[dict[str, Any]], list[str]]:
    import pandas as pd
    with sqlite3.connect(path) as source:
        tables = [row[0] for row in source.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()]
        if not tables:
            raise ValueError("The SQLite file contains no user tables")
        selected = requested_table if requested_table in tables else tables[0]
        quoted = '"' + selected.replace('"', '""') + '"'
        df = pd.read_sql_query(f"SELECT * FROM {quoted}", source)
    df.columns = [
        f"column_{index + 1}" if not str(column).strip()
        else str(column).strip().replace(" ", "_").replace("-", "_")
        for index, column in enumerate(df.columns)
    ]
    duck = get_duckdb()
    duck.register_dataframe(table_name, df)
    rows = len(df)
    profiles = []
    for column in duck.get_table_schema(table_name):
        name = column["column_name"]
        values = df[name].dropna().head(100).tolist()
        numeric = df[name].dropna()
        profile = {
            "column_name": name,
            "data_type": column["data_type"],
            "semantic_type": infer_semantic_type(name, column["data_type"], values),
            "is_nullable": bool(df[name].isna().any()),
            "unique_count": int(df[name].nunique(dropna=True)),
            "null_count": int(df[name].isna().sum()),
            "sample_values": values[:10],
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "std_dev": None,
            "top_values": df[name].value_counts(dropna=True).head(10).to_dict(),
        }
        if pd.api.types.is_numeric_dtype(df[name]):
            profile["min"] = float(numeric.min()) if len(numeric) else None
            profile["max"] = float(numeric.max()) if len(numeric) else None
            profile["mean"] = float(numeric.mean()) if len(numeric) else None
            profile["median"] = float(numeric.median()) if len(numeric) else None
            profile["std_dev"] = float(numeric.std()) if len(numeric) else None
        profiles.append(profile)
    return rows, profiles, tables


@app.post("/api/v1/datasets/upload")
async def upload_dataset(
    workspace_id: str,
    file: UploadFile = File(...),
    sqlite_table: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "dataset:upload" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: dataset:upload")
    workspace = (await db.execute(select(Workspace).where(Workspace.id == workspace_id))).scalar_one_or_none()
    if not workspace or workspace.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Workspace is outside your organization")

    filename = os.path.basename(file.filename or "upload")
    suffix = Path(filename).suffix.lower()
    if suffix not in {".csv", ".sqlite", ".sqlite3", ".db"}:
        raise HTTPException(status_code=400, detail="Only CSV and SQLite files are supported")
    content = await file.read()
    max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(status_code=413, detail="File exceeds upload limit")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = str(uuid.uuid4())
    stored_path = upload_dir / f"{dataset_id}{suffix}"
    stored_path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    table_name = safe_table_name(dataset_id)

    dataset = Dataset(
        id=dataset_id,
        name=filename,
        file_path=str(stored_path),
        file_type=suffix.lstrip("."),
        file_size=len(content),
        workspace_id=workspace_id,
        uploaded_by=user.id,
        status="processing",
    )
    db.add(dataset)
    await db.flush()

    try:
        sqlite_tables = []
        if suffix == ".csv":
            row_count, profiles = profile_csv(stored_path, table_name)
        else:
            row_count, profiles, sqlite_tables = profile_sqlite(stored_path, table_name, sqlite_table)
        dataset.row_count = row_count
        dataset.status = "ready"
        for profile in profiles:
            semantic = SemanticModel(
                dataset_id=dataset.id,
                column_name=profile["column_name"],
                data_type=profile["data_type"],
                semantic_type=profile["semantic_type"],
                is_nullable=profile["is_nullable"],
                unique_count=profile["unique_count"],
                null_count=profile["null_count"],
                sample_values={"values": profile["sample_values"]},
            )
            db.add(semantic)
            await db.flush()
            from app.models.schema import ColumnProfile
            db.add(ColumnProfile(
                semantic_model_id=semantic.id,
                min_val=str(profile["min"]) if profile["min"] is not None else None,
                max_val=str(profile["max"]) if profile["max"] is not None else None,
                mean_val=profile["mean"],
                median_val=profile["median"],
                std_dev=profile["std_dev"],
                top_values=profile["top_values"],
            ))
    except Exception as exc:
        dataset.status = "error"
        dataset.description = str(exc)
        await db.commit()
        raise HTTPException(status_code=400, detail=f"Could not ingest dataset: {exc}")

    await audit(db, user, "dataset.upload", "dataset", dataset.id,
               {"filename": filename, "checksum": checksum, "row_count": row_count})
    await db.commit()
    return {
        "id": dataset.id,
        "name": dataset.name,
        "file_type": dataset.file_type,
        "row_count": dataset.row_count,
        "status": dataset.status,
        "checksum": checksum,
        "sqlite_tables": sqlite_tables,
        "table_name": table_name,
    }


@app.get("/api/v1/datasets")
async def list_datasets(
    workspace_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "dataset:view" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: dataset:view")
    result = await db.execute(
        select(Dataset).join(Workspace, Dataset.workspace_id == Workspace.id).where(
            Workspace.organization_id == user.organization_id
        )
    )
    datasets = result.scalars().all()
    if workspace_id:
        datasets = [d for d in datasets if d.workspace_id == workspace_id]
    return [{"id": d.id, "name": d.name, "file_type": d.file_type,
             "row_count": d.row_count, "status": d.status,
             "workspace_id": d.workspace_id, "created_at": d.created_at.isoformat()}
            for d in datasets]


@app.get("/api/v1/datasets/{dataset_id}")
async def get_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dataset = await get_authorized_dataset(dataset_id, user, db)
    return {"id": dataset.id, "name": dataset.name, "file_type": dataset.file_type,
            "file_size": dataset.file_size, "row_count": dataset.row_count,
            "status": dataset.status, "workspace_id": dataset.workspace_id,
            "description": dataset.description}


@app.delete("/api/v1/datasets/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "dataset:delete" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: dataset:delete")
    dataset = await get_authorized_dataset(dataset_id, user, db)
    get_duckdb().drop_table(safe_table_name(dataset.id))
    await db.delete(dataset)
    await audit(db, user, "dataset.delete", "dataset", dataset.id)
    await db.commit()
    return {"deleted": True}


@app.get("/api/v1/schema/datasets/{dataset_id}")
async def get_schema(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dataset = await get_authorized_dataset(dataset_id, user, db)
    result = await db.execute(select(SemanticModel).where(SemanticModel.dataset_id == dataset.id))
    models = result.scalars().all()
    return [{"id": m.id, "column_name": m.column_name, "data_type": m.data_type,
             "semantic_type": m.semantic_type, "description": m.description,
             "is_pii": m.is_pii, "is_nullable": m.is_nullable,
             "unique_count": m.unique_count, "null_count": m.null_count,
             "sample_values": m.sample_values} for m in models]


def schema_explanation(column: SemanticModel) -> tuple[str, str, bool]:
    """Explain inferred field roles without claiming certainty beyond observed metadata."""
    name = column.column_name.lower()
    pii = column.semantic_type in {"email", "phone"} or any(word in name for word in ("email", "phone", "mobile", "address"))
    if pii:
        return "sensitive", "Name pattern indicates potential personally identifiable information; mask it in prompts and exports.", True
    if column.semantic_type == "datetime":
        return "time", f"Detected as a date/time field from its name and parseable values; {column.null_count or 0} null value(s) need review.", False
    if column.semantic_type == "identifier":
        return "identifier", f"Name and uniqueness pattern indicate a record identifier ({column.unique_count or 0} distinct values).", False
    if column.semantic_type == "measure":
        business_role = "revenue" if any(word in name for word in ("revenue", "sales", "gross_sales", "net_sales", "mrr")) else "measure"
        return business_role, f"Numeric distribution supports aggregation; {column.null_count or 0} null value(s) are excluded from calculations.", False
    return "dimension", f"Low-cardinality categorical field with {column.unique_count or 0} distinct value(s), suitable for segment analysis.", False


def schema_readiness(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    included = [column for column in columns if column.get("include", True)]
    roles = {column.get("role") for column in included}
    has_time = "time" in roles
    has_revenue = "revenue" in roles
    has_measure = has_revenue or "measure" in roles
    has_identifier = "identifier" in roles
    return [
        {"use_case": "Executive reporting", "ready": has_measure, "score": 92 if has_measure else 35,
         "reason": "A revenue or numeric business measure is approved." if has_measure else "Approve at least one business measure to generate KPI scorecards."},
        {"use_case": "Trend analysis", "ready": has_measure and has_time, "score": 90 if has_measure and has_time else 45,
         "reason": "Approved time and measure fields support comparable period trends." if has_measure and has_time else "Approve a reporting date and a numeric measure for trends."},
        {"use_case": "Customer analysis", "ready": has_identifier, "score": 88 if has_identifier else 40,
         "reason": "An approved identifier supports distinct-count and segment analysis." if has_identifier else "Approve a customer, order, or account identifier."},
        {"use_case": "Forecasting", "ready": False, "score": 0,
         "reason": "Requires an approved time series with sufficient validated monthly history; model validation is still required."},
    ]


@app.get("/api/v1/schema/datasets/{dataset_id}/approval")
async def get_schema_approval(dataset_id: str, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    dataset = await get_authorized_dataset(dataset_id, user, db)
    from sqlalchemy import desc
    models = list((await db.execute(select(SemanticModel).where(SemanticModel.dataset_id == dataset.id))).scalars().all())
    approval = (await db.execute(select(SchemaApproval).where(SchemaApproval.dataset_id == dataset.id).order_by(desc(SchemaApproval.version_number)).limit(1))).scalar_one_or_none()
    saved = {item["column_name"]: item for item in (approval.contract.get("columns", []) if approval else [])}
    columns=[]
    for model in models:
        role, reason, pii = schema_explanation(model)
        stored=saved.get(model.column_name,{})
        columns.append({"column_name":model.column_name,"data_type":model.data_type,"unique_count":model.unique_count,"null_count":model.null_count,"role":stored.get("role",role),"include":stored.get("include",True),"is_pii":stored.get("is_pii",pii),"reason":reason})
    return {"dataset_id":dataset.id,"dataset_name":dataset.name,"domain":approval.contract.get("domain") if approval else detect_business_domain(models),"status":approval.status if approval else "pending_approval","version":approval.version_number if approval else 0,"primary_date_column":approval.contract.get("primary_date_column") if approval else next((item["column_name"] for item in columns if item["role"]=="time"),None),"columns":columns,"readiness":schema_readiness(columns),"approval_note":"Raw uploaded data is retained unchanged. This approval controls semantic meaning and analytical eligibility."}


@app.post("/api/v1/schema/datasets/{dataset_id}/approval")
async def approve_schema(dataset_id: str, payload: SchemaApprovalRequest, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    dataset = await get_authorized_dataset(dataset_id, user, db, require_write=True)
    models=list((await db.execute(select(SemanticModel).where(SemanticModel.dataset_id == dataset.id))).scalars().all())
    known={model.column_name:model for model in models}
    approved=[]
    for item in payload.columns:
        name=item.get("column_name")
        if name not in known: raise HTTPException(status_code=422,detail=f"Unknown schema column: {name}")
        role=item.get("role","dimension")
        if role not in {"time","revenue","measure","dimension","identifier","sensitive","ignored"}: raise HTTPException(status_code=422,detail=f"Unsupported role for {name}")
        include=bool(item.get("include",role not in {"ignored","sensitive"}))
        model=known[name]; model.semantic_type={"time":"datetime","revenue":"measure","measure":"measure","dimension":"category","identifier":"identifier","sensitive":"email","ignored":"ignored"}[role]; model.is_pii=bool(item.get("is_pii",role=="sensitive")); model.description=f"Approved business role: {role}"
        approved.append({"column_name":name,"role":role,"include":include,"is_pii":model.is_pii})
    from sqlalchemy import func
    prior=(await db.execute(select(func.max(SchemaApproval.version_number)).where(SchemaApproval.dataset_id == dataset.id))).scalar_one() or 0
    contract={"domain":payload.domain or detect_business_domain(models),"primary_date_column":payload.primary_date_column,"columns":approved,"approved_at":datetime.now(timezone.utc).isoformat()}
    record=SchemaApproval(dataset_id=dataset.id,version_number=prior+1,status="approved",contract=contract,approved_by=user.id)
    db.add(record); await audit(db,user,"schema.approve","dataset",dataset.id,{"version":record.version_number,"columns":len(approved)}); await db.commit()
    return {"status":"approved","version":record.version_number,"contract":contract,"readiness":schema_readiness(approved)}


@app.post("/api/v1/quality/datasets/{dataset_id}/scan")
async def quality_scan(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    dataset = await get_authorized_dataset(dataset_id, user, db)
    table = safe_table_name(dataset.id)
    if not get_duckdb().table_exists(table):
        raise HTTPException(status_code=409, detail="Dataset is not loaded in the analytics engine")
    result = await db.execute(select(SemanticModel).where(SemanticModel.dataset_id == dataset.id))
    columns = result.scalars().all()
    issues = []
    null_total = 0
    invalid_date_total = 0
    import pandas as pd
    quality_frame = get_duckdb().query_df(f"SELECT * FROM {quote_identifier(table)}")
    duplicate_total = int(quality_frame.duplicated().sum())
    if duplicate_total:
        issues.append({"type": "duplicate_records", "column": None, "count": duplicate_total,
                       "severity": "high" if duplicate_total / max(1, len(quality_frame)) > .02 else "medium"})
    for column in columns:
        if column.null_count:
            null_total += column.null_count
            issues.append({"type": "missing_values", "column": column.column_name,
                           "count": column.null_count, "severity": "medium"})
        if column.semantic_type == "datetime":
            raw_values = get_duckdb().query_df(
                f"SELECT {quote_identifier(column.column_name)} "
                f"FROM {quote_identifier(table)}"
            )[column.column_name]
            text_values = raw_values.astype("string").str.strip()
            missing_values = raw_values.isna() | text_values.eq("")
            parsed_dates = pd.to_datetime(text_values, format="mixed", errors="coerce", utc=True)
            invalid_count = int((~missing_values & parsed_dates.isna()).sum())
            if invalid_count:
                invalid_date_total += invalid_count
                issues.append({"type": "invalid_dates", "column": column.column_name,
                               "count": invalid_count, "severity": "medium"})
        if column.unique_count == 1:
            issues.append({"type": "constant_column", "column": column.column_name,
                           "count": dataset.row_count, "severity": "low"})
    total_cells = max(1, (dataset.row_count or 0) * len(columns))
    completeness = round(max(0.0, 1 - null_total / total_cells) * 100, 2)
    invalid_date_pct = invalid_date_total / max(1, dataset.row_count or 0) * 100
    duplicate_pct = duplicate_total / max(1, dataset.row_count or 0) * 100
    constant_columns = sum(issue["type"] == "constant_column" for issue in issues)
    consistency = round(max(0.0, 100 - invalid_date_pct - duplicate_pct - constant_columns * 5), 2)
    overall = round((completeness + consistency) / 2, 2)
    recommendations = []
    if any(issue["type"] == "missing_values" for issue in issues):
        recommendations.append({"action": "Review missing values in the flagged columns", "priority": "high"})
    if any(issue["type"] == "invalid_dates" for issue in issues):
        recommendations.append({"action": "Normalize or remove unparseable date values", "priority": "high"})
    if duplicate_total:
        recommendations.append({"action": "Review duplicate records before using totals or customer counts", "priority": "high"})
    if any(issue["type"] == "constant_column" for issue in issues):
        recommendations.append({"action": "Review constant columns for analytical relevance", "priority": "low"})
    if not recommendations:
        recommendations.append({"action": "Dataset is ready for analysis", "priority": "low"})
    report = QualityReport(dataset_id=dataset.id, overall_score=overall,
                           completeness_score=completeness, consistency_score=consistency,
                           accuracy_score=consistency, issues={"items": issues},
                           recommendations={"items": recommendations},
                           generated_by=user.id, status="completed")
    db.add(report)
    await audit(db, user, "quality.scan", "dataset", dataset.id, {"score": overall})
    await db.commit()
    return {"id": report.id, "overall_score": overall, "completeness_score": completeness,
            "consistency_score": consistency, "accuracy_score": consistency,
            "issues": issues, "recommendations": recommendations,
            "raw_records": len(quality_frame), "duplicate_records": duplicate_total,
            "duplicate_percent": round(duplicate_pct, 2),
            "missing_cells": null_total, "invalid_dates": invalid_date_total,
            "cleaning_actions": "No records were altered; this report profiles raw uploaded data."}


@app.get("/api/v1/quality/datasets/{dataset_id}")
async def quality_latest(
    dataset_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await get_authorized_dataset(dataset_id, user, db)
    from sqlalchemy import desc
    report = (await db.execute(
        select(QualityReport).where(QualityReport.dataset_id == dataset_id)
        .order_by(desc(QualityReport.created_at)).limit(1)
    )).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="No quality report found")
    return {"id": report.id, "overall_score": report.overall_score,
            "completeness_score": report.completeness_score,
            "consistency_score": report.consistency_score,
            "accuracy_score": report.accuracy_score,
            "issues": report.issues.get("items", []) if report.issues else [],
            "recommendations": report.recommendations.get("items", []) if report.recommendations else []}


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def infer_nl_sql(question: str, table_name: str, columns: list[SemanticModel]) -> str:
    low = question.lower()
    numeric = [c for c in columns if c.semantic_type == "measure"]
    categorical = [c for c in columns if c.semantic_type == "category"]
    dates = [c for c in columns if c.semantic_type == "datetime"]
    table = quote_identifier(table_name)

    if any(word in low for word in ("count", "how many", "number of rows")):
        return f"SELECT COUNT(*) AS result_count FROM {table}"
    if any(word in low for word in ("show rows", "sample rows", "preview", "list records")):
        return f"SELECT * FROM {table} LIMIT 100"

    def choose_column(items: list[SemanticModel]) -> SemanticModel | None:
        return next(
            (column for column in items if column.column_name.lower() in low),
            items[0] if items else None,
        )

    if any(word in low for word in ("scatter", "correlation", "relationship")) and len(numeric) >= 2:
        x_column, y_column = numeric[:2]
        return (
            f"SELECT {quote_identifier(x_column.column_name)}, "
            f"{quote_identifier(y_column.column_name)} FROM {table} "
            f"WHERE {quote_identifier(x_column.column_name)} IS NOT NULL "
            f"AND {quote_identifier(y_column.column_name)} IS NOT NULL LIMIT 1000"
        )

    if any(word in low for word in ("trend", "over time", "by month", "by date")) and dates and numeric:
        date_column = choose_column(dates)
        measure = choose_column(numeric)
        raw_date = f"TRIM({quote_identifier(date_column.column_name)})"
        parsed_date = (
            f"COALESCE(TRY_CAST({raw_date} AS TIMESTAMP), "
            f"TRY_STRPTIME({raw_date}, ['%m/%d/%Y', '%d-%b-%Y', '%Y/%m/%d']))"
        )
        return (
            f"SELECT DATE_TRUNC('month', {parsed_date}) AS period, "
            f"SUM({quote_identifier(measure.column_name)}) AS total "
            f"FROM {table} WHERE {parsed_date} IS NOT NULL "
            "GROUP BY period ORDER BY period"
        )

    if numeric:
        measure = choose_column(numeric)
        if measure and any(word in low for word in ("average", "mean", "avg")):
            return f"SELECT AVG({quote_identifier(measure.column_name)}) AS average FROM {table}"
        if measure and any(word in low for word in ("sum", "total", "revenue", "sales")):
            group = choose_column(categorical)
            if group:
                return (
                    f"SELECT {quote_identifier(group.column_name)} AS category, "
                    f"SUM({quote_identifier(measure.column_name)}) AS total "
                    f"FROM {table} GROUP BY {quote_identifier(group.column_name)} "
                    "ORDER BY total DESC"
                )
            return f"SELECT SUM({quote_identifier(measure.column_name)}) AS total FROM {table}"

    if any(word in low for word in ("breakdown", "distribution", "group by", "by category")) and categorical:
        group = choose_column(categorical)
        return (
            f"SELECT {quote_identifier(group.column_name)} AS category, COUNT(*) AS row_count "
            f"FROM {table} GROUP BY category ORDER BY row_count DESC"
        )

    raise ValueError(
        "Could not map this question to a supported query. Ask for a row count, "
        "sum/average, category breakdown, time trend, or configure an LLM provider."
    )


def clean_generated_sql(content: str) -> str:
    sql = content.strip()
    if sql.startswith("```"):
        sql = sql.split("\n", 1)[-1]
        if sql.endswith("```"):
            sql = sql[:-3]
        sql = sql.strip()
        if sql.lower().startswith("sql"):
            sql = sql[3:].strip()
    return sql


async def generate_nl_sql(
    question: str,
    table_name: str,
    columns: list[SemanticModel],
    correction: str | None = None,
    previous_sql: str | None = None,
) -> tuple[str, str]:
    if not settings.OPENAI_API_KEY:
        if correction:
            raise ValueError(f"Unable to repair query without an LLM provider: {correction}")
        return infer_nl_sql(question, table_name, columns), "rule_based"

    schema = [
        {"name": column.column_name, "type": column.data_type, "meaning": column.semantic_type}
        for column in columns
    ]
    messages = [
        {
            "role": "system",
            "content": (
                "You translate business questions into one DuckDB SELECT query. "
                "Only query the supplied table and columns. Never use file, network, "
                "catalog, system, or write operations. Return SQL only, without markdown. "
                "Prefer explicit aliases and useful aggregations. For mixed-format date "
                "columns use TRY_CAST/TRY_STRPTIME and omit values that cannot be parsed."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Table: {quote_identifier(table_name)}\n"
                f"Schema: {schema}\n"
                f"Question: {question}\n"
                + (
                    f"Previous SQL failed with: {correction}\n"
                    f"Previous SQL: {previous_sql}\n"
                    "Repair it using only the supplied table and schema."
                    if correction else ""
                )
            ),
        },
    ]
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    completion = await client.chat.completions.create(
        model=settings.DEFAULT_AI_MODEL,
        messages=messages,
        temperature=0,
    )
    content = completion.choices[0].message.content
    if not content:
        raise ValueError("The configured model returned an empty SQL response")
    return clean_generated_sql(content), settings.DEFAULT_AI_MODEL


def infer_chart(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not rows:
        return None
    keys = list(rows[0])
    numeric_keys = [
        key for key in keys
        if all(value is None or isinstance(value, (int, float)) for value in (row.get(key) for row in rows))
        and any(isinstance(row.get(key), (int, float)) for row in rows)
    ]
    dimension_keys = [key for key in keys if key not in numeric_keys]
    if len(numeric_keys) >= 2:
        points = [
            {"x": row.get(numeric_keys[0]), "y": row.get(numeric_keys[1])}
            for row in rows
            if row.get(numeric_keys[0]) is not None and row.get(numeric_keys[1]) is not None
        ]
        if not points:
            return None
        return {
            "type": "scatter",
            "x_key": numeric_keys[0],
            "y_key": numeric_keys[1],
            "data": points,
        }
    if numeric_keys and dimension_keys:
        x_key, y_key = dimension_keys[0], numeric_keys[0]
        points = [
            {"x": str(row.get(x_key)), "y": row.get(y_key)}
            for row in rows
            if row.get(x_key) is not None and row.get(y_key) is not None
        ]
        if not points:
            return None
        is_date = any(token in x_key.lower() for token in ("date", "time", "period"))
        return {
            "type": "line" if is_date else "bar",
            "x_key": x_key,
            "y_key": y_key,
            "data": points,
        }
    return None


def detect_outliers(dataset_id: str, columns: list[SemanticModel]) -> list[dict[str, Any]]:
    table = quote_identifier(safe_table_name(dataset_id))
    connection = get_duckdb().connection
    outliers = []
    for column in columns:
        if column.semantic_type != "measure":
            continue
        name = quote_identifier(column.column_name)
        quartiles = connection.execute(
            f"SELECT quantile_cont({name}, 0.25), quantile_cont({name}, 0.75) "
            f"FROM {table}"
        ).fetchone()
        if not quartiles or quartiles[0] is None or quartiles[1] is None:
            continue
        q1, q3 = float(quartiles[0]), float(quartiles[1])
        spread = q3 - q1
        lower, upper = q1 - 1.5 * spread, q3 + 1.5 * spread
        count = connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE {name} < ? OR {name} > ?",
            [lower, upper],
        ).fetchone()[0]
        if count:
            samples = connection.execute(
                f"SELECT {name} FROM {table} WHERE {name} < ? OR {name} > ? "
                f"ORDER BY ABS({name} - ?) DESC LIMIT 5",
                [lower, upper, (q1 + q3) / 2],
            ).fetchall()
            outliers.append({
                "column": column.column_name,
                "method": "IQR",
                "count": count,
                "lower_bound": lower,
                "upper_bound": upper,
                "examples": [float(row[0]) for row in samples],
            })
    return outliers


def to_json_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_json_value(item) for item in value]
    if hasattr(value, "item"):
        return to_json_value(value.item())
    return value


def serialize_chat_message(message: ChatMessage) -> dict[str, Any]:
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "metadata": message.message_metadata or {},
        "created_at": message.created_at.isoformat(),
    }


@app.get("/api/v1/conversations")
async def list_conversations(
    workspace_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(Conversation)
        .join(Workspace, Conversation.workspace_id == Workspace.id)
        .where(
            Conversation.user_id == user.id,
            Workspace.organization_id == user.organization_id,
        )
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    )
    if workspace_id:
        query = query.where(Conversation.workspace_id == workspace_id)
    conversations = (await db.execute(query)).scalars().all()
    datasets = {}
    if conversations:
        dataset_ids = {conversation.dataset_id for conversation in conversations}
        dataset_rows = (await db.execute(select(Dataset).where(Dataset.id.in_(dataset_ids)))).scalars().all()
        datasets = {dataset.id: dataset.name for dataset in dataset_rows}
    return [
        {
            "id": conversation.id,
            "title": conversation.title,
            "dataset_id": conversation.dataset_id,
            "dataset_name": datasets.get(conversation.dataset_id, "Dataset"),
            "updated_at": conversation.updated_at.isoformat(),
        }
        for conversation in conversations
    ]


@app.get("/api/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation = (await db.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": conversation.id,
        "title": conversation.title,
        "dataset_id": conversation.dataset_id,
        "messages": [serialize_chat_message(message) for message in conversation.messages],
    }


@app.post("/api/v1/analytics/query")
async def analytics_query(
    payload: QueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "analytics:query" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: analytics:query")
    dataset = await get_authorized_dataset(payload.dataset_id, user, db)
    workspace = (await db.execute(select(Workspace).where(Workspace.id == payload.workspace_id))).scalar_one_or_none()
    if not workspace or workspace.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Workspace is outside your organization")
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="Question cannot be empty")
    if payload.conversation_id:
        conversation = (await db.execute(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.user_id == user.id,
            )
        )).scalar_one_or_none()
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if conversation.workspace_id != workspace.id or conversation.dataset_id != dataset.id:
            raise HTTPException(status_code=409, detail="Conversation context does not match the selected dataset")
    else:
        conversation = Conversation(
            workspace_id=workspace.id,
            dataset_id=dataset.id,
            user_id=user.id,
            title=payload.question.strip()[:255],
        )
        db.add(conversation)
        await db.flush()

    last_sequence = (await db.execute(
        select(ChatMessage.sequence_order)
        .where(ChatMessage.conversation_id == conversation.id)
        .order_by(ChatMessage.sequence_order.desc())
        .limit(1)
    )).scalar_one_or_none()
    user_message = ChatMessage(
        conversation_id=conversation.id,
        role="user",
        content=payload.question.strip(),
        sequence_order=(last_sequence + 1) if last_sequence is not None else 0,
    )
    db.add(user_message)
    await db.flush()
    greeting_words = {"hi", "hello", "hey", "good morning", "good afternoon", "good evening"}
    if payload.question.strip().lower().rstrip("!?.") in greeting_words:
        assistant_message = ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=("Hello — I’m ready to analyze this dataset with verified, read-only calculations. "
                     "Try ‘Show monthly sales trend’, ‘Compare sales by region’, ‘What is the average order value?’, "
                     "or ‘Which products have the highest profit?’"),
            message_metadata={"generation_method": "guided_response", "suggestions": [
                "Show monthly sales trend", "Compare sales by region", "Which products have the highest profit?"
            ]},
            sequence_order=user_message.sequence_order + 1,
        )
        db.add(assistant_message)
        conversation.updated_at = datetime.now(timezone.utc)
        await db.commit()
        return {"conversation_id": conversation.id, "assistant_message_id": assistant_message.id,
                "summary": assistant_message.content, "generation_method": "guided_response"}
    result = await db.execute(select(SemanticModel).where(SemanticModel.dataset_id == dataset.id))
    columns = result.scalars().all()
    columns = list(columns)
    run = AnalyticsRun(workspace_id=payload.workspace_id, user_id=user.id,
                       natural_language_query=payload.question,
                       status="running", model_used=payload.model_id)
    db.add(run)
    await db.flush()
    started = perf_counter()
    sql = ""
    provider = "rule_based"
    repaired = False
    try:
        correction = None
        for attempt in range(2):
            sql, provider = await generate_nl_sql(
                payload.question,
                safe_table_name(dataset.id),
                columns,
                correction=correction,
                previous_sql=sql or None,
            )
            try:
                validated = validate_sql(sql, {safe_table_name(dataset.id)})
                limited = add_limit(validated, 10000)
                rows = get_duckdb().query_dicts(limited)
                repaired = attempt > 0
                break
            except Exception as exc:
                if attempt == 1 or provider == "rule_based":
                    raise
                correction = str(exc)
        rows = [{key: value.item() if hasattr(value, "item") else value for key, value in row.items()} for row in rows]
        summary = f"Query returned {len(rows)} result rows."
        outliers = detect_outliers(dataset.id, columns)
        chart = infer_chart(rows)
        assistant_metadata = to_json_value({
            "run_id": run.id,
            "question": payload.question.strip(),
            "sql": sql,
            "columns": list(rows[0].keys()) if rows else [],
            "rows": rows[:100],
            "chart": chart,
            "outliers": outliers,
            "generation_method": provider,
            "repaired": repaired,
        })
        run.status = "completed"
        run.generated_sql = sql
        run.result_summary = summary
        run.duration_ms = int((perf_counter() - started) * 1000)
        run.model_used = provider
    except Exception as exc:
        run.status = "failed"
        run.generated_sql = sql or None
        run.error_message = str(exc)
        db.add(ChatMessage(
            conversation_id=conversation.id,
            role="assistant",
            content=f"Query failed: {exc}",
            message_metadata={"run_id": run.id, "error": str(exc)},
            sequence_order=user_message.sequence_order + 1,
        ))
        conversation.updated_at = datetime.now(timezone.utc)
        await db.commit()
        status_code = 422 if isinstance(exc, ValueError) else 400
        raise HTTPException(status_code=status_code, detail=f"Query failed: {exc}")
    await audit(db, user, "analytics.query", "analytics_run", run.id,
               {"dataset_id": dataset.id, "row_count": len(rows), "provider": provider})
    assistant_message = ChatMessage(
        conversation_id=conversation.id,
        role="assistant",
        content=summary,
        message_metadata=assistant_metadata,
        sequence_order=user_message.sequence_order + 1,
    )
    db.add(assistant_message)
    conversation.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()
    return {
        "conversation_id": conversation.id,
        "assistant_message_id": assistant_message.id,
        **assistant_metadata,
        "summary": summary,
    }


@app.post("/api/v1/analytics/sql")
async def execute_sql(
    payload: SQLRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "analytics:advanced" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: analytics:advanced")
    dataset = await get_authorized_dataset(payload.dataset_id, user, db)
    allowed = {safe_table_name(dataset.id)}
    try:
        sql = validate_sql(payload.sql, allowed)
        sql = add_limit(sql, 10000)
        rows = get_duckdb().query_dicts(sql)
    except SQLSandboxError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Query failed: {exc}")
    return {"sql": sql, "columns": list(rows[0].keys()) if rows else [], "rows": rows[:100]}


@app.get("/api/v1/runs")
async def list_runs(
    workspace_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import desc
    result = await db.execute(
        select(AnalyticsRun).join(Workspace, AnalyticsRun.workspace_id == Workspace.id)
        .where(Workspace.organization_id == user.organization_id)
        .order_by(desc(AnalyticsRun.created_at)).limit(100)
    )
    runs = result.scalars().all()
    if workspace_id:
        runs = [r for r in runs if r.workspace_id == workspace_id]
    return [{"id": r.id, "question": r.natural_language_query,
             "sql": r.generated_sql, "status": r.status,
             "summary": r.result_summary, "error": r.error_message,
             "model": r.model_used, "created_at": r.created_at.isoformat()}
            for r in runs]


@app.post("/api/v1/reports")
async def create_report(
    payload: ReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "report:create" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: report:create")
    summary = payload.content.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise HTTPException(status_code=422, detail="A report requires a non-empty evidence summary")
    workspace = (await db.execute(select(Workspace).where(Workspace.id == payload.workspace_id))).scalar_one_or_none()
    if not workspace or workspace.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Workspace is outside your organization")
    report = Report(title=payload.title, description=payload.description,
                    workspace_id=workspace.id, created_by=user.id, content=payload.content)
    db.add(report)
    await audit(db, user, "report.create", "report")
    await db.commit()
    await db.refresh(report)
    return {"id": report.id, "title": report.title, "description": report.description,
            "content": report.content, "is_published": report.is_published,
            "created_at": report.created_at.isoformat()}


@app.get("/api/v1/reports")
async def list_reports(
    workspace_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Report).join(Workspace, Report.workspace_id == Workspace.id)
        .where(Workspace.organization_id == user.organization_id)
    )
    reports = result.scalars().all()
    if workspace_id:
        reports = [r for r in reports if r.workspace_id == workspace_id]
    return [{"id": r.id, "title": r.title, "description": r.description,
             "content": r.content, "is_published": r.is_published,
             "created_at": r.created_at.isoformat()} for r in reports]


def provider_is_configured(provider_name: str) -> bool:
    return {
        "openai": bool(settings.OPENAI_API_KEY),
        "anthropic": bool(settings.ANTHROPIC_API_KEY),
        "google": bool(settings.GEMINI_API_KEY),
        "local": bool(settings.LOCAL_LLM_BASE_URL),
    }.get(provider_name, False)


async def generate_report_summary(
    provider_name: str,
    model_name: str,
    evidence: dict[str, Any],
) -> str:
    prompt = (
        "Write a concise executive review of the supplied analytics evidence. "
        "Separate observed facts from interpretation. Cite actual values and dates; "
        "never invent causes or numbers. State when evidence is insufficient. "
        "Include key trend direction, notable outliers, and 2-3 decisions or follow-ups.\n\n"
        + json.dumps(evidence, ensure_ascii=False, default=str)
    )
    if provider_name == "openai":
        from openai import APIError as OpenAIAPIError

        try:
            response = await AsyncOpenAI(api_key=settings.OPENAI_API_KEY).chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=1200,
            )
        except OpenAIAPIError as exc:
            raise HTTPException(status_code=502, detail=f"OpenAI report generation failed: {exc}") from exc
        summary = response.choices[0].message.content
    elif provider_name == "anthropic":
        from anthropic import APIError as AnthropicAPIError, AsyncAnthropic

        try:
            response = await AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY).messages.create(
                model=model_name,
                max_tokens=1200,
                temperature=0.2,
                messages=[{"role": "user", "content": prompt}],
            )
        except AnthropicAPIError as exc:
            raise HTTPException(status_code=502, detail=f"Anthropic report generation failed: {exc}") from exc
        summary = response.content[0].text if response.content else None
    elif provider_name == "google":
        import google.generativeai as genai
        from google.api_core.exceptions import GoogleAPIError

        genai.configure(api_key=settings.GEMINI_API_KEY)
        try:
            response = await genai.GenerativeModel(model_name).generate_content_async(
                prompt,
                generation_config={"temperature": 0.2, "max_output_tokens": 1200},
            )
        except GoogleAPIError as exc:
            raise HTTPException(status_code=502, detail=f"Google report generation failed: {exc}") from exc
        summary = response.text
    elif provider_name == "local":
        import httpx

        try:
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    f"{settings.LOCAL_LLM_BASE_URL.rstrip('/')}/api/chat",
                    json={
                        "model": model_name,
                        "stream": False,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Local model request failed: {exc}") from exc
        summary = response.json().get("message", {}).get("content")
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported model provider: {provider_name}")

    if not summary or not summary.strip():
        raise HTTPException(status_code=502, detail="The selected model returned an empty report")
    return summary.strip()


@app.post("/api/v1/reports/generate")
async def generate_report(
    payload: GenerateReportRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "report:create" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: report:create")
    if not user.is_superuser and "model:select" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: model:select")

    conversation = (await db.execute(
        select(Conversation).where(
            Conversation.id == payload.conversation_id,
            Conversation.user_id == user.id,
        )
    )).scalar_one_or_none()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    message = (await db.execute(
        select(ChatMessage).where(
            ChatMessage.id == payload.message_id,
            ChatMessage.conversation_id == conversation.id,
            ChatMessage.role == "assistant",
        )
    )).scalar_one_or_none()
    if not message or not message.message_metadata or not message.message_metadata.get("run_id"):
        raise HTTPException(status_code=422, detail="Select a saved analytics result to generate a report")
    run = (await db.execute(
        select(AnalyticsRun).where(
            AnalyticsRun.id == message.message_metadata["run_id"],
            AnalyticsRun.user_id == user.id,
            AnalyticsRun.status == "completed",
        )
    )).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=422, detail="The saved analytics result is not a completed run")

    model_row = (await db.execute(
        select(AIModel, AIProvider)
        .join(AIProvider, AIModel.provider_id == AIProvider.id)
        .where(AIModel.id == payload.model_id, AIModel.is_active.is_(True), AIProvider.is_active.is_(True))
    )).one_or_none()
    if not model_row:
        raise HTTPException(status_code=404, detail="Selected model is unavailable")
    model, provider = model_row
    if not provider_is_configured(provider.name):
        raise HTTPException(
            status_code=400,
            detail=f"No credentials or endpoint are configured for {provider.display_name}",
        )

    semantic_models = (await db.execute(
        select(SemanticModel).where(SemanticModel.dataset_id == conversation.dataset_id)
    )).scalars().all()
    private_columns = {column.column_name for column in semantic_models if column.is_pii}
    message_data = message.message_metadata
    safe_rows = [
        {key: value for key, value in row.items() if key not in private_columns}
        for row in message_data.get("rows", [])[:40]
    ]
    source_chart = message_data.get("chart")
    safe_chart = source_chart
    if source_chart and (
        source_chart.get("x_key") in private_columns
        or source_chart.get("y_key") in private_columns
    ):
        safe_chart = None
    evidence = {
        "question": message_data.get("question", conversation.title),
        "validated_sql": message_data.get("sql"),
        "result_rows": safe_rows,
        "statistical_outliers": message_data.get("outliers", []),
    }
    summary = await generate_report_summary(provider.name, model.name, evidence)
    dataset = (await db.execute(
        select(Dataset).where(Dataset.id == conversation.dataset_id)
    )).scalar_one()
    title = (payload.title or f"Executive review: {conversation.title}")[:255]
    report_content = to_json_value({
        "summary": summary,
        "question": message_data.get("question", conversation.title),
        "sql": message_data.get("sql"),
        "rows": safe_rows,
        "chart": safe_chart,
        "outliers": message_data.get("outliers", []),
        "model": {"id": model.id, "name": model.display_name, "provider": provider.display_name},
        "run_id": message_data["run_id"],
        "conversation_id": conversation.id,
        "source_message_id": message.id,
    })
    report = Report(
        title=title,
        description=f"{dataset.name} · generated with {model.display_name}",
        workspace_id=conversation.workspace_id,
        created_by=user.id,
        content=report_content,
    )
    db.add(report)
    await audit(
        db, user, "report.generate", "report",
        details={"conversation_id": conversation.id, "run_id": message_data["run_id"],
                 "model_id": model.id},
    )
    await db.commit()
    await db.refresh(report)
    return {
        "id": report.id,
        "title": report.title,
        "summary": summary,
        "model": report_content["model"],
        "source_message_id": message.id,
        "created_at": report.created_at.isoformat(),
    }


@app.get("/api/v1/reports/{report_id}/export")
async def export_report(
    report_id: str,
    format: str = Query("markdown", pattern="^(markdown|pdf|csv)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = (await db.execute(select(Report).where(Report.id == report_id))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    workspace = (await db.execute(select(Workspace).where(Workspace.id == report.workspace_id))).scalar_one_or_none()
    if not workspace or workspace.organization_id != user.organization_id:
        raise HTTPException(status_code=403, detail="Report is outside your organization")
    export_dir = Path(settings.UPLOAD_DIR)
    export_dir.mkdir(parents=True, exist_ok=True)
    content = report.content or {}
    if format == "markdown":
        md = f"# {report.title}\n\n"
        if report.description:
            md += f"{report.description}\n\n"
        md += "## Executive Summary\n\n"
        md += str(content.get("summary", "No summary provided")) + "\n\n"
        if content.get("sql"):
            md += f"## Query\n\n```sql\n{content['sql']}\n```\n\n"
        if content.get("outliers"):
            md += "## Statistical outliers (IQR)\n\n"
            for item in content["outliers"]:
                md += (
                    f"- **{item['column']}**: {item['count']} outlier(s); "
                    f"bounds {item['lower_bound']:.3g}–{item['upper_bound']:.3g}; "
                    f"examples: {', '.join(map(str, item['examples']))}\n"
                )
            md += "\n"
        if content.get("rows"):
            rows = content["rows"]
            headers = list(rows[0])
            md += "## Analysis results\n\n"
            md += "| " + " | ".join(headers) + " |\n"
            md += "| " + " | ".join("---" for _ in headers) + " |\n"
            for row in rows[:100]:
                md += "| " + " | ".join(str(row.get(key, "")) for key in headers) + " |\n"
        path = export_dir / f"{report.id}.md"
        path.write_text(md, encoding="utf-8")
        return FileResponse(path, media_type="text/markdown",
                            filename=f"{report.title}.md")
    if format == "pdf":
        from reportlab.graphics.charts.barcharts import VerticalBarChart
        from reportlab.graphics.charts.lineplots import LinePlot, ScatterPlot
        from reportlab.graphics.shapes import Drawing, String
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from xml.sax.saxutils import escape

        buffer = io.BytesIO()
        document = SimpleDocTemplate(buffer, pagesize=letter, title=report.title)
        styles = getSampleStyleSheet()
        story = [
            Paragraph(escape(report.title), styles["Title"]),
            Spacer(1, 0.15 * inch),
        ]
        if report.description:
            story.extend([Paragraph(escape(report.description), styles["Normal"]), Spacer(1, 0.1 * inch)])
        story.extend([
            Paragraph("Executive Summary", styles["Heading2"]),
            Paragraph(escape(str(content.get("summary", "No summary provided"))), styles["BodyText"]),
        ])
        if content.get("sql"):
            story.extend([
                Spacer(1, 0.15 * inch),
                Paragraph("Validated SQL", styles["Heading2"]),
                Paragraph(escape(str(content["sql"])).replace("\n", "<br/>"), styles["Code"]),
            ])
        if content.get("outliers"):
            story.extend([Spacer(1, 0.15 * inch), Paragraph("Statistical outliers (IQR)", styles["Heading2"])])
            for item in content["outliers"]:
                story.append(Paragraph(
                    escape(
                        f"{item['column']}: {item['count']} outlier(s), bounds "
                        f"{item['lower_bound']:.3g}–{item['upper_bound']:.3g}; "
                        f"examples: {', '.join(map(str, item['examples']))}"
                    ),
                    styles["BodyText"],
                ))
        chart_data = content.get("chart")
        if chart_data and chart_data.get("data"):
            points = chart_data["data"][:100]
            drawing = Drawing(500, 250)
            drawing.add(String(
                250, 228,
                f"{chart_data.get('y_key', 'Value')} by {chart_data.get('x_key', 'Category')}",
                textAnchor="middle",
                fontName="Helvetica-Bold",
                fontSize=10,
            ))
            if chart_data["type"] == "bar":
                values = [float(point["y"] or 0) for point in points]
                chart = VerticalBarChart()
                chart.x, chart.y, chart.width, chart.height = 48, 34, 430, 175
                chart.data = [values]
                chart.categoryAxis.categoryNames = [str(point["x"])[:18] for point in points]
                chart.categoryAxis.labels.angle = 25
                chart.categoryAxis.labels.dy = -8
                chart.valueAxis.valueMin = min(0, min(values, default=0))
                chart.valueAxis.valueMax = max(values, default=1) * 1.1 or 1
                chart.valueAxis.valueStep = max(1, chart.valueAxis.valueMax / 5)
                chart.bars[0].fillColor = colors.HexColor("#315efb")
                drawing.add(chart)
            elif chart_data["type"] in {"line", "scatter"}:
                plot = LinePlot() if chart_data["type"] == "line" else ScatterPlot()
                plot.x, plot.y, plot.width, plot.height = 48, 34, 430, 175
                if chart_data["type"] == "line":
                    plot.data = [[(index, float(point["y"] or 0)) for index, point in enumerate(points)]]
                    plot.xValueAxis.valueMin = 0
                    plot.xValueAxis.valueMax = max(1, len(points) - 1)
                    plot.xValueAxis.valueStep = max(1, len(points) // 6)
                else:
                    plot.data = [[(float(point["x"]), float(point["y"])) for point in points]]
                y_values = [float(point["y"] or 0) for point in points]
                plot.yValueAxis.valueMin = min(0, min(y_values, default=0))
                plot.yValueAxis.valueMax = max(y_values, default=1) * 1.1 or 1
                plot.yValueAxis.valueStep = max(1, plot.yValueAxis.valueMax / 5)
                plot.lines[0].strokeColor = colors.HexColor("#315efb")
                drawing.add(plot)
            story.extend([
                Spacer(1, 0.15 * inch),
                Paragraph("Visualization", styles["Heading2"]),
                drawing,
            ])
        if content.get("rows"):
            rows = content["rows"][:50]
            headers = list(rows[0])
            table_data = [[escape(str(key)) for key in headers]]
            table_data.extend([[escape(str(row.get(key, ""))) for key in headers] for row in rows])
            table = Table(table_data, repeatRows=1)
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#315efb")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#dce2ed")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            story.extend([Spacer(1, 0.2 * inch), Paragraph("Analysis results", styles["Heading2"]), table])
        document.build(story)
        buffer.seek(0)
        safe_title = "".join(
            character for character in report.title
            if character.isascii() and (character.isalnum() or character in " ._-")
        ).strip().replace(" ", "_") or "report"
        return StreamingResponse(
            buffer,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_title}.pdf"'},
        )
    path = export_dir / f"{report.id}.csv"
    rows = content.get("rows", [])
    with path.open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    return FileResponse(path, media_type="text/csv", filename=f"{report.title}.csv")


@app.get("/api/v1/models")
async def list_models(_current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    permissions = await get_user_permissions(_current_user, db)
    if not _current_user.is_superuser and "model:view" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: model:view")
    result = await db.execute(
        select(AIModel, AIProvider)
        .join(AIProvider, AIModel.provider_id == AIProvider.id)
        .where(AIModel.is_active.is_(True), AIProvider.is_active.is_(True))
        .order_by(AIProvider.display_name, AIModel.display_name)
    )
    output = []
    for model, provider in result.all():
        output.append({"id": model.id, "name": model.name, "display_name": model.display_name,
                       "provider": provider.display_name,
                       "configured": provider_is_configured(provider.name),
                       "context_window": model.context_window,
                       "input_price_per_1k": model.input_price_per_1k,
                       "output_price_per_1k": model.output_price_per_1k,
                       "capabilities": model.capabilities})
    return output


@app.get("/api/v1/finops/summary")
async def finops_summary(
    workspace_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "finops:view" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: finops:view")
    result = await db.execute(
        select(UsageLedger).join(Workspace, UsageLedger.workspace_id == Workspace.id)
        .where(Workspace.organization_id == user.organization_id)
    )
    records = result.scalars().all()
    if workspace_id:
        records = [r for r in records if r.workspace_id == workspace_id]
    total_tokens = sum(r.input_tokens + r.output_tokens for r in records)
    total_cost = sum(r.cost for r in records)
    by_model: dict[str, dict[str, Any]] = {}
    for record in records:
        model = (await db.execute(select(AIModel).where(AIModel.id == record.model_id))).scalar_one_or_none()
        name = model.display_name if model else "Unknown"
        item = by_model.setdefault(name, {"cost": 0.0, "tokens": 0})
        item["cost"] += record.cost
        item["tokens"] += record.input_tokens + record.output_tokens
    return {"total_cost": round(total_cost, 6), "total_tokens": total_tokens,
            "run_count": len({r.run_id for r in records if r.run_id}),
            "by_model": [{"model": k, **v} for k, v in by_model.items()]}


@app.get("/api/v1/admin/users")
async def admin_users(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and "admin:users" not in permissions:
        raise HTTPException(status_code=403, detail="Permission denied: admin:users")
    result = await db.execute(select(User).where(User.organization_id == user.organization_id))
    users = result.scalars().all()
    output = []
    for managed_user in users:
        role_rows = await db.execute(
            select(Role.name).join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == managed_user.id)
        )
        output.append({
            "id": managed_user.id,
            "email": managed_user.email,
            "full_name": managed_user.full_name,
            "is_active": managed_user.is_active,
            "is_superuser": managed_user.is_superuser,
            "roles": list(role_rows.scalars().all()),
        })
    return output


@app.put("/api/v1/admin/users/{user_id}/role")
async def assign_user_role(
    user_id: str,
    payload: RoleAssignmentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    permissions = await get_user_permissions(user, db)
    if not user.is_superuser and (
        "admin:users" not in permissions or "admin:roles" not in permissions
    ):
        raise HTTPException(status_code=403, detail="Permission denied: admin:users and admin:roles")
    target_user = (await db.execute(
        select(User).where(
            User.id == user_id,
            User.organization_id == user.organization_id,
        )
    )).scalar_one_or_none()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found in your organization")
    role = (await db.execute(select(Role).where(Role.id == payload.role_id))).scalar_one_or_none()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")
    if role.name in {"Super Administrator", "Administrator"} and not user.is_superuser:
        raise HTTPException(status_code=403, detail="Only a superuser can assign an Administrator role")
    existing_assignment = (await db.execute(
        select(UserRole).where(UserRole.user_id == target_user.id)
    )).scalars().all()
    for assignment in existing_assignment:
        await db.delete(assignment)
    db.add(UserRole(user_id=target_user.id, role_id=role.id))
    await audit(
        db, user, "admin.user_role.assign", "user", target_user.id,
        {"role_id": role.id, "role_name": role.name},
    )
    await db.commit()
    return {"user_id": target_user.id, "role_id": role.id, "role_name": role.name}


@app.get("/api/v1/admin/roles")
async def admin_roles(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.is_superuser:
        permissions = await get_user_permissions(user, db)
        if "admin:roles" not in permissions:
            raise HTTPException(status_code=403, detail="Permission denied: admin:roles")
    result = await db.execute(select(Role))
    roles = result.scalars().all()
    return [{"id": r.id, "name": r.name, "description": r.description,
             "is_system_role": r.is_system_role} for r in roles]


@app.get("/api/v1/audit")
async def audit_list(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.is_superuser:
        permissions = await get_user_permissions(user, db)
        if "admin:audit" not in permissions:
            raise HTTPException(status_code=403, detail="Permission denied: admin:audit")
    result = await db.execute(
        select(AuditLog).join(User, AuditLog.user_id == User.id)
        .where(User.organization_id == user.organization_id)
        .order_by(AuditLog.created_at.desc()).limit(200)
    )
    logs = result.scalars().all()
    return [{"id": l.id, "action": l.action, "resource_type": l.resource_type,
             "resource_id": l.resource_id, "details": l.details,
             "created_at": l.created_at.isoformat()} for l in logs]


@app.get("/api/v1/overview")
async def overview(
    workspace_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ds = await db.execute(
        select(Dataset).join(Workspace, Dataset.workspace_id == Workspace.id)
        .where(Workspace.organization_id == user.organization_id)
    )
    datasets = ds.scalars().all()
    runs = await db.execute(
        select(AnalyticsRun).join(Workspace, AnalyticsRun.workspace_id == Workspace.id)
        .where(Workspace.organization_id == user.organization_id)
    )
    run_rows = runs.scalars().all()
    reports = await db.execute(
        select(Report).join(Workspace, Report.workspace_id == Workspace.id)
        .where(Workspace.organization_id == user.organization_id)
    )
    report_rows = reports.scalars().all()
    if workspace_id:
        datasets = [d for d in datasets if d.workspace_id == workspace_id]
        run_rows = [r for r in run_rows if r.workspace_id == workspace_id]
        report_rows = [r for r in report_rows if r.workspace_id == workspace_id]
    today = datetime.now(timezone.utc).date()
    days = [(today - timedelta(days=offset)).isoformat() for offset in range(6, -1, -1)]
    activity_counts = {day: 0 for day in days}
    for run in run_rows:
        day = run.created_at.date().isoformat()
        if day in activity_counts:
            activity_counts[day] += 1
    return {"dataset_count": len(datasets), "row_count": sum(d.row_count or 0 for d in datasets),
            "run_count": len(run_rows), "report_count": len(report_rows),
            "completed_runs": len([r for r in run_rows if r.status == "completed"]),
            "failed_runs": len([r for r in run_rows if r.status == "failed"]),
            "activity": [{"date": day, "runs": activity_counts[day]} for day in days]}

