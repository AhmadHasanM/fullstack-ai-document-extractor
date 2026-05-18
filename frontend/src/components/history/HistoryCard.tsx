import Link from "next/link";

export default function HistoryCard({
  item,
}: {
  item: any;
}) {
  return (
    <Link
      href={`/file/${item.id}`}
      className="bg-slate-800 rounded-2xl p-5 block"
    >
      <h3>{item.filename}</h3>
      <p>{item.status}</p>
    </Link>
  );
}