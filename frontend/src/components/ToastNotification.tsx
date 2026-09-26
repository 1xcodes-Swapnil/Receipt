import { CheckCircle2, AlertCircle, Info, X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  type: 'success' | 'error' | 'info';
  title: string;
  message?: string;
}

interface Props {
  toasts: ToastMessage[];
  onDismiss: (id: string) => void;
}

export function ToastNotification({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-md w-full px-4 pointer-events-none">
      {toasts.map((toast) => {
        const isSuccess = toast.type === 'success';
        const isError = toast.type === 'error';
        const Icon = isSuccess ? CheckCircle2 : isError ? AlertCircle : Info;

        return (
          <div
            key={toast.id}
            className={`pointer-events-auto p-4 rounded-2xl shadow-soft-2xl border flex items-start gap-3 backdrop-blur-md transition-all duration-300 animate-slide-up ${
              isSuccess
                ? 'bg-emerald-900/90 text-white border-emerald-700'
                : isError
                ? 'bg-rose-900/90 text-white border-rose-700'
                : 'bg-brand-900/90 text-white border-brand-700'
            }`}
          >
            <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${isSuccess ? 'text-emerald-400' : isError ? 'text-rose-400' : 'text-brand-300'}`} />
            <div className="flex-1">
              <h4 className="font-semibold text-sm">{toast.title}</h4>
              {toast.message && <p className="text-xs text-gray-200 mt-0.5 leading-relaxed">{toast.message}</p>}
            </div>
            <button
              onClick={() => onDismiss(toast.id)}
              className="text-gray-400 hover:text-white p-1 rounded-full hover:bg-white/10 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
