import { createContext, useContext, useEffect, useState, useCallback } from 'react';
import { fetchWallets } from '../services/api';
import type { Wallet } from '../types';

interface WalletContextValue {
  wallets: Wallet[];
  selectedWallet: Wallet | null;
  setSelectedWallet: (wallet: Wallet | null) => void;
  refreshWallets: () => Promise<void>;
  loading: boolean;
}

const WalletContext = createContext<WalletContextValue | undefined>(undefined);

export function WalletProvider({ children }: { children: React.ReactNode }) {
  const [wallets, setWallets] = useState<Wallet[]>([]);
  const [selectedWallet, setSelectedWallet] = useState<Wallet | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshWallets = useCallback(async () => {
    setLoading(true);
    try {
      const list = await fetchWallets();
      setWallets(list);
      const defaultWallet = list.find((w) => w.isDefault) || list[0] || null;
      setSelectedWallet((current) => current || defaultWallet);
    } catch {
      setWallets([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshWallets();
  }, [refreshWallets]);

  return (
    <WalletContext.Provider
      value={{ wallets, selectedWallet, setSelectedWallet, refreshWallets, loading }}
    >
      {children}
    </WalletContext.Provider>
  );
}

export function useWallet() {
  const ctx = useContext(WalletContext);
  if (!ctx) {
    throw new Error('useWallet must be used within a WalletProvider');
  }
  return ctx;
}
