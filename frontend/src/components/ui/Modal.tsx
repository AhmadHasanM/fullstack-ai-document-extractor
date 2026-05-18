"use client";

export default function Modal({
  open,
  onClose,
  children,
}: {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 bg-black/60 grid place-items-center z-50">
      <div className="bg-slate-900 p-6 rounded-2xl w-full max-w-xl">
        <button
          onClick={onClose}
          className="mb-4 text-sm text-slate-400"
        >
          Close
        </button>
        {children}
      </div>
    </div>
  );
}