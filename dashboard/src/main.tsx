import React from 'react';
import ReactDOM from 'react-dom/client';
import '@fontsource-variable/manrope';
import { lazy, Suspense } from 'react';
import InstallGuide from './InstallGuide';
import './styles.css';

const App = lazy(() => import('./App'));
const isInstallGuide = ['/install', '/install/index.html'].includes(window.location.pathname.replace(/\/+$/, ''));

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {isInstallGuide ? <InstallGuide /> : <Suspense fallback={<div className="auth-screen"><div className="loading">Открываем кабинет…</div></div>}><App /></Suspense>}
  </React.StrictMode>,
);
