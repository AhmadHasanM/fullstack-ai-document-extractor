"use client";

import { useState, useEffect, useCallback } from "react";
import {
  ChatLayout,
  ChatSidebar,
  ChatMessages,
  ChatInput,
} from "@/components/chat";
import { authFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL;

type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
};

type ChatSession = {
  id: string;
  document_id?: string;
  title: string;
  created_at: string;
  updated_at: string;
};

type Document = {
  id: string;
  filename?: string;
  original_filename?: string;
  status?: string;
};

// Sample initial messages
const INITIAL_MESSAGES: Message[] = [
  {
    id: "welcome",
    role: "assistant",
    content: "Hello! I'm your AI document assistant. You can ask me questions about your uploaded documents, request summaries, extract specific information, or help with any content analysis.\n\n**How to use:**\n• Select a document from the sidebar to chat with it specifically\n• Or ask general questions about all your documents\n• Create a new chat session to start fresh\n\nHow can I help you today?",
    timestamp: "2024-01-01T00:00:00.000Z",
  },
];

export default function ChatPage() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [showSidebar, setShowSidebar] = useState(true);

  // Load documents for RAG context
  useEffect(() => {
    async function loadDocs() {
      try {
        const token = localStorage.getItem("auth_token");
        const res = await fetch(`${API}/api/documents`, {
          cache: "no-store",
          headers: token ? { Authorization: `Bearer ${token}` } : {}
        });
        const data = await res.json();
        const list = Array.isArray(data)
          ? data
          : Array.isArray(data?.documents)
          ? data.documents
          : [];
        setDocuments(list.filter((d: Document) => d.status === "completed"));
      } catch (e) {
        console.error("Failed to load documents:", e);
      }
    }
    loadDocs();
  }, []);

  // Load chat sessions
  useEffect(() => {
    async function loadSessions() {
      try {
        const token = localStorage.getItem("auth_token");
        const res = await fetch(`${API}/api/chat/sessions`, {
          cache: "no-store",
          headers: token ? { Authorization: `Bearer ${token}` } : {}
        });
        if (res.ok) {
          const data = await res.json();
          setSessions(data.sessions || []);
        }
      } catch (e) {
        console.error("Failed to load sessions:", e);
      }
    }
    loadSessions();
  }, []);

  // Load session history when session is selected
  const loadSessionHistory = useCallback(async (sessionId: string) => {
    try {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${API}/api/chat/sessions/${sessionId}/history`, {
        cache: "no-store",
        headers: token ? { Authorization: `Bearer ${token}` } : {}
      });
      if (res.ok) {
        const data = await res.json();
        if (data.messages && data.messages.length > 0) {
          setMessages(
            data.messages.map((m: { id: string; role: string; message: string; created_at: string }) => ({
              id: m.id,
              role: m.role as "user" | "assistant",
              content: m.message,
              timestamp: m.created_at,
            }))
          );
        } else {
          setMessages(INITIAL_MESSAGES);
        }
      }
    } catch (e) {
      console.error("Failed to load session history:", e);
      setMessages(INITIAL_MESSAGES);
    }
  }, []);

  // Handle new chat - create a new session
  async function handleNewChat() {
    try {
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${API}/api/chat/sessions`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          title: "New Chat",
          document_id: selectedDocId,
        }),
      });

      if (res.ok) {
        const data = await res.json();
        setCurrentSessionId(data.session_id);
        setMessages(INITIAL_MESSAGES);

        // Refresh sessions list
        const sessionsRes = await fetch(`${API}/api/chat/sessions`, {
          cache: "no-store",
          headers: token ? { Authorization: `Bearer ${token}` } : {}
        });
        if (sessionsRes.ok) {
          const sessionsData = await sessionsRes.json();
          setSessions(sessionsData.sessions || []);
        }
      }
    } catch (e) {
      console.error("Failed to create session:", e);
    }
  }

  // Handle session selection
  function handleSelectSession(sessionId: string) {
    setCurrentSessionId(sessionId);
    loadSessionHistory(sessionId);
  }

  // Handle document selection
  function handleSelectDocument(docId: string | null) {
    setSelectedDocId(docId);
  }

  // Handle sidebar toggle
  function handleToggleSidebar() {
    setShowSidebar(!showSidebar);
  }

  // Handle send message - through backend
  async function sendMessage() {
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input.trim(),
      timestamp: new Date().toISOString(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      let responseText: string;
      let sessionId = currentSessionId;
      const token = localStorage.getItem("auth_token");

      // If no session, create one through backend
      if (!sessionId) {
        const createRes = await fetch(`${API}/api/chat/sessions`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {})
          },
          body: JSON.stringify({
            title: input.trim().substring(0, 50),
            document_id: selectedDocId,
          }),
        });

        if (createRes.ok) {
          const sessionData = await createRes.json();
          sessionId = sessionData.session_id;
          setCurrentSessionId(sessionId);

          // Refresh sessions
          const sessionsRes = await fetch(`${API}/api/chat/sessions`, {
            cache: "no-store",
            headers: token ? { Authorization: `Bearer ${token}` } : {}
          });
          if (sessionsRes.ok) {
            const sessionsData = await sessionsRes.json();
            setSessions(sessionsData.sessions || []);
          }
        } else {
          throw new Error("Failed to create session");
        }
      }

      // Call backend API which will call AI service
      const res = await fetch(`${API}/api/chat/sessions/${sessionId}/messages`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {})
        },
        body: JSON.stringify({
          document_id: selectedDocId || "",
          session_id: sessionId,
          message: input.trim(),
        }),
      });

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(`Backend error: ${res.status} - ${errorText}`);
      }

      const data = await res.json();
      responseText = data.response;

      const aiResponse: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: responseText,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, aiResponse]);
    } catch (e: unknown) {
      console.error("Chat error:", e);
      const errorMessage = e instanceof Error ? e.message : "Unknown error";

      const errorResponse: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `I apologize, but I'm having trouble processing your request right now.\n\nError: ${errorMessage}\n\nMake sure:\n• Backend is running on port 8080\n• AI service is running on port 8000\n• You have uploaded and processed some documents`,
        timestamp: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, errorResponse]);
    } finally {
      setIsLoading(false);
    }
  }

  const sidebar = (
    <ChatSidebar
      sessions={sessions}
      currentSessionId={currentSessionId}
      documents={documents}
      selectedDocId={selectedDocId}
      onNewChat={handleNewChat}
      onSelectSession={handleSelectSession}
      onSelectDocument={handleSelectDocument}
    />
  );

  const chatContent = (
    <>
      <ChatMessages messages={messages} isLoading={isLoading} />
      <ChatInput
        value={input}
        onChange={setInput}
        onSend={sendMessage}
        isLoading={isLoading}
      />
    </>
  );

  return (
    <ChatLayout
      sidebar={sidebar}
      showSidebar={showSidebar}
      onToggleSidebar={handleToggleSidebar}
    >
      {chatContent}
    </ChatLayout>
  );
}