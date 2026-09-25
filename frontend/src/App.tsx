import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import Dashboard from './pages/Dashboard';
import PRReview from './pages/PRReview';
import ReviewDetails from './pages/ReviewDetails';
import { BugImmunity, Replay, AuditTrail } from './pages/Placeholders';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="/review" element={<PRReview />} />
          <Route path="/reviews/:runId" element={<ReviewDetails />} />
          <Route path="/immunity" element={<BugImmunity />} />
          <Route path="/replay" element={<Replay />} />
          <Route path="/audit" element={<AuditTrail />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
