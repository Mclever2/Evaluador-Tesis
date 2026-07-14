import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import { inicializarTema } from "./lib/theme";
import "./index.css";

inicializarTema();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
