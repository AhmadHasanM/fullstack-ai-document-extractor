type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
};

type ChatMessageProps = {
  message: Message;
};

function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    // Use UTC to avoid timezone differences between server and client
    const date = new Date(iso);
    if (isNaN(date.getTime())) return "";
    const hours = date.getUTCHours();
    const minutes = date.getUTCMinutes();
    const ampm = hours >= 12 ? "PM" : "AM";
    const displayHours = hours % 12 || 12;
    const displayMinutes = minutes.toString().padStart(2, "0");
    return `${displayHours}:${displayMinutes} ${ampm}`;
  } catch {
    return "";
  }
}

export function ChatMessage({ message }: ChatMessageProps) {
  return (
    <div className={`flex gap-4 ${message.role === "user" ? "flex-row-reverse" : ""}`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
          message.role === "assistant"
            ? "bg-black text-white"
            : "bg-surface-soft text-black/60"
        }`}
      >
        {message.role === "assistant" ? (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        ) : (
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        )}
      </div>

      {/* Message Content */}
      <div className={`max-w-[70%] ${message.role === "user" ? "text-right" : ""}`}>
        <div
          className={`p-4 rounded-2xl text-body-sm ${
            message.role === "user"
              ? "bg-black text-white"
              : "bg-surface-soft text-black"
          }`}
        >
          <div className="prose prose-sm max-w-none">
            {message.content.split("\n").map((line, i) => {
              if (line.startsWith("**") && line.endsWith("**")) {
                return <p key={i} className="font-bold mb-1">{line.replace(/\*\*/g, "")}</p>;
              }
              if (line.startsWith("• ") || line.startsWith("- ")) {
                return <p key={i} className="ml-2 mb-1">• {line.slice(2)}</p>;
              }
              if (line.startsWith("> ")) {
                return <p key={i} className="italic border-l-2 border-black/20 pl-2 my-2">{line.slice(2)}</p>;
              }
              if (line.startsWith("1. ") || line.startsWith("2. ") || line.startsWith("3. ")) {
                return <p key={i} className="ml-2 mb-1">{line}</p>;
              }
              if (line.trim() === "") {
                return <br key={i} />;
              }
              return <p key={i} className="mb-1">{line}</p>;
            })}
          </div>
        </div>
        <p className="text-xs text-black/30 mt-1">{formatTime(message.timestamp)}</p>
      </div>
    </div>
  );
}