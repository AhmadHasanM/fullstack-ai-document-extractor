import Link from "next/link";

export default function DownloadButtons({
  id,
}: {
  id: string;
}) {
  const API = process.env.NEXT_PUBLIC_API_URL;

  return (
    <div className="flex gap-3">
      <Link
        href={`${API}/api/documents/${id}/markdown`}
        className="px-4 py-2 bg-blue-600 rounded-xl"
      >
        Download MD
      </Link>

      <Link
        href={`${API}/api/documents/${id}/json`}
        className="px-4 py-2 bg-green-600 rounded-xl"
      >
        Download JSON
      </Link>
    </div>
  );
}