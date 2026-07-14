import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createBrowserRouter, createRoutesFromElements, RouterProvider } from 'react-router-dom';
import { appRouteElements } from './app/routes';
import './i18n';
import './index.css';

const router = createBrowserRouter(createRoutesFromElements(appRouteElements));

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
