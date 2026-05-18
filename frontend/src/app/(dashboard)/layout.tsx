"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/lib/auth";

function DashboardNavigation() {
  const { user, logout, isAuthenticated } = useAuth();

  return (
    <>
      {/* Top Navigation - sticky white bar */}
      <nav className="sticky top-0 z-50 bg-white border-b border-hairline">
        <div className="max-w-7xl mx-auto px-8 h-14 flex items-center justify-between">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-3 group">
            <div className="h-8 w-8 rounded-lg bg-black flex items-center justify-center">
              <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="font-semibold text-base tracking-tight">AI-Powered Document Intelligence</span>
          </Link>

          {/* Navigation Links */}
          <div className="flex items-center gap-1">
            <Link
              href="/"
              className="px-4 py-2 rounded-full text-sm text-black hover:bg-surface-soft transition-all"
            >
              Dashboard
            </Link>
            <Link
              href="/history"
              className="px-4 py-2 rounded-full text-sm text-black/60 hover:text-black hover:bg-surface-soft transition-all"
            >
              History
            </Link>
            <Link
              href="/chat"
              className="px-4 py-2 rounded-full text-sm text-black/60 hover:text-black hover:bg-surface-soft transition-all"
            >
              Chat
            </Link>

            {isAuthenticated && (
              <div className="flex items-center gap-2 ml-4">
                <span className="text-sm text-black/60">{user?.email}</span>
                <button
                  onClick={logout}
                  className="px-4 py-2 rounded-full text-sm text-black/60 hover:text-black hover:bg-surface-soft transition-all"
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* Marquee Strip - thin black ribbon */}
      <div className="bg-black text-white h-9 flex items-center overflow-hidden">
        <div className="flex animate-marquee whitespace-nowrap text-sm">
          <span className="mx-8">AI Powered Document Extraction</span>
          <span className="mx-8">•</span>
          <span className="mx-8">Extract text, tables, images, and formulas</span>
          <span className="mx-8">•</span>
          <span className="mx-8">Convert PDF to Markdown & JSON</span>
          <span className="mx-8">•</span>
          <span className="mx-8">Chat with your documents</span>
        </div>
      </div>
    </>
  );
}

function DashboardFooter() {
  return (
    <footer className="bg-white border-t border-hairline py-16 px-8">
      <div className="max-w-7xl mx-auto">
        <div className="flex flex-col md:flex-row justify-between items-start gap-8">
          <div>
            <h4 className="text-caption text-black mb-4">AI-Powered Document Intelligence</h4>
            <p className="text-body-sm text-black/60 max-w-xs">
              AI-powered document extraction system that converts PDF documents into Markdown and JSON formats.
            </p>
          </div>
          <div className="flex gap-8">
            <div>
              <h4 className="text-caption text-black mb-3">Product</h4>
              <ul className="space-y-2 text-body-sm text-black/60">
                <li><Link href="/" className="hover:text-black">Dashboard</Link></li>
                <li><Link href="/history" className="hover:text-black">History</Link></li>
                <li><Link href="/chat" className="hover:text-black">Chat</Link></li>
              </ul>
            </div>
            <div>
              <h4 className="text-caption text-black mb-3">System</h4>
              <ul className="space-y-2 text-body-sm text-black/60">
                <li>Backend: Go/Gin</li>
                <li>AI Service: Python</li>
                <li>Database: PostgreSQL</li>
              </ul>
            </div>
          </div>
        </div>
        <div className="mt-12 pt-8 border-t border-hairline-soft text-center">
          <p className="text-caption text-black/40">AI-Powered Document Intelligence</p>
        </div>
      </div>
    </footer>
  );
}

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const { isAuthenticated, isLoading } = useAuth();

  // Reactively redirect when auth state changes
  useEffect(() => {
    if (isLoading) return;
    if (!isAuthenticated) {
      router.replace("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white">
        <div className="w-8 h-8 border-2 border-black border-t-transparent rounded-full animate-spin"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="min-h-screen bg-white">
      <DashboardNavigation />
      {children}
      <DashboardFooter />
    </div>
  );
}