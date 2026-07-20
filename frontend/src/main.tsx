import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, createRoutesFromElements, RouterProvider } from 'react-router-dom';
import { appRouteElements } from './app/routes';
import { ErrorBoundary } from './components/ErrorBoundary';
import './i18n';
import './index.css';

const router = createBrowserRouter(createRoutesFromElements(appRouteElements));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary scope="root">
      <RouterProvider router={router} />
    </ErrorBoundary>
  </StrictMode>,
);
