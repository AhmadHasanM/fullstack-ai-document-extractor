import Card from "../ui/Card";

export default function MarkdownPreview({
  markdown,
}: {
  markdown: string;
}) {
  return (
    <Card>
      <h3 className="mb-3 font-bold">Markdown</h3>
      <pre className="whitespace-pre-wrap text-sm">
        {markdown}
      </pre>
    </Card>
  );
}