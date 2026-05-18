"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { authFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL;

type Doc = {
  id: string;
  filename?: string;
  original_filename?: string;
  status?: string;
  created_at?: string;
};

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  completed:  { label: "Completed",  color: "text-emerald-600", dot: "bg-emerald-600" },
  processing: { label: "Processing", color: "text-amber-500",   dot: "bg-amber-500 animate-pulse" },
  pending:    { label: "Pending",    color: "text-zinc-400",    dot: "bg-zinc-400" },
  queued:     { label: "Queued",     color: "text-blue-500",    dot: "bg-blue-500" },
  failed:     { label: "Failed",     color: "text-red-500",     dot: "bg-red-500" },
};

function formatDate(iso?: string) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

function StatCard({
  label,
  value,
  pulse,
}: {
  label: string;
  value: number;
  pulse?: boolean;
}) {
  return (
    <div className="rounded-lg bg-white/50 p-5">
      <p className="text-caption text-black/50 uppercase tracking-wider">{label}</p>
      <div className="flex items-center gap-2 mt-2">
        <h3 className="text-3xl font-bold text-black">{value}</h3>
        {pulse && value > 0 && (
          <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
        )}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);

  async function loadData() {
    try {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${API}/api/documents`, {
        cache: "no-store",
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      const data = await res.json();
      const list = Array.isArray(data)
        ? data
        : Array.isArray(data?.documents)
        ? data.documents
        : [];
      setDocs(list);
    } catch (e) {
      console.error(e);
    }
  }

  async function uploadFile(file: File) {
    try {
      setUploading(true);
      const form = new FormData();
      form.append("file", file);
      const token = localStorage.getItem("auth_token");
      await fetch(`${API}/api/upload`, {
        method: "POST",
        body: form,
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      await loadData();
    } catch (e) {
      console.error(e);
      alert("Upload gagal");
    } finally {
      setUploading(false);
    }
  }

  function handleDrop(e: React.DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) uploadFile(file);
  }

  useEffect(() => {
    loadData();
    const t = setInterval(loadData, 3000);
    return () => clearInterval(t);
  }, []);

  const stats = {
    total:      docs.length,
    queued:     docs.filter((d) => d.status === "pending" || d.status === "queued").length,
    processing: docs.filter((d) => d.status === "processing").length,
    completed:  docs.filter((d) => d.status === "completed").length,
    failed:     docs.filter((d) => d.status === "failed").length,
  };

  return (
    <main>
      {/* HERO SECTION - White canvas */}
      <section className="max-w-7xl mx-auto px-8 pt-16 pb-12">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <p className="text-eyebrow text-black/50 mb-4">
              AI Powered Document Extraction
            </p>
            <h1 className="text-display-lg mb-6">
              Convert PDF Into
              <span className="block">Markdown & JSON</span>
            </h1>
            <p className="text-body-lg text-black/60 mb-8 max-w-lg">
              Upload dokumen Anda. Sistem akan membaca scan, mengekstrak teks,
              tabel, gambar, dan rumus secara otomatis.
            </p>
            <div className="flex gap-4 flex-wrap items-center">
              <span className="px-5 py-3 rounded-lg bg-surface-soft text-body-sm font-medium">
                {stats.total} Documents
              </span>
              {stats.processing > 0 && (
                <span className="px-5 py-3 rounded-lg border border-amber-300 bg-amber-50 text-amber-700 text-body-sm flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
                  {stats.processing} Processing
                </span>
              )}
              {stats.queued > 0 && (
                <span className="px-5 py-3 rounded-lg border border-blue-300 bg-blue-50 text-blue-700 text-body-sm flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-blue-500" />
                  {stats.queued} In Queue
                </span>
              )}
            </div>
          </div>

          {/* Upload Zone - White card with hairline border */}
          <div
            onDrop={handleDrop}
            onDragOver={(e) => e.preventDefault()}
            onDragEnter={() => setDragging(true)}
            onDragLeave={() => setDragging(false)}
            className={`rounded-xl border p-8 transition-all cursor-pointer ${
              dragging
                ? "border-black bg-surface-soft scale-[1.02]"
                : "border-hairline bg-white hover:border-black/30"
            }`}
          >
            <div className="text-center">
              <div className="mx-auto h-16 w-16 rounded-full bg-black mb-5 flex items-center justify-center">
                <svg className="w-7 h-7 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                </svg>
              </div>
              <h3 className="text-card-title mb-2">Upload PDF File</h3>
              <p className="text-body-sm text-black/40 mb-5">Drag & drop file ke sini, atau klik tombol di bawah</p>
              <label className="inline-block btn-primary cursor-pointer">
                {uploading ? (
                  <span className="flex items-center gap-2">
                    <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                    Uploading...
                  </span>
                ) : (
                  "Choose File"
                )}
                <input
                  hidden
                  type="file"
                  accept=".pdf"
                  disabled={uploading}
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) uploadFile(file);
                  }}
                />
              </label>
            </div>
          </div>
        </div>
      </section>

      {/* STATS - Lime color block section */}
      <section className="max-w-7xl mx-auto px-8 pb-12">
        <div className="color-block-lime">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
            <StatCard label="Queued" value={stats.queued} />
            <StatCard label="Processing" value={stats.processing} pulse={stats.processing > 0} />
            <StatCard label="Completed" value={stats.completed} />
            <StatCard label="Failed" value={stats.failed} />
          </div>
        </div>
      </section>

      {/* FEATURES - Navy color block section */}
      <section className="max-w-7xl mx-auto px-8 pb-12">
        <div className="color-block-navy">
          <div className="grid md:grid-cols-3 gap-8">
            <div>
              <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center mb-4">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </div>
              <h3 className="text-headline text-white mb-2">Text Extraction</h3>
              <p className="text-body text-white/70">Extract clean text from digital and scanned PDFs with OCR support.</p>
            </div>
            <div>
              <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center mb-4">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              </div>
              <h3 className="text-headline text-white mb-2">Table Recognition</h3>
              <p className="text-body text-white/70">Automatically detect and extract structured tables from documents.</p>
            </div>
            <div>
              <div className="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center mb-4">
                <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
              <h3 className="text-headline text-white mb-2">Image Extraction</h3>
              <p className="text-body text-white/70">Extract images and figures with automatic organization.</p>
            </div>
          </div>
        </div>
      </section>

      {/* RECENT FILES */}
      <section className="max-w-7xl mx-auto px-8 pb-20">
        <h2 className="text-heading-md mb-6">Recent Files</h2>
        {docs.length === 0 ? (
          <div className="text-center py-12 border border-dashed border-hairline rounded-xl">
            <p className="text-body text-black/40">Belum ada dokumen. Upload PDF pertama Anda!</p>
          </div>
        ) : (
          <div className="grid gap-3">
            {docs.slice(0, 5).map((doc) => {
              const status = STATUS_CONFIG[doc.status || "pending"];
              return (
                <Link
                  key={doc.id}
                  href={`/file/${doc.id}`}
                  className="flex items-center justify-between p-4 bg-surface-soft rounded-lg hover:bg-hairline transition-colors"
                >
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-lg bg-black flex items-center justify-center">
                      <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                      </svg>
                    </div>
                    <div>
                      <p className="text-body-sm font-medium text-black">
                        {doc.original_filename || doc.filename}
                      </p>
                      <p className="text-caption text-black/40">
                        {formatDate(doc.created_at)}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${status.dot}`} />
                    <span className={`text-caption ${status.color}`}>{status.label}</span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </section>
    </main>
  );
}