import { createContext } from 'react';
import type { Wallet } from '../types';

export interface WalletContextValue {
  wallets: Wallet[];
  selectedWallet: Wallet | null;
  setSelectedWallet: (wallet: Wallet | null) => void;
  refreshWallets: () => Promise<void>;
  loading: boolean;
}

export const WalletContext = createContext<WalletContextValue | undefined>(undefined);
