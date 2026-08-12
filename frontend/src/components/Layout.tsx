import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, ScanLine, Radio, Wallet as WalletIcon, Bot, Cpu, LineChart, Settings } from 'lucide-react';
import { useWallet } from '../context/WalletContext';

const nav = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/scanner', label: 'Scanner', icon: ScanLine },
  { path: '/strategies', label: 'Strategies', icon: Cpu },
  { path: '/backtest', label: 'Backtest', icon: LineChart },
  { path: '/signals', label: 'Signals', icon: Radio },
  { path: '/positions', label: 'Positions', icon: WalletIcon },
  { path: '/wallets', label: 'Wallets', icon: Settings },
];

function mask(address: string) {
  if (address.length <= 12) return address;
  return `${address.slice(0, 4)}...${address.slice(-4)}`;
}

export function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { wallets, selectedWallet, setSelectedWallet, loading } = useWallet();

  return (
    <div className="flex h-screen bg-[#0b0d12] text-gray-100">
      <aside className="w-64 border-r border-gray-800 p-4 flex flex-col">
        <div className="flex items-center gap-2 px-2 mb-8">
          <Bot className="w-7 h-7 text-violet-400" />
          <span className="font-semibold text-lg tracking-tight">HL Agents</span>
        </div>
        <nav className="space-y-1">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.path;
            return (
              <Link
                key={item.path}
                to={item.path}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? 'bg-violet-500/10 text-violet-300 border border-violet-500/20'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/50'
                }`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-auto space-y-3 pt-4 border-t border-gray-800">
          <div className="px-2">
            <label className="block text-[10px] font-medium uppercase tracking-wider text-gray-500 mb-1">Active Wallet</label>
            {loading ? (
              <span className="text-xs text-gray-500">Loading...</span>
            ) : wallets.length === 0 ? (
              <Link to="/wallets" className="text-xs text-violet-400 hover:text-violet-300">Add wallet</Link>
            ) : (
              <select
                value={selectedWallet?.id || ''}
                onChange={(e) => {
                  const wallet = wallets.find((w) => w.id === e.target.value) || null;
                  setSelectedWallet(wallet);
                }}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-2 py-1.5 text-xs text-gray-200 focus:outline-none focus:border-violet-500"
              >
                {wallets.map((w) => (
                  <option key={w.id} value={w.id}>
                    {w.name} ({mask(w.address)})
                  </option>
                ))}
              </select>
            )}
          </div>
          <div className="px-3 py-2 text-xs text-gray-500">
            <p className="font-medium text-gray-300">Paper Mode</p>
            <p className="mt-1">No real orders sent.</p>
          </div>
        </div>
      </aside>
      <main className="flex-1 overflow-auto p-6">{children}</main>
    </div>
  );
}
