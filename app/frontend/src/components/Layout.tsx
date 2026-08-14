import { useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, ScanLine, Radio, Wallet as WalletIcon, Bot, Cpu, LineChart, Settings, Bell, BookOpen, Menu, X } from 'lucide-react';
import { useWallet } from '../context/useWallet';
import { fetchUnreadAlertCount } from '../services/api';

const nav = [
  { path: '/', label: 'Dashboard', icon: LayoutDashboard },
  { path: '/scanner', label: 'Scanner', icon: ScanLine },
  { path: '/strategies', label: 'Strategies', icon: Cpu },
  { path: '/backtest', label: 'Backtest', icon: LineChart },
  { path: '/signals', label: 'Signals', icon: Radio },
  { path: '/positions', label: 'Positions', icon: WalletIcon },
  { path: '/alerts', label: 'Alerts', icon: Bell },
  { path: '/journal', label: 'Journal', icon: BookOpen },
  { path: '/wallets', label: 'Wallets', icon: Settings },
];

function mask(address: string) {
  if (address.length <= 12) return address;
  return `${address.slice(0, 4)}...${address.slice(-4)}`;
}

function isActive(path: string, pathname: string) {
  if (path === '/') return pathname === '/';
  return pathname.startsWith(path);
}

export function Layout({ children }: { children: React.ReactNode }) {
  const { pathname } = useLocation();
  const { wallets, selectedWallet, setSelectedWallet, loading } = useWallet();
  const [unreadCount, setUnreadCount] = useState(0);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  useEffect(() => {
    fetchUnreadAlertCount(selectedWallet?.id).then(setUnreadCount).catch(() => 0);
    const interval = setInterval(() => {
      fetchUnreadAlertCount(selectedWallet?.id).then(setUnreadCount).catch(() => 0);
    }, 30000);
    return () => clearInterval(interval);
  }, [selectedWallet]);

  useEffect(() => {
    setSidebarOpen(false);
  }, [pathname]);

  return (
    <div className="flex h-screen bg-[#0b0d12] text-gray-100">
      <aside
        className={`fixed inset-y-0 left-0 z-40 w-64 border-r border-gray-800 bg-[#0b0d12] p-4 flex flex-col transition-transform duration-200 md:translate-x-0 md:static ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
      >
        <div className="flex items-center gap-2 px-2 mb-8">
          <Bot className="w-7 h-7 text-violet-400" />
          <span className="font-semibold text-lg tracking-tight">HL Agents</span>
        </div>
        <nav className="space-y-1">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = isActive(item.path, pathname);
            return (
              <Link
                key={item.path}
                to={item.path}
                onClick={() => setSidebarOpen(false)}
                className={`flex items-center justify-between px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  active
                    ? 'bg-violet-500/10 text-violet-300 border border-violet-500/20'
                    : 'text-gray-400 hover:text-gray-100 hover:bg-gray-800/50'
                }`}
              >
                <span className="flex items-center gap-3">
                  <Icon className="w-4 h-4" />
                  {item.label}
                </span>
                {item.label === 'Alerts' && unreadCount > 0 && (
                  <span className="bg-rose-500 text-white text-[10px] px-1.5 py-0.5 rounded-full">
                    {unreadCount > 99 ? '99+' : unreadCount}
                  </span>
                )}
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

      {sidebarOpen && (
        <button
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
          aria-label="Close sidebar"
        />
      )}

      <main className="flex-1 overflow-auto p-4 sm:p-6 w-full min-w-0">
        <div className="flex items-center gap-3 mb-4 md:hidden">
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg bg-gray-800 text-gray-200"
            aria-label="Open sidebar"
          >
            {sidebarOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>
          <span className="font-semibold">HL Agents</span>
        </div>
        {children}
      </main>
    </div>
  );
}
