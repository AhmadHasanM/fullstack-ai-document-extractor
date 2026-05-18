import Link from "next/link";

export default function HistoryTable({
  data,
}: {
  data: any[];
}) {
  return (
    <table className="w-full text-left">
      <thead>
        <tr>
          <th>ID</th>
          <th>File</th>
          <th>Status</th>
          <th></th>
        </tr>
      </thead>

      <tbody>
        {data.map((item) => (
          <tr key={item.id}>
            <td>{item.id}</td>
            <td>{item.filename}</td>
            <td>{item.status}</td>
            <td>
              <Link href={`/file/${item.id}`}>
                View
              </Link>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}