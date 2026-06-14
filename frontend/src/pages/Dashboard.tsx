import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { fetchWatchlist, scanWatchlist } from '../api/watchlist';
import Card from '../components/ui/Card';
import Button from '../components/ui/Button';
import Badge from '../components/ui/Badge';

export default function Dashboard() {
  const navigate = useNavigate();
  const [searchCode, setSearchCode] = useState('');

  const { data: watchlist } = useQuery({
    queryKey: ['watchlist'],
    queryFn: fetchWatchlist,
  });

  const { data: scanResult, isLoading: scanning, refetch: doScan } = useQuery({
    queryKey: ['dashboard-scan'],
    queryFn: scanWatchlist,
    enabled: false,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const code = searchCode.trim().toUpperCase();
    if (!code) return;
    let tsCode = code;
    if (/^\d{6}$/.test(tsCode)) {
      tsCode = tsCode.startsWith('6') ? `${tsCode}.SH` : `${tsCode}.SZ`;
    }
    navigate(`/stock/${tsCode}`);
  };

  return (
    <div className="space-y-6">
      {/* Hero Search */}
      <div className="flex flex-col items-center justify-center py-12">
        <h1 className="text-2xl font-bold text-text-primary mb-2">Z哥量化</h1>
        <p className="text-sm text-text-muted mb-6">量化交易分析工具</p>
        <form onSubmit={handleSearch} className="flex items-center gap-3">
          <input
            type="text"
            value={searchCode}
            onChange={(e) => setSearchCode(e.target.value)}
            placeholder="输入股票代码开始分析，如 600487"
            className="w-96 rounded-lg border border-border bg-bg-secondary px-4 py-3 text-sm text-text-primary placeholder-text-muted outline-none focus:border-accent-gold transition-colors"
          />
          <button
            type="submit"
            className="rounded-lg bg-accent-gold/20 px-6 py-3 text-sm font-medium text-accent-gold hover:bg-accent-gold/30 transition-colors"
          >
            分析
          </button>
        </form>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card>
          <div className="text-center">
            <div className="text-xs text-text-muted">自选股</div>
            <div className="text-2xl font-bold text-accent-gold mt-1">{watchlist?.count || 0}</div>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <div className="text-xs text-text-muted">B1 信号</div>
            <div className="text-2xl font-bold text-accent-green mt-1">{scanResult?.b1_count || 0}</div>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <div className="text-xs text-text-muted">逃顶预警</div>
            <div className="text-2xl font-bold text-accent-red mt-1">{scanResult?.exit_count || 0}</div>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <div className="text-xs text-text-muted">异动</div>
            <div className="text-2xl font-bold text-accent-blue mt-1">{scanResult?.abnormal_count || 0}</div>
          </div>
        </Card>
      </div>

      {/* Watchlist Signals */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-bold text-text-primary">自选股信号</h2>
        <Button size="sm" onClick={() => doScan()} disabled={scanning}>
          {scanning ? '扫描中...' : '扫描信号'}
        </Button>
      </div>

      {scanResult && scanResult.alerts.length > 0 && (
        <div className="space-y-2">
          {scanResult.alerts.slice(0, 10).map((a, i) => (
            <div
              key={i}
              className="flex items-center gap-3 p-3 rounded-lg border border-border bg-bg-card hover:bg-bg-hover/50 cursor-pointer transition-colors"
              onClick={() => navigate(`/stock/${a.ts_code}`)}
            >
              <Badge variant={a.level === 'CRITICAL' ? 'danger' : a.level === 'WARNING' ? 'warning' : 'info'}>
                {a.level}
              </Badge>
              <span className="font-mono text-sm text-accent-gold">{a.ts_code}</span>
              <span className="text-sm text-text-secondary">{a.alert_type}</span>
              <span className="text-xs text-text-muted flex-1">{a.message}</span>
            </div>
          ))}
        </div>
      )}

      {scanResult && scanResult.alerts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-10 text-text-muted border border-dashed border-border/40 rounded-lg">
          <div className="text-2xl mb-2 opacity-60">✓</div>
          <div className="text-sm">暂无信号 — 自选股平稳运行中</div>
          <div className="text-xs mt-1 text-text-muted/70">有新信号时会在此处出现</div>
        </div>
      )}

      {!scanResult && (
        <div className="grid grid-cols-3 gap-3">
          {[
            { icon: '◎', title: '选股筛选', desc: 'B1 / B2 / B3 等 12 种战法', path: '/screen' },
            { icon: '★', title: '加入自选', desc: '把感兴趣的票放进观察池', path: '/watchlist' },
            { icon: '⟲', title: '策略回测', desc: '用少妇战法验证历史收益', path: '/backtest' },
          ].map((item) => (
            <button
              key={item.path}
              onClick={() => navigate(item.path)}
              className="text-left rounded-xl border border-border/40 bg-bg-card/60 p-4 hover:border-accent-gold/40 hover:bg-bg-hover/40 transition-all"
            >
              <div className="text-xl text-accent-gold mb-1">{item.icon}</div>
              <div className="text-sm font-bold text-text-primary">{item.title}</div>
              <div className="text-xs text-text-muted mt-1">{item.desc}</div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
