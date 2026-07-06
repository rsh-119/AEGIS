"""
forecast_service.py — multi-algorithm short-horizon price projection.

Three models exposed via `forecast(candles, horizon_days, model)`:

  "holt"    — Holt Double Exponential Smoothing + EWMA vol confidence band
               Best baseline; fully explainable; no feature engineering needed.

  "xgboost" — XGBoost regression on 20+ engineered lag/rolling features.
               Learns non-linear price patterns; generally outperforms Holt
               on back-tests for 1–2 week horizons.

  "lgbm"    — LightGBM (same feature set as XGBoost, leaf-wise tree growth).
               Faster training, often slightly better on noisy/sparse data.

Shared pipeline for tree models:
  • Lag features: close[t-1..t-10]
  • Rolling stats: mean/std over 5/10/20 days
  • Momentum: 5-day and 20-day log-return
  • RSI(14), MACD signal
  • Target: next-N-day log return (multi-step via direct strategy)

Confidence bands: EWMA volatility ×√t (all three models use the same band).

NOT investment advice — educational statistical projection only.
"""

from __future__ import annotations
import numpy as np

# ── EWMA volatility ───────────────────────────────────────────────────────────

def _ewma_vol(log_ret: np.ndarray, span: int = 20) -> float:
    if len(log_ret) < 3:
        return 0.015
    lam = 1 - 2 / (span + 1)
    w = np.array([lam ** i for i in range(len(log_ret))])[::-1]
    w /= w.sum()
    return float(np.sqrt(np.dot(w, log_ret ** 2)))


# ── Feature engineering for tree models ──────────────────────────────────────

def _rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    delta = np.diff(prices)
    gain  = np.where(delta > 0, delta, 0.0)
    loss  = np.where(delta < 0, -delta, 0.0)
    rs    = np.full(len(prices), np.nan)
    if len(gain) < period:
        return rs
    avg_g = np.mean(gain[:period])
    avg_l = np.mean(loss[:period])
    for i in range(period, len(gain)):
        avg_g = (avg_g * (period - 1) + gain[i]) / period
        avg_l = (avg_l * (period - 1) + loss[i]) / period
        if avg_l == 0:
            rs[i + 1] = 100.0
        else:
            rs[i + 1] = 100 - 100 / (1 + avg_g / avg_l)
    return rs


def _build_features(prices: np.ndarray) -> tuple[np.ndarray, list[str]]:
    """Return (X matrix, feature_names) for each timestep that has enough history."""
    n    = len(prices)
    lret = np.concatenate([[0.0], np.diff(np.log(prices))])
    rsi  = _rsi(prices)

    # MACD (12/26 EMA diff)
    ema12 = np.zeros(n); ema26 = np.zeros(n)
    a12, a26 = 2/13, 2/27
    ema12[0] = ema26[0] = prices[0]
    for i in range(1, n):
        ema12[i] = prices[i] * a12 + ema12[i-1] * (1 - a12)
        ema26[i] = prices[i] * a26 + ema26[i-1] * (1 - a26)
    macd = ema12 - ema26

    rows, names = [], []
    min_lookback = 25  # enough for all rolling windows

    names = (
        [f"lag_{k}" for k in range(1, 11)] +
        ["roll_mean5", "roll_std5", "roll_mean10", "roll_std10", "roll_mean20", "roll_std20"] +
        ["mom5", "mom20"] +
        ["rsi14", "macd"] +
        ["log_ret_1", "log_ret_2", "log_ret_3"]
    )

    for i in range(min_lookback, n):
        lags        = [lret[i - k] for k in range(1, 11)]
        rm5, rs5    = np.mean(lret[i-5:i]),  np.std(lret[i-5:i])
        rm10, rs10  = np.mean(lret[i-10:i]), np.std(lret[i-10:i])
        rm20, rs20  = np.mean(lret[i-20:i]), np.std(lret[i-20:i])
        mom5        = float(np.log(prices[i]) - np.log(prices[i-5]))
        mom20       = float(np.log(prices[i]) - np.log(prices[i-20]))
        rsi_v       = rsi[i] if not np.isnan(rsi[i]) else 50.0
        macd_v      = macd[i]
        lr1, lr2, lr3 = lret[i], lret[i-1], lret[i-2]
        rows.append(lags + [rm5,rs5,rm10,rs10,rm20,rs20, mom5,mom20, rsi_v,macd_v, lr1,lr2,lr3])

    X = np.array(rows, dtype=float)
    # Replace any NaN/inf
    X = np.where(np.isfinite(X), X, 0.0)
    return X, names


def _tree_forecast(prices: np.ndarray, horizon: int, model_name: str) -> np.ndarray:
    """
    Direct multi-step forecast: train one model per horizon step.
    Returns array of length `horizon` with projected log-prices.
    """
    import pandas as pd
    X_arr, feat_names = _build_features(prices)
    X = pd.DataFrame(X_arr, columns=feat_names)
    log_p = np.log(prices)
    min_lb = 25

    proj_log = np.zeros(horizon)
    last_log = log_p[-1]
    X_last = X.iloc[[-1]]  # single-row DataFrame for prediction

    for step in range(1, horizon + 1):
        # Target: log return `step` days ahead
        n_samples = len(X) - step
        if n_samples < 30:
            # Not enough samples for this step — use linear extrapolation
            drift = np.mean(np.diff(log_p[-30:]))
            proj_log[step - 1] = last_log + drift * step
            continue

        X_tr = X.iloc[:n_samples]
        y_tr = np.array([
            log_p[min_lb + i + step] - log_p[min_lb + i]
            for i in range(n_samples)
        ])

        if model_name == "xgboost":
            import xgboost as xgb
            mdl = xgb.XGBRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=1.0,
                verbosity=0, n_jobs=2,
            )
        else:  # lgbm
            import lightgbm as lgb
            mdl = lgb.LGBMRegressor(
                n_estimators=200, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                reg_alpha=0.1, reg_lambda=1.0,
                verbose=-1, n_jobs=2,
            )

        mdl.fit(X_tr, y_tr)
        pred_ret = float(mdl.predict(X_last)[0])
        proj_log[step - 1] = last_log + pred_ret

    return proj_log


# ── Holt DES ──────────────────────────────────────────────────────────────────

def _holt_forecast(log_y: np.ndarray, horizon: int) -> np.ndarray:
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing as ES
        mdl = ES(log_y, trend="add", initialization_method="estimated").fit(
            optimized=True, use_brute=False
        )
        return np.asarray(mdl.forecast(horizon))
    except Exception:
        alpha, beta = 0.25, 0.08
        lvl, trd = log_y[0], (log_y[1] - log_y[0]) if len(log_y) > 1 else 0.0
        for v in log_y[1:]:
            prev = lvl
            lvl  = alpha * v + (1 - alpha) * (lvl + trd)
            trd  = beta * (lvl - prev) + (1 - beta) * trd
        return np.array([lvl + trd * (i + 1) for i in range(horizon)])


# ── Public entry point ────────────────────────────────────────────────────────

def forecast(
    candles: list[dict],
    horizon_days: int = 30,
    model: str = "holt",   # "holt" | "xgboost" | "lgbm"
) -> dict:
    closes = [c["close"] for c in candles if c.get("close")]
    min_required = 60 if model == "holt" else 80
    if len(closes) < min_required:
        return {"available": False, "reason": f"Need at least {min_required} trading days of history"}

    # Use up to last 2 years for training
    y     = np.array(closes[-504:], dtype=float)
    log_y = np.log(y)
    log_ret = np.diff(log_y)
    ewma_vol = _ewma_vol(log_ret)

    # ── Run selected model ────────────────────────────────────────
    try:
        if model in ("xgboost", "lgbm"):
            proj_log = _tree_forecast(y, horizon_days, model)
        else:
            # Holt DES already fits its own additive trend component from the
            # same log-price series — a separate hand-crafted momentum drift
            # used to be added on top of that, double-counting the trend and
            # making Holt's forecasts diverge sharply (~2x more extreme) from
            # XGBoost/LightGBM, which get no such extra push. Removed so all
            # three models are driven purely by their own native fit.
            proj_log = _holt_forecast(log_y, horizon_days)
    except Exception as e:
        return {"available": False, "reason": f"Model error: {e}"}

    # ── Confidence band ───────────────────────────────────────────
    z80  = 1.282
    band = np.array([ewma_vol * np.sqrt(i + 1) * z80 for i in range(horizon_days)])
    proj  = np.exp(proj_log)
    upper = np.exp(proj_log + band)
    lower = np.exp(proj_log - band)

    last_price = float(y[-1])

    # ── Milestone prices ──────────────────────────────────────────
    milestones: dict[str, dict] = {}
    for label, days in [("1W", 7), ("2W", 14), ("3W", 21), ("1M", 30)]:
        if days <= horizon_days:
            idx = days - 1
            p = float(proj[idx])
            milestones[label] = {
                "days":       days,
                "price":      round(p, 2),
                "upper":      round(float(upper[idx]), 2),
                "lower":      round(float(lower[idx]), 2),
                "return_pct": round((p - last_price) / last_price * 100, 2),
            }

    points = [
        {
            "day":   i + 1,
            "price": round(float(proj[i]),  2),
            "upper": round(float(upper[i]), 2),
            "lower": round(float(lower[i]), 2),
        }
        for i in range(horizon_days)
    ]

    target = float(proj[-1])
    ret30  = (target - last_price) / last_price * 100
    direction = "up" if ret30 > 1.5 else "down" if ret30 < -1.5 else "flat"
    ann_trend = (float(np.exp(np.mean(log_ret) * 252)) - 1) * 100

    model_labels = {
        "holt":    "Holt DES + EWMA Vol",
        "xgboost": "XGBoost (lag/RSI/MACD features)",
        "lgbm":    "LightGBM (lag/RSI/MACD features)",
    }

    return {
        "available":            True,
        "model":                model,
        "model_label":          model_labels.get(model, model),
        "horizon_days":         horizon_days,
        "last_price":           round(last_price, 2),
        "target_price":         round(target, 2),
        "expected_return_pct":  round(ret30, 2),
        "direction":            direction,
        "daily_vol_pct":        round(ewma_vol * 100, 3),
        "annualised_trend_pct": round(ann_trend, 2),
        "milestones":           milestones,
        "points":               points,
        "disclaimer":           "Statistical projection only. Not investment advice.",
    }
