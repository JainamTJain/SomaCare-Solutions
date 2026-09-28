import { Route, Routes } from "react-router-dom";
import SiteChrome from "./components/SiteChrome.jsx";
import HomePage from "./pages/HomePage.jsx";
import TryPage from "./pages/TryPage.jsx";
import PresentPage from "./pages/PresentPage.jsx";
import LivePage from "./pages/LivePage.jsx";

export default function App() {
  return (
    <SiteChrome>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/try" element={<TryPage />} />
        <Route path="/present" element={<PresentPage />} />
        <Route path="/live" element={<LivePage />} />
      </Routes>
    </SiteChrome>
  );
}
