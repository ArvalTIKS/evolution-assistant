import { BrowserRouter, Routes, Route } from 'react-router-dom';
import AdminPanel from './components/AdminPanel';
import QRAssistantPage from './components/QRAssistantPage';
import ClientLanding from './components/ClientLanding';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AdminPanel />} />
        <Route path="/client/:unique_url" element={<ClientLanding />} />
        <Route path="/qr-assistant/:unique_url" element={<QRAssistantPage />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;