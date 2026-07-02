import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Home } from "./pages/Home";
import { CollectorList } from "./pages/CollectorList";
import { CollectorEditor } from "./pages/CollectorEditor";
import { Sidebar } from "./components/Sidebar";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <div className="app-shell">
        <Sidebar />
        <div className="app-content">
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/collectors" element={<CollectorList />} />
            <Route path="/collectors/new" element={<CollectorEditor />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;
