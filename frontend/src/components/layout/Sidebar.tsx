import Link from "next/link";

export default function Sidebar() {
  return (
    <aside className="w-64 bg-slate-900 min-h-screen p-5 space-y-4">
      <Link href="/">Dashboard</Link>
      <Link href="/history">History</Link>
    </aside>
  );
}