import { ReactNode } from "react";

type ChatLayoutProps = {
  sidebar: ReactNode;
  children: ReactNode;
  showSidebar: boolean;
  onToggleSidebar: () => void;
};

export function ChatLayout({ sidebar, children, showSidebar, onToggleSidebar }: ChatLayoutProps) {
  return (
    <main className="h-[calc(100vh-120px)] flex">
      {/* Sidebar */}
      <div className={`${showSidebar ? "block" : "hidden"} lg:block`}>
        {sidebar}
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col">
        {/* Mobile Sidebar Toggle */}
        <div className="lg:hidden p-4 border-b border-hairline">
          <button
            onClick={onToggleSidebar}
            className="text-sm text-black/60 hover:text-black"
          >
            {showSidebar ? "Hide" : "Show"} sidebar
          </button>
        </div>

        {children}
      </div>
    </main>
  );
}