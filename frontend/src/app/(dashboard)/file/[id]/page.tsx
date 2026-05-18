"use client";

import { useEffect, useState, use } from "react";
import Link from "next/link";
import { authFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL;

type DocMeta = {
  id: string;
  original_filename?: string;
  filename?: string;
  file_size?: number;
  status?: string;
  created_at?: string;
  processed_at?: string;
  error_message?: string;
};

type Tab = "overview" | "markdown" | "json" | "images";

const STATUS_CONFIG: Record<string, { label: string; color: string; dot: string }> = {
  completed:  { label: "Completed",  color: "text-emerald-600", dot: "bg-emerald-600" },
  processing: { label: "Processing", color: "text-amber-500",   dot: "bg-amber-500 animate-pulse" },
  pending:    { label: "Pending",    color: "text-zinc-400",    dot: "bg-zinc-400" },
  failed:     { label: "Failed",     color: "text-red-500",     dot: "bg-red-500" },
};

function formatBytes(bytes?: number) {
  if (!bytes) return "-";
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function formatDate(iso?: string) {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("id-ID", { dateStyle: "long", timeStyle: "short" });
}

function MarkdownView({ content }: { content: string }) {
  const lines = content.split("\n");
  return (
    <div
      className="prose prose-sm max-w-none leading-relaxed"
      style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: "0.85rem" }}
    >
      {lines.map((line, i) => {
        if (line.startsWith("## "))  return <h2 key={i} className="text-black font-bold text-base mt-6 mb-2">{line.slice(3)}</h2>;
        if (line.startsWith("# "))   return <h1 key={i} className="text-black font-bold text-lg mt-6 mb-2">{line.slice(2)}</h1>;
        if (line.startsWith("### ")) return <h3 key={i} className="text-black/80 font-semibold text-sm mt-4 mb-1">{line.slice(4)}</h3>;
        if (line.startsWith("#### ")) return <h4 key={i} className="text-black/70 font-medium text-sm mt-3 mb-1">{line.slice(5)}</h4>;
        if (line.startsWith("| ")) {
          const cells = line.split("|").filter((c) => c.trim() !== "");
          const isHeader = lines[i + 1]?.startsWith("|---") || lines[i + 1]?.startsWith("| ---") || lines[i + 1]?.match(/^\|[\s:-]+\|/);
          const isSeparator = line.match(/^\|[\s:-]+\|/);
          if (isSeparator) return null;
          return (
            <div key={i} className={`flex border-b border-hairline ${isHeader ? "bg-surface-soft font-medium" : "hover:bg-surface-soft"}`}>
              {cells.map((cell, j) => (
                <div key={j} className="flex-1 px-3 py-1.5 text-xs truncate">{cell.trim()}</div>
              ))}
            </div>
          );
        }
        if (line.startsWith("- ") || line.startsWith("* ")) return <div key={i} className="flex gap-2 my-0.5"><span className="text-black/40 mt-1">•</span><span>{line.slice(2)}</span></div>;
        if (/^\d+\.\s/.test(line)) return <div key={i} className="my-0.5 ml-4">{line}</div>;
        if (line.trim() === "") return <div key={i} className="h-2" />;
        if (line.startsWith("![")) return null;
        return <p key={i} className="my-0.5">{line}</p>;
      })}
    </div>
  );
}

function JsonView({ data }: { data: unknown }) {
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  function toggle(path: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  }

  function renderValue(val: unknown, path: string, depth = 0): React.ReactNode {
    if (val === null) return <span className="text-black/40">null</span>;
    if (typeof val === "boolean") return <span className="text-amber-600">{String(val)}</span>;
    if (typeof val === "number") return <span className="text-cyan-600">{val}</span>;
    if (typeof val === "string") return <span className="text-emerald-600">&ldquo;{val}&rdquo;</span>;

    if (Array.isArray(val)) {
      if (val.length === 0) return <span className="text-black/40">[]</span>;
      const isCollapsed = collapsed.has(path);
      return (
        <span>
          <button onClick={() => toggle(path)} className="text-black/40 hover:text-black mr-1 text-xs">
            {isCollapsed ? "▶" : "▼"}
          </button>
          <span className="text-black/40">[ {val.length} items ]</span>
          {!isCollapsed && (
            <div className="ml-4 border-l border-hairline pl-3 mt-1 space-y-0.5">
              {val.map((item, idx) => (
                <div key={idx} className="flex gap-2 text-xs">
                  <span className="text-black/30 shrink-0">{idx}:</span>
                  {renderValue(item, `${path}.${idx}`, depth + 1)}
                </div>
              ))}
            </div>
          )}
        </span>
      );
    }

    if (typeof val === "object") {
      const entries = Object.entries(val as Record<string, unknown>);
      if (entries.length === 0) return <span className="text-black/40">{"{}"}</span>;
      const isCollapsed = collapsed.has(path);
      return (
        <span>
          <button onClick={() => toggle(path)} className="text-black/40 hover:text-black mr-1 text-xs">
            {isCollapsed ? "▶" : "▼"}
          </button>
          {isCollapsed && <span className="text-black/40">{"{ ... }"}</span>}
          {!isCollapsed && (
            <div className="ml-4 border-l border-hairline pl-3 mt-1 space-y-0.5">
              {entries.map(([k, v]) => (
                <div key={k} className="flex gap-2 text-xs flex-wrap">
                  <span className="text-purple-600 shrink-0">&ldquo;{k}&rdquo;:</span>
                  {renderValue(v, `${path}.${k}`, depth + 1)}
                </div>
              ))}
            </div>
          )}
        </span>
      );
    }

    return <span>{String(val)}</span>;
  }

  return (
    <div className="text-xs" style={{ fontFamily: "'JetBrains Mono', monospace" }}>
      {renderValue(data, "root")}
    </div>
  );
}

function ImageGallery({ images, docId }: { images: string[]; docId: string }) {
  const [selected, setSelected] = useState<string | null>(null);

  if (images.length === 0) {
    return <p className="text-black/40 text-sm py-10 text-center">Tidak ada gambar ditemukan</p>;
  }

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {images.map((img) => {
          const src = `${API}/outputs/images/${docId}/${img}`;
          return (
            <button
              key={img}
              onClick={() => setSelected(src)}
              className="group relative aspect-square rounded-xl overflow-hidden border border-hairline hover:border-black/30 transition bg-surface-soft"
            >
              <img
                src={src}
                alt={img}
                className="w-full h-full object-contain p-2 group-hover:scale-105 transition-transform duration-300"
              />
              <div className="absolute inset-0 bg-black/0 group-hover:bg-black/10 transition flex items-center justify-center">
                <svg className="w-6 h-6 text-black opacity-0 group-hover:opacity-60 transition" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                </svg>
              </div>
              <p className="absolute bottom-0 left-0 right-0 bg-black/60 text-xs text-white px-2 py-1 truncate opacity-0 group-hover:opacity-100 transition">
                {img}
              </p>
            </button>
          );
        })}
      </div>

      {selected && (
        <div
          className="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
          onClick={() => setSelected(null)}
        >
          <button className="absolute top-4 right-4 text-white/60 hover:text-white text-2xl">✕</button>
          <img
            src={selected}
            alt="preview"
            className="max-w-full max-h-full object-contain rounded-xl"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
    </>
  );
}

function OverviewTab({ meta, id, isCompleted }: { meta: DocMeta; id: string; isCompleted: boolean }) {
  const cfg = STATUS_CONFIG[meta.status || ""] ?? STATUS_CONFIG.pending;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="rounded-lg border border-hairline p-5">
          <p className="text-caption text-black/50 uppercase tracking-wider mb-1">Status</p>
          <div className="flex items-center gap-2 mt-1">
            <span className={`w-2.5 h-2.5 rounded-full ${cfg.dot}`} />
            <span className={`text-headline font-semibold ${cfg.color}`}>{cfg.label}</span>
          </div>
        </div>
        <div className="rounded-lg border border-hairline p-5">
          <p className="text-caption text-black/50 uppercase tracking-wider mb-1">Ukuran File</p>
          <p className="text-headline font-semibold text-black">{formatBytes(meta.file_size)}</p>
        </div>
        <div className="rounded-lg border border-hairline p-5">
          <p className="text-caption text-black/50 uppercase tracking-wider mb-1">Dibuat</p>
          <p className="text-headline font-semibold text-black">{formatDate(meta.created_at)}</p>
        </div>
        {meta.processed_at && (
          <div className="rounded-lg border border-hairline p-5">
            <p className="text-caption text-black/50 uppercase tracking-wider mb-1">Selesai Diproses</p>
            <p className="text-headline font-semibold text-black">{formatDate(meta.processed_at)}</p>
          </div>
        )}
        <div className="rounded-lg border border-hairline p-5">
          <p className="text-caption text-black/50 uppercase tracking-wider mb-1">Document ID</p>
          <p className="font-mono text-sm text-black/70 break-all mt-1">{meta.id}</p>
        </div>
      </div>

      {meta.status === "failed" && meta.error_message && (
        <div className="text-body-sm text-red-500 bg-red-50 border border-red-200 rounded-lg px-5 py-4">
          <p className="font-medium mb-1">Error:</p>
          {meta.error_message}
        </div>
      )}

      {isCompleted && (
        <div className="rounded-lg border border-hairline p-5">
          <p className="text-caption text-black/50 uppercase tracking-wider mb-3">Download</p>
          <div className="flex gap-3 flex-wrap">
            <a
              href={`${API}/api/documents/${id}/markdown`}
              download
              className="btn-secondary flex items-center gap-2 text-body-sm"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download Markdown
            </a>
            <a
              href={`${API}/api/documents/${id}/json`}
              download
              className="btn-secondary flex items-center gap-2 text-body-sm"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download JSON
            </a>
          </div>
        </div>
      )}
    </div>
  );
}

export default function DetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [meta, setMeta] = useState<DocMeta | null>(null);
  const [tab, setTab] = useState<Tab>("overview");
  const [markdown, setMarkdown] = useState<string>("");
  const [jsonData, setJsonData] = useState<unknown>(null);
  const [images, setImages] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [tabLoading, setTabLoading] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const res = await authFetch(`${API}/api/documents/${id}`, { cache: "no-store" });
        if (res.ok) setMeta(await res.json());
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [id]);

  useEffect(() => {
    async function loadTab() {
      setTabLoading(true);
      try {
        if (tab === "markdown" && !markdown) {
          const res = await authFetch(`${API}/api/documents/${id}/markdown`);
          if (res.ok) setMarkdown(await res.text());
        }
        if (tab === "json" && !jsonData) {
          const res = await authFetch(`${API}/api/documents/${id}/json`);
          if (res.ok) setJsonData(await res.json());
        }
        if (tab === "images" && images.length === 0) {
          const res = await authFetch(`${API}/api/documents/${id}/images`);
          if (res.ok) {
            const data = await res.json();
            setImages(data.images || []);
          }
        }
      } finally {
        setTabLoading(false);
      }
    }
    if (meta?.status === "completed" && tab !== "overview") loadTab();
  }, [tab, meta?.status, id]);

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-8 h-8 border-2 border-black border-t-transparent rounded-full animate-spin" />
          <p className="text-body-sm text-black/40">Memuat dokumen...</p>
        </div>
      </div>
    );
  }

  if (!meta) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <div className="text-center">
          <p className="text-4xl mb-4">🔍</p>
          <p className="text-body text-black/50">Dokumen tidak ditemukan</p>
          <Link href="/" className="text-link text-black/60 mt-4 block hover:text-black">← Kembali ke Dashboard</Link>
        </div>
      </div>
    );
  }

  const cfg = STATUS_CONFIG[meta.status || ""] ?? STATUS_CONFIG.pending;
  const isCompleted = meta.status === "completed";

  const TABS: { key: Tab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "markdown", label: "Markdown" },
    { key: "json", label: "JSON" },
    { key: "images", label: "Images" },
  ];

  return (
    <div>
      <section className="border-b border-hairline">
        <div className="max-w-7xl mx-auto px-8 py-6">
          <div className="flex items-center gap-2 text-sm text-black/40 mb-4">
            <Link href="/" className="hover:text-black transition">Dashboard</Link>
            <span>/</span>
            <Link href="/history" className="hover:text-black transition">History</Link>
            <span>/</span>
            <span className="text-black/60 truncate max-w-xs">{meta.original_filename || meta.filename}</span>
          </div>

          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-2 flex-wrap">
                <h1 className="text-card-title truncate">
                  {meta.original_filename || meta.filename || "Untitled.pdf"}
                </h1>
                <span className={`flex items-center gap-1.5 text-body-sm font-medium ${cfg.color}`}>
                  <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
                  {cfg.label}
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-8 py-8">
        {!isCompleted && tab !== "overview" ? (
          <div className="text-center py-24">
            {meta.status === "failed" ? (
              <div className="card inline-block">
                <p className="text-4xl mb-4">❌</p>
                <p className="text-body text-black/50">Ekstraksi dokumen gagal</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-4">
                <div className="w-10 h-10 border-2 border-black border-t-transparent rounded-full animate-spin" />
                <p className="text-body text-black/60">Dokumen sedang diproses...</p>
                <p className="text-body-sm text-black/40">Halaman akan otomatis update</p>
              </div>
            )}
          </div>
        ) : (
          <>
            <div className="color-block-lilac mb-6">
              <div className="flex gap-2 w-fit">
                {TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    className={`px-5 py-2.5 rounded-lg text-body-sm font-medium transition-all capitalize ${
                      tab === t.key ? "bg-black text-white" : "text-black/60 hover:text-black hover:bg-white/30"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="color-block-cream">
              {tabLoading ? (
                <div className="flex items-center justify-center py-24">
                  <div className="w-7 h-7 border-2 border-black border-t-transparent rounded-full animate-spin" />
                </div>
              ) : (
                <div className="p-6 overflow-auto max-h-[70vh]">
                  {tab === "overview" && (
                    <OverviewTab meta={meta} id={id} isCompleted={isCompleted} />
                  )}
                  {tab === "markdown" && (
                    markdown
                      ? <MarkdownView content={markdown} />
                      : <p className="text-body text-black/40 text-center py-10">Tidak ada konten markdown</p>
                  )}
                  {tab === "json" && (
                    jsonData
                      ? <JsonView data={jsonData} />
                      : <p className="text-body text-black/40 text-center py-10">Tidak ada data JSON</p>
                  )}
                  {tab === "images" && (
                    <ImageGallery images={images} docId={id} />
                  )}
                </div>
              )}
            </div>

            {tab === "markdown" && markdown && (
              <div className="mt-4 flex justify-end">
                <button
                  onClick={() => navigator.clipboard.writeText(markdown)}
                  className="text-body-sm text-black/40 hover:text-black flex items-center gap-2 transition"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                  Copy markdown
                </button>
              </div>
            )}
          </>
        )}
      </section>
    </div>
  );
}
