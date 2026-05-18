"use client";

import { useRef } from "react";

export default function UploadDropzone({
  onSelect,
}: {
  onSelect: (file: File) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);

  return (
    <div
      onClick={() => ref.current?.click()}
      className="border-2 border-dashed border-slate-600 rounded-2xl p-10 text-center cursor-pointer"
    >
      <p>Drop PDF here</p>
      <p>or click to browse</p>

      <input
        ref={ref}
        hidden
        type="file"
        accept=".pdf"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onSelect(file);
        }}
      />
    </div>
  );
}