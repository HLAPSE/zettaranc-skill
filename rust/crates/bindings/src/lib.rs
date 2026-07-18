//! PyO3 绑定 crate，编译成 `_core_compute` 原生扩展。
//!
//! 包含：smoke 测试 + 高层 API（compute_atr / 单策略回测）+ 错误映射。
#![forbid(unsafe_code)]

mod backtest_bindings;
mod error;

use pyo3::prelude::*;
use zt_core_types::KLine;
use zt_indicators;

/// 测试函数：证明 Rust 编译产物可以被 Python 调用。
#[pyfunction]
fn rust_smoke() -> &'static str {
    "ok from rust"
}

/// 抛出一个 ValueError（验证错误映射）。
#[pyfunction]
fn raise_value_error() -> PyResult<()> {
    Err(error::core_error_to_pyerr(
        zt_core_types::CoreError::InvalidKLine("test".to_string()),
    ))
}

/// 抛出一个 KeyError。
#[pyfunction]
fn raise_key_error() -> PyResult<()> {
    Err(error::core_error_to_pyerr(
        zt_core_types::CoreError::MissingColumn("ts_code".to_string()),
    ))
}

/// 高层 API：从 Python 接收 list[dict]，返回 list[float]。
#[pyfunction]
#[pyo3(signature = (klines, window=14))]
fn compute_atr_py(klines: Vec<Bound<'_, pyo3::PyAny>>, window: usize) -> PyResult<Vec<f64>> {
    let series = parse_klines(&klines)?;
    zt_indicators::compute_atr(&series, window).map_err(error::core_error_to_pyerr)
}

/// 把 Python list[dict] 转成 Rust KLineSeries。
fn parse_klines(items: &[Bound<'_, pyo3::PyAny>]) -> PyResult<zt_core_types::KLineSeries> {
    use pyo3::types::PyDict;
    let mut out = Vec::with_capacity(items.len());
    for item in items {
        let d = item.downcast::<PyDict>()?;
        let get_f64 = |k: &str| -> PyResult<f64> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
                .extract::<f64>()
        };
        let get_i32 = |k: &str| -> PyResult<i32> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
                .extract::<i32>()
        };
        let get_str = |k: &str| -> PyResult<String> {
            d.get_item(k)?
                .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(k.to_string()))?
                .extract::<String>()
        };
        let get_opt_f64 = |k: &str| -> PyResult<Option<f64>> {
            Ok(d.get_item(k)?
                .and_then(|v| if v.is_none() { None } else { Some(v) })
                .map(|v| v.extract::<f64>())
                .transpose()?)
        };
        let get_opt_bool = |k: &str| -> PyResult<Option<bool>> {
            Ok(d.get_item(k)?
                .and_then(|v| if v.is_none() { None } else { Some(v) })
                .map(|v| v.extract::<bool>())
                .transpose()?)
        };

        out.push(KLine {
            ts_code: get_str("ts_code")?,
            trade_date: get_i32("trade_date")?,
            open: get_f64("open")?,
            high: get_f64("high")?,
            low: get_f64("low")?,
            close: get_f64("close")?,
            vol: get_f64("vol")?,
            amount: get_f64("amount")?,
            pct_chg: get_f64("pct_chg")?,
            vol_ratio: get_opt_f64("vol_ratio")?,
            is_limit_up: get_opt_bool("is_limit_up")?,
            is_limit_down: get_opt_bool("is_limit_down")?,
        });
    }
    Ok(zt_core_types::KLineSeries { items: out })
}

#[pymodule]
fn _core_compute(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add_function(wrap_pyfunction!(rust_smoke, m)?)?;
    m.add_function(wrap_pyfunction!(raise_value_error, m)?)?;
    m.add_function(wrap_pyfunction!(raise_key_error, m)?)?;
    m.add_function(wrap_pyfunction!(compute_atr_py, m)?)?;
    m.add_function(wrap_pyfunction!(
        backtest_bindings::run_single_strategy_backtest_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(
        backtest_bindings::run_portfolio_backtest_py,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(backtest_bindings::run_grid_search_py, m)?)?;
    Ok(())
}