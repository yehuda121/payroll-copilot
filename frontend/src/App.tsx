import { AppRoutes } from './app/routes';
import { DialogProvider } from './components/ui/Dialog';

export default function App() {
  return (
    <DialogProvider>
      <AppRoutes />
    </DialogProvider>
  );
}
