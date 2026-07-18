//! 回测引擎 crate（单策略 + 组合）。
#![forbid(unsafe_code)]

pub mod single;

pub use single::{
    run_single_strategy_backtest, SingleStrategyConfig, SingleStrategyResult, Trade,
};