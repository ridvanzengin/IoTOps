import { BrowserRouter, Link, Route, Routes } from "react-router-dom";
import { Home } from "./pages/Home";
import { CollectorList } from "./pages/CollectorList";
import { CollectorEditor } from "./pages/CollectorEditor";
import "./App.css";

function App() {
  return (
    <BrowserRouter>
      <nav className="app-nav">
        <Link to="/">Home</Link>
        <Link to="/collectors">Collectors</Link>
      </nav>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/collectors" element={<CollectorList />} />
        <Route path="/collectors/new" element={<CollectorEditor />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
