"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useCallback } from "react";
import { authFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL;

type Doc = {
  id: string;
  filename?: string;
  original_filename?: string;
  file_size?: number;
  status?: string;
  created_at?: string;
  processed_at?: string;
  error_message?: string;
};

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  completed:  { label: "Completed",  color: "text-emerald-600", dot: "bg-emerald-600" },
  processing: { label: "Processing", color: "text-amber-500",   dot: "bg-amber-500 animate-pulse" },
  pending:    { label: "Pending",    color: "text-zinc-400",    dot: "bg-zinc-400" },
  failed:     { label: "Failed",     color: "text-red-500",     dot: "bg-red-500" },
  queued:     { label: "Queued",     color: "text-blue-500",    dot: "bg-blue-500" },
};

function formatBytes(bytes?: number) {
  if (!bytes) return "-";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function formatDate(iso?: string) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
}

export default function HistoryPage() {
  const router = useRouter();
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [deleting, setDeleting] = useState<Record<string, boolean>>({});
  const [toast, setToast] = useState<{ message: string; type: "success" | "error" } | null>(null);

  const showToast = useCallback((message: string, type: "success" | "error") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3000);
  }, []);

  useEffect(() => {
    async function load() {
      try {
        const res = await authFetch(`${API}/api/documents`, { cache: "no-store" });
        const data = await res.json();
        const list = Array.isArray(data) ? data : Array.isArray(data?.documents) ? data.documents : [];
        setDocs(list);
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  const filtered = docs.filter((d) => {
    if (filter !== "all" && d.status !== filter) return false;
    if (search && !(d.filename || d.original_filename || "").toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const stats = {
    total: docs.length,
    completed: docs.filter((d) => d.status === "completed").length,
    processing: docs.filter((d) => d.status === "processing").length,
    pending: docs.filter((d) => d.status === "pending" || d.status === "queued").length,
    failed: docs.filter((d) => d.status === "failed").length,
  };

  const handleDelete = async (e: React.MouseEvent, documentId: string) => {
    e.stopPropagation();

    if (!window.confirm("Are you sure you want to delete this document?")) {
      return;
    }

    setDeleting((prev) => ({ ...prev, [documentId]: true }));

    try {
      const res = await authFetch(`${API}/api/documents/${documentId}`, {
        method: "DELETE",
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ message: "Failed to delete document" }));
        throw new Error(err.message || err.error || "Failed to delete document");
      }

      setDocs((prev) => prev.filter((d) => d.id !== documentId));
      showToast("Document deleted successfully", "success");
    } catch (e) {
      const message = e instanceof Error ? e.message : "Failed to delete document";
      showToast(message, "error");
    } finally {
      setDeleting((prev) => ({ ...prev, [documentId]: false }));
    }
  };

  return (
    <main>
      {/* Toast */}
      {toast && (
        <div className="fixed top-4 right-4 z-50 animate-in fade-in slide-in-from-top-2">
          <div
            className={`px-5 py-3 rounded-xl shadow-lg text-sm font-medium flex items-center gap-2 ${
              toast.type === "success"
                ? "bg-emerald-600 text-white"
                : "bg-red-500 text-white"
            }`}
          >
            {toast.type === "success" ? (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            )}
            {toast.message}
            <button onClick={() => setToast(null)} className="ml-2 opacity-70 hover:opacity-100">
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* Header */}
      <section className="max-w-7xl mx-auto px-8 pt-10 pb-6">
        <div className="flex items-center gap-2 text-sm text-black/40 mb-3">
          <Link href="/" className="hover:text-black transition">Dashboard</Link>
          <span>/</span>
          <span className="text-black/60">History</span>
        </div>
        <p className="text-eyebrow text-black/50 mb-2">Document Archive</p>
        <h1 className="text-display-lg mb-3">All Documents</h1>
        <p className="text-body text-black/50">Kelola dan lihat semua dokumen yang telah diproses</p>
      </section>

      {/* Stats Cards */}
      <section className="max-w-7xl mx-auto px-8 pb-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="rounded-lg bg-white/50 p-5">
            <p className="text-caption text-black/50 uppercase tracking-wider">Total</p>
            <h3 className="text-3xl font-bold text-black mt-2">{stats.total}</h3>
          </div>
          <div className="rounded-lg bg-white/50 p-5">
            <p className="text-caption text-black/50 uppercase tracking-wider">Completed</p>
            <h3 className="text-3xl font-bold text-emerald-600 mt-2">{stats.completed}</h3>
          </div>
          <div className="rounded-lg bg-white/50 p-5">
            <p className="text-caption text-black/50 uppercase tracking-wider">Processing</p>
            <div className="flex items-center gap-2 mt-2">
              <h3 className="text-3xl font-bold text-amber-500">{stats.processing}</h3>
              {stats.processing > 0 && <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse" />}
            </div>
          </div>
          <div className="rounded-lg bg-white/50 p-5">
            <p className="text-caption text-black/50 uppercase tracking-wider">Failed</p>
            <h3 className="text-3xl font-bold text-red-500 mt-2">{stats.failed}</h3>
          </div>
        </div>
      </section>

      {/* Filter & Search */}
      <section className="max-w-7xl mx-auto px-8 pb-6">
        <div className="flex flex-wrap gap-3 items-center justify-between">
          <div className="flex gap-2">
            <button
              onClick={() => setFilter("all")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                filter === "all" ? "bg-black text-white" : "bg-surface-soft text-black/60 hover:bg-hairline"
              }`}
            >
              All ({stats.total})
            </button>
            <button
              onClick={() => setFilter("completed")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                filter === "completed" ? "bg-black text-white" : "bg-surface-soft text-black/60 hover:bg-hairline"
              }`}
            >
              Completed ({stats.completed})
            </button>
            <button
              onClick={() => setFilter("processing")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                filter === "processing" ? "bg-black text-white" : "bg-surface-soft text-black/60 hover:bg-hairline"
              }`}
            >
              Processing ({stats.processing})
            </button>
            <button
              onClick={() => setFilter("failed")}
              className={`px-4 py-2 rounded-lg text-sm transition-colors ${
                filter === "failed" ? "bg-black text-white" : "bg-surface-soft text-black/60 hover:bg-hairline"
              }`}
            >
              Failed ({stats.failed})
            </button>
          </div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search files..."
            className="px-4 py-2 rounded-lg border border-hairline text-sm bg-white focus:outline-none focus:border-black w-full sm:w-64"
          />
        </div>
      </section>

      {/* Document List */}
      <section className="max-w-7xl mx-auto px-8 pb-20">
        {loading ? (
          <div className="text-center py-12">
            <div className="w-8 h-8 border-2 border-black border-t-transparent rounded-full animate-spin mx-auto"></div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="text-center py-12 border border-dashed border-hairline rounded-xl">
            <p className="text-body text-black/40">Tidak ada dokumen</p>
          </div>
        ) : (
          <div className="border border-hairline rounded-xl overflow-hidden">
            <table className="w-full">
              <thead className="bg-surface-soft text-left">
                <tr>
                  <th className="px-4 py-3 text-caption text-black/50 font-medium">Filename</th>
                  <th className="px-4 py-3 text-caption text-black/50 font-medium">Size</th>
                  <th className="px-4 py-3 text-caption text-black/50 font-medium">Status</th>
                  <th className="px-4 py-3 text-caption text-black/50 font-medium">Processed</th>
                  <th className="px-4 py-3 text-caption text-black/50 font-medium text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((doc) => {
                  const status = STATUS_CONFIG[doc.status || "pending"];
                  const isDeleting = deleting[doc.id] ?? false;
                  return (
                    <tr
                      key={doc.id}
                      onClick={() => !isDeleting && router.push(`/file/${doc.id}`)}
                      className={`border-t border-hairline hover:bg-surface-soft/50 transition-colors ${
                        isDeleting ? "opacity-50 pointer-events-none" : "cursor-pointer"
                      }`}
                    >
                      <td className="px-4 py-3">
                        <p className="text-body-sm font-medium text-black">
                          {doc.original_filename || doc.filename}
                        </p>
                        <p className="text-caption text-black/40 mt-0.5">{doc.id}</p>
                      </td>
                      <td className="px-4 py-3 text-body-sm text-black/60">
                        {formatBytes(doc.file_size)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${status.dot}`} />
                          <span className={`text-body-sm ${status.color}`}>{status.label}</span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-body-sm text-black/60">
                        {formatDate(doc.processed_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={(e) => handleDelete(e, doc.id)}
                          disabled={isDeleting}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-red-200 text-red-600 hover:bg-red-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                        >
                          {isDeleting ? (
                            <>
                              <span className="w-3.5 h-3.5 border-2 border-red-600 border-t-transparent rounded-full animate-spin" />
                              Deleting...
                            </>
                          ) : (
                            <>
                              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                              </svg>
                              Delete
                            </>
                          )}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}