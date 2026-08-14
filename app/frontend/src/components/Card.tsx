export function Card({ children, title, actions, className = '' }: { children: React.ReactNode; title?: React.ReactNode; actions?: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-[#11131a] border border-gray-800 rounded-xl p-5 ${className}`}>
      {(title || actions) && (
        <div className="flex items-center justify-between mb-4">
          {title && <h3 className="text-sm font-medium text-gray-200">{title}</h3>}
          {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
}

export function Badge({ action }: { action: 'BUY' | 'SELL' | 'HOLD' }) {
  const styles = {
    BUY: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
    SELL: 'bg-rose-500/10 text-rose-400 border-rose-500/20',
    HOLD: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  };
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold border ${styles[action]}`}>
      {action}
    </span>
  );
}
