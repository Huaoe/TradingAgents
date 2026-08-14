import { useEffect, useState } from 'react';
import { Plus, Trash2, Star, Wallet as WalletIcon } from 'lucide-react';
import { Card } from '../components/Card';
import { useWallet } from '../context/useWallet';
import { createWallet, deleteWallet, updateWallet } from '../services/api';
import type { Wallet } from '../types';

function maskAddress(address: string) {
  if (address.length <= 12) return address;
  return `${address.slice(0, 6)}...${address.slice(-4)}`;
}

export function Wallets() {
  const { wallets, refreshWallets, selectedWallet, setSelectedWallet } = useWallet();
  const [showAdd, setShowAdd] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    refreshWallets();
  }, [refreshWallets]);

  async function handleCreate(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError('');
    const form = e.currentTarget;
    const formData = new FormData(form);
    const name = String(formData.get('name') || '');
    const address = String(formData.get('address') || '');
    const privateKey = String(formData.get('privateKey') || '');
    const masterPassword = String(formData.get('masterPassword') || '');
    const confirmPassword = String(formData.get('confirmPassword') || '');
    const isDefault = formData.get('isDefault') === 'on';

    if (!name || !address || !privateKey) {
      setError('Name, address, and private key are required.');
      return;
    }
    if (masterPassword.length < 8) {
      setError('Master password must be at least 8 characters.');
      return;
    }
    if (masterPassword !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    try {
      await createWallet({
        name,
        address,
        privateKey,
        masterPassword,
        isDefault,
        chain: 'hyperliquid',
      });
      form.reset();
      setShowAdd(false);
      await refreshWallets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create wallet');
    }
  }

  async function handleDelete(wallet: Wallet) {
    if (!confirm(`Delete wallet "${wallet.name}"?`)) return;
    try {
      await deleteWallet(wallet.id);
      await refreshWallets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete wallet');
    }
  }

  async function handleSetDefault(wallet: Wallet) {
    try {
      await updateWallet(wallet.id, { isDefault: true });
      await refreshWallets();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update wallet');
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-white">Wallets</h1>
          <p className="text-sm text-gray-400 mt-1">Manage the wallets used for execution.</p>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          className="inline-flex items-center gap-2 bg-violet-600 hover:bg-violet-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Wallet
        </button>
      </div>

      {showAdd && (
        <Card title="Add Wallet">
          <form onSubmit={handleCreate} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium text-gray-400">Name</label>
              <input
                name="name"
                required
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
              />
            </div>
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium text-gray-400">Address</label>
              <input
                name="address"
                required
                placeholder="0x..."
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
              />
            </div>
            <div className="space-y-1 md:col-span-2">
              <label className="text-xs font-medium text-gray-400">Private Key</label>
              <input
                name="privateKey"
                type="password"
                required
                placeholder="Never stored in plain text"
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-400">Master Password</label>
              <input
                name="masterPassword"
                type="password"
                required
                minLength={8}
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-400">Confirm Password</label>
              <input
                name="confirmPassword"
                type="password"
                required
                className="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-violet-500"
              />
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-300 md:col-span-2">
              <input name="isDefault" type="checkbox" className="rounded border-gray-700 bg-gray-900 text-violet-600" />
              Set as default wallet
            </label>
            {error && (
              <div className="md:col-span-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 text-red-200 text-sm">
                {error}
              </div>
            )}
            <div className="md:col-span-2 flex items-center gap-3">
              <button
                type="submit"
                className="bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
              >
                Save Wallet
              </button>
              <button
                type="button"
                onClick={() => setShowAdd(false)}
                className="text-gray-400 hover:text-gray-200 text-sm"
              >
                Cancel
              </button>
            </div>
          </form>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4">
        {wallets.length === 0 && (
          <div className="text-gray-500 text-sm">No wallets configured. Add one to enable execution.</div>
        )}
        {wallets.map((wallet) => (
          <Card
            key={wallet.id}
            className={`flex flex-col sm:flex-row sm:items-start justify-between gap-4 ${selectedWallet?.id === wallet.id ? 'ring-1 ring-violet-500' : ''}`}
          >
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-violet-500/10 text-violet-400 flex-shrink-0">
                <WalletIcon className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="font-medium text-white">{wallet.name}</h3>
                  {wallet.isDefault && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-amber-500/10 text-amber-400">
                      <Star className="w-3 h-3" /> Default
                    </span>
                  )}
                </div>
                <div className="text-sm text-gray-400 mt-0.5 font-mono">{maskAddress(wallet.address)}</div>
                <div className="text-xs text-gray-500 mt-1">{wallet.chain}</div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => setSelectedWallet(wallet)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                  selectedWallet?.id === wallet.id
                    ? 'bg-violet-600 text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {selectedWallet?.id === wallet.id ? 'Selected' : 'Select'}
              </button>
              {!wallet.isDefault && (
                <button
                  type="button"
                  onClick={() => handleSetDefault(wallet)}
                  className="px-3 py-1.5 rounded-lg text-xs font-medium bg-gray-800 text-gray-300 hover:bg-gray-700 transition-colors"
                >
                  Set Default
                </button>
              )}
              <button
                type="button"
                onClick={() => handleDelete(wallet)}
                className="p-1.5 rounded-lg text-red-400 hover:bg-red-500/10 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
