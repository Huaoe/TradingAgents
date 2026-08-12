import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { WalletProvider } from './context/WalletContext';
import { Dashboard } from './pages/Dashboard';
import { Scanner } from './pages/Scanner';
import { Signals } from './pages/Signals';
import { Positions } from './pages/Positions';
import { Strategies } from './pages/Strategies';
import { StrategyEditor } from './pages/StrategyEditor';
import { Backtest } from './pages/Backtest';
import { Wallets } from './pages/Wallets';
import { Alerts } from './pages/Alerts';
import { Journal } from './pages/Journal';

function App() {
  return (
    <BrowserRouter>
      <WalletProvider>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/scanner" element={<Scanner />} />
            <Route path="/signals" element={<Signals />} />
            <Route path="/positions" element={<Positions />} />
            <Route path="/wallets" element={<Wallets />} />
            <Route path="/alerts" element={<Alerts />} />
            <Route path="/journal" element={<Journal />} />
            <Route path="/strategies" element={<Strategies />} />
            <Route path="/strategies/new" element={<StrategyEditor />} />
            <Route path="/strategies/:id" element={<StrategyEditor />} />
            <Route path="/backtest" element={<Backtest />} />
          </Routes>
        </Layout>
      </WalletProvider>
    </BrowserRouter>
  );
}

export default App;
