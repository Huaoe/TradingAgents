import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { Dashboard } from './pages/Dashboard';
import { Scanner } from './pages/Scanner';
import { Signals } from './pages/Signals';
import { Positions } from './pages/Positions';
import { Strategies } from './pages/Strategies';
import { StrategyEditor } from './pages/StrategyEditor';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/scanner" element={<Scanner />} />
          <Route path="/signals" element={<Signals />} />
          <Route path="/positions" element={<Positions />} />
          <Route path="/strategies" element={<Strategies />} />
          <Route path="/strategies/new" element={<StrategyEditor />} />
          <Route path="/strategies/:id" element={<StrategyEditor />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
