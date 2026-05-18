type Document = {
  id: string;
  filename?: string;
  original_filename?: string;
  status?: string;
};

type DocumentSelectorProps = {
  documents: Document[];
  selectedDocId: string | null;
  onSelect: (docId: string | null) => void;
};

export function DocumentSelector({ documents, selectedDocId, onSelect }: DocumentSelectorProps) {
  return (
    <div className="mb-4">
      <label className="text-caption text-black/50 block mb-2">Active Document</label>
      <select
        value={selectedDocId || ""}
        onChange={(e) => onSelect(e.target.value || null)}
        className="w-full text-input text-sm"
      >
        <option value="">All documents</option>
        {documents.map((doc) => (
          <option key={doc.id} value={doc.id}>
            {doc.original_filename || doc.filename || "Untitled"}
          </option>
        ))}
      </select>
    </div>
  );
}