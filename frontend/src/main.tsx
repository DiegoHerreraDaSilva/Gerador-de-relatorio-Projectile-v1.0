import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { ConfirmHost } from "./components/ConfirmDialog";
import { HintHost } from "./components/HintHost";
import "./styles/index.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
      <ConfirmHost />
      <HintHost />
    </ErrorBoundary>
  </React.StrictMode>,
);
