import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# ----------------------------
# CONFIG (adjust if needed)
# ----------------------------
N_PROJECTS = 10
N_DAYS = 365
N_ACTIVITIES_PER_PROJECT = 50   # "Many activities" per project
START_DATE = "2025-01-01"

SEED = 42
np.random.seed(SEED)

# Thresholds used to shape trends (not for classification here)
BASELINE_DURATION_DAYS = 540  # ~18 months baseline
DEFAULT_SCOPE_QTY = 1000.0    # arbitrary scope qty per project
DEFAULT_ROW_FINAL = 0.95      # target ROW availability at end (95%)

# ----------------------------
# Helper functions
# ----------------------------
def clamp(x, lo, hi):
    return max(lo, min(hi, x))

def sigmoid(x):
    return 1 / (1 + np.exp(-x))

# ----------------------------
# Build Projects + Activities
# ----------------------------
start_dt = pd.to_datetime(START_DATE)
dates = pd.date_range(start_dt, periods=N_DAYS, freq="D")

projects = []
for p in range(1, N_PROJECTS + 1):
    project_id = f"PRJ{p:03d}"
    project_name = f"Project_{p:02d}"
    # planned finish: baseline duration from start
    planned_finish = start_dt + pd.Timedelta(days=BASELINE_DURATION_DAYS + np.random.randint(-30, 31))
    # base risk profile (0..1): higher => more likely delays / float erosion
    risk = clamp(np.random.normal(0.45, 0.18), 0.10, 0.85)

    # create activities with different planned windows and budgets
    activities = []
    for a in range(1, N_ACTIVITIES_PER_PROJECT + 1):
        activity_id = f"{project_id}-ACT{a:04d}"
        activity_name = f"Activity_{a:04d}"

        # Activity planned start somewhere within first 60% of baseline duration
        act_start_offset = int(clamp(np.random.normal(0.25, 0.15), 0.0, 0.60) * BASELINE_DURATION_DAYS)
        act_duration = int(clamp(np.random.normal(45, 20), 10, 120))

        planned_start = start_dt + pd.Timedelta(days=act_start_offset)
        planned_finish_act = planned_start + pd.Timedelta(days=act_duration)

        # Budget/Planned Value weight for activity (sums to project PV profile)
        budget_value = max(50_000, np.random.lognormal(mean=11, sigma=0.35))  # ~ large-ish values

        # Critical flag ~ 25% activities, slightly higher if risk high
        crit_prob = clamp(0.20 + 0.20 * risk, 0.20, 0.45)
        is_critical = np.random.rand() < crit_prob

        activities.append({
            "activity_id": activity_id,
            "activity_name": activity_name,
            "planned_start_date": planned_start.date(),
            "planned_finish_activity_date": planned_finish_act.date(),
            "activity_budget_value": float(budget_value),
            "is_critical_flag": int(is_critical)
        })

    projects.append({
        "project_id": project_id,
        "project_name": project_name,
        "planned_finish_date": planned_finish.date(),
        "risk_profile": float(risk),
        "total_scope_qty": float(DEFAULT_SCOPE_QTY),
        "activities": activities
    })

# ----------------------------
# Generate Daily Activity-level rows
# ----------------------------
rows = []

for proj in projects:
    pid = proj["project_id"]
    pname = proj["project_name"]
    planned_finish_date = pd.to_datetime(proj["planned_finish_date"])
    risk = proj["risk_profile"]
    total_scope_qty = proj["total_scope_qty"]

    # ROW availability trend: improves over time, but slower for higher risk projects
    # starts around 50-70%, ends around 85-98%
    row_start = clamp(np.random.normal(0.60, 0.08), 0.45, 0.75)
    row_end = clamp(DEFAULT_ROW_FINAL - 0.10 * risk + np.random.normal(0, 0.03), 0.75, 0.98)

    # simulate project-level "forecast finish date" drift: riskier projects drift more
    # base drift over the year: -10 to +120 days
    forecast_drift_end = int(clamp(np.random.normal(30 + 90 * risk, 25), -10, 140))

    # base CPI & Billing Readiness proxies (for PEI computation)
    # (SRA status uses PEI as context; we provide it to support the intent)
    cpi_base = clamp(np.random.normal(0.98 - 0.10 * risk, 0.04), 0.75, 1.05)
    bill_ready_base = clamp(np.random.normal(0.90 - 0.15 * risk, 0.05), 0.60, 0.98)

    # Precompute activity planned PV distribution profile
    act_df = pd.DataFrame(proj["activities"]).copy()

    # Normalize activity budgets to compute PV contribution
    total_budget = act_df["activity_budget_value"].sum()

    for d in dates:
        day_idx = (d - start_dt).days
        t = day_idx / (N_DAYS - 1)

        # ROW % trend
        row_pct = row_start + (row_end - row_start) * sigmoid((t - 0.35) * 8)
        row_available_qty = total_scope_qty * row_pct

        # Project forecast finish drift grows over time
        drift_days = int(round(forecast_drift_end * sigmoid((t - 0.40) * 6)))
        forecast_finish_date = planned_finish_date + pd.Timedelta(days=drift_days)

        # For each activity, compute PV & EV for the day
        for _, act in act_df.iterrows():
            astart = pd.to_datetime(act["planned_start_date"])
            afin = pd.to_datetime(act["planned_finish_activity_date"])
            budget = act["activity_budget_value"]
            is_crit = int(act["is_critical_flag"])

            # planned daily PV: distribute budget evenly across planned duration (only within window)
            if astart <= d <= afin:
                duration = max((afin - astart).days + 1, 1)
                pv_day = budget / duration
            else:
                pv_day = 0.0

            # earned value EV: lags PV depending on risk; sometimes catches up late
            # use a lag factor that increases with risk, plus noise
            lag = clamp(np.random.normal(0.03 + 0.18 * risk, 0.03), 0.0, 0.35)
            # if critical, lag impact slightly higher
            if is_crit:
                lag = clamp(lag + 0.03, 0.0, 0.45)

            # if within planned window, EV is PV * (1 - lag) with some volatility
            if pv_day > 0:
                ev_day = pv_day * clamp(np.random.normal(1.0 - lag, 0.10), 0.0, 1.25)
            else:
                # outside planned window: small chance of late EV if lagging project
                late_work_prob = clamp(0.02 + 0.10 * risk, 0.02, 0.20)
                ev_day = (budget / 60) * (np.random.rand() < late_work_prob) * clamp(np.random.normal(0.6, 0.3), 0.0, 1.2)

            # executed quantity: proportional to EV vs budget (rough synthetic relation)
            executed_qty = (ev_day / max(budget, 1.0)) * 5.0  # scaled tiny per activity/day

            # float: degrades over time and with risk; critical activities have lower float
            base_float = clamp(np.random.normal(12 - 8 * risk, 3), 0.0, 25.0)
            if is_crit:
                base_float = clamp(base_float - 6, 0.0, 15.0)
            # degrade with time + randomness
            total_float_days = clamp(base_float - (t * (6 + 10 * risk)) + np.random.normal(0, 1.2), 0.0, 30.0)

            rows.append({
                "date": d.date(),
                "project_id": pid,
                "project_name": pname,

                # Activity identifiers
                "activity_id": act["activity_id"],
                "activity_name": act["activity_name"],
                "is_critical_flag": is_crit,

                # Schedule planned dates (project + activity)
                "planned_finish_date": planned_finish_date.date(),
                "forecast_finish_date": forecast_finish_date.date(),
                "planned_start_date": act["planned_start_date"],
                "planned_finish_activity_date": act["planned_finish_activity_date"],

                # Core value fields for SPI computation (aggregate later at project-day)
                "planned_value_amount": float(pv_day),
                "earned_value_amount": float(ev_day),

                # Workfront / scope fields
                "total_scope_qty": float(total_scope_qty),
                "row_available_qty": float(row_available_qty),

                # Progress proxy
                "executed_qty": float(executed_qty),

                # Float fields
                "total_float_days": float(total_float_days),

                # Optional context fields (helps PEI snapshot)
                "cpi_value": float(cpi_base + np.random.normal(0, 0.01)),
                "billing_readiness_pct": float(clamp(bill_ready_base + np.random.normal(0, 0.01), 0.50, 0.99)),
                "risk_profile": float(risk)
            })

df = pd.DataFrame(rows)

# Compute daily project-level SPI and PEI and attach to each row (so SRA_Status_PEI can read directly)
proj_day = df.groupby(["date", "project_id"], as_index=False).agg(
    earned_value_amount_sum=("earned_value_amount", "sum"),
    planned_value_amount_sum=("planned_value_amount", "sum"),
    avg_float=("total_float_days", "mean"),
    row_available_qty=("row_available_qty", "first"),
    total_scope_qty=("total_scope_qty", "first"),
    planned_finish_date=("planned_finish_date", "first"),
    forecast_finish_date=("forecast_finish_date", "first"),
    cpi_value=("cpi_value", "mean"),
    billing_readiness_pct=("billing_readiness_pct", "mean")
)

proj_day["spi_value"] = proj_day["earned_value_amount_sum"] / proj_day["planned_value_amount_sum"].replace(0, np.nan)
proj_day["workfront_readiness_pct"] = (proj_day["row_available_qty"] / proj_day["total_scope_qty"]) * 100.0
proj_day["forecast_delay_days"] = (pd.to_datetime(proj_day["forecast_finish_date"]) - pd.to_datetime(proj_day["planned_finish_date"])).dt.days

# PEI = 0.4*SPI + 0.3*CPI + 0.3*BillingReadiness
proj_day["pei_value"] = 0.4 * proj_day["spi_value"].fillna(1.0) + 0.3 * proj_day["cpi_value"] + 0.3 * proj_day["billing_readiness_pct"]

# Join back to activity-level
df = df.merge(
    proj_day[["date", "project_id", "spi_value", "pei_value", "forecast_delay_days", "workfront_readiness_pct", "avg_float"]],
    on=["date", "project_id"],
    how="left"
)

# Save
out_path = "sra_status_pei_activity_level_10projects_365days.csv"
df.to_csv(out_path, index=False)

print(f"Created: {out_path}")
print(f"Rows: {len(df):,} | Columns: {len(df.columns)}")