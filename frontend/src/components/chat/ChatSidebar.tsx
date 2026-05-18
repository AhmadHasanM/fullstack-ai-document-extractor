import { DocumentSelector } from "./DocumentSelector";

type ChatSession = {
  id: string;
  document_id?: string;
  title: string;
  created_at: string;
  updated_at: string;
};

// Deterministic date formatter to avoid hydration mismatch
function formatDate(iso?: string): string {
  if (!iso) return "";
  try {
    const date = new Date(iso);
    if (isNaN(date.getTime())) return "";
    // Use ISO string parsing for deterministic output
    const [year, month, day] = date.toISOString().split("T")[0].split("-");
    const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    return `${monthNames[parseInt(month, 10) - 1]} ${parseInt(day, 10)}, ${year}`;
  } catch {
    return "";
  }
}

type Document = {
  id: string;
  filename?: string;
  original_filename?: string;
  status?: string;
};

type ChatSidebarProps = {
  sessions: ChatSession[];
  currentSessionId: string | null;
  documents: Document[];
  selectedDocId: string | null;
  onNewChat: () => void;
  onSelectSession: (sessionId: string) => void;
  onSelectDocument: (docId: string | null) => void;
};

export function ChatSidebar({
  sessions,
  currentSessionId,
  documents,
  selectedDocId,
  onNewChat,
  onSelectSession,
  onSelectDocument,
}: ChatSidebarProps) {
  return (
    <aside className="w-72 border-r border-hairline bg-surface-soft flex-shrink-0">
      <div className="p-4 h-full flex flex-col">
        {/* New Chat Button */}
        <button
          onClick={onNewChat}
          className="w-full btn-primary mb-4 flex items-center justify-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
          </svg>
          New Chat
        </button>

        {/* Document Selector */}
        <DocumentSelector
          documents={documents}
          selectedDocId={selectedDocId}
          onSelect={onSelectDocument}
        />

        {/* Sessions List */}
        <div className="flex-1 overflow-auto">
          <p className="text-caption text-black/40 mb-2">Recent Chats</p>
          {sessions.length === 0 ? (
            <div className="text-sm text-black/40 py-4 text-center">
              No chat history yet
            </div>
          ) : (
            <div className="space-y-1">
              {sessions.map((session) => (
                <button
                  key={session.id}
                  onClick={() => onSelectSession(session.id)}
                  className={`w-full text-left p-2 rounded-lg text-sm transition-all ${
                    currentSessionId === session.id
                      ? "bg-black text-white"
                      : "hover:bg-white text-black/70"
                  }`}
                >
                  <p className="truncate">{session.title}</p>
                  <p className="text-xs opacity-50 truncate">
                    {formatDate(session.updated_at)}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}