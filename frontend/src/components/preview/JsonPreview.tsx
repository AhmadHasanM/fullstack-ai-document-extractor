import Card from "../ui/Card";

export default function JsonPreview({
  data,
}: {
  data: unknown;
}) {
  return (
    <Card>
      <h3 className="mb-3 font-bold">JSON</h3>
      <pre className="text-sm overflow-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </Card>
  );
}