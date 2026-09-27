import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import Landing from './pages/Landing';
import Dashboard from './pages/Dashboard';
import PRReview from './pages/PRReview';
import ReviewDetails from './pages/ReviewDetails';
import BugImmunity from './pages/BugImmunity';
import PatternLibrary from './pages/PatternLibrary';
import ReplayBenchmark from './pages/ReplayBenchmark';
import AuditTrail from './pages/AuditTrail';
import PRActivityLogs from './pages/PRActivityLogs';
import DemoExecution from './pages/DemoExecution';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Landing />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/demo" element={<DemoExecution />} />
          <Route path="/activity" element={<PRActivityLogs />} />
          <Route path="/review" element={<PRReview />} />
          <Route path="/reviews/:runId" element={<ReviewDetails />} />
          <Route path="/immunity" element={<BugImmunity />} />
          <Route path="/patterns" element={<PatternLibrary />} />
          <Route path="/replay" element={<ReplayBenchmark />} />
          <Route path="/audit" element={<AuditTrail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
