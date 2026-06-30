import type { Conversation } from "./chat-types";

type ChatSidebarProps = {
  activeConversationId: string | null;
  conversations: Conversation[];
  onNewChat: () => void;
  onSelectConversation: (conversationId: string) => void;
};

export function ChatSidebar({
  activeConversationId,
  conversations,
  onNewChat,
  onSelectConversation,
}: ChatSidebarProps) {
  return (
    <aside className="flex min-h-0 flex-col border-b border-border bg-[#eef2f7] p-3 md:w-72 md:border-b-0 md:border-r">
      <div className="flex items-center justify-between gap-3 md:block">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">
            VnLaw-QA
          </p>
          <h1 className="mt-1 text-base font-semibold text-ink">
            Hỏi đáp pháp luật Việt Nam
          </h1>
        </div>
        <button
          className="shrink-0 rounded-md border border-border bg-surface px-3 py-2 text-sm font-semibold text-ink transition hover:border-primary hover:text-primary md:mt-4 md:w-full"
          onClick={onNewChat}
          type="button"
        >
          + Cuộc trò chuyện mới
        </button>
      </div>

      <div className="mt-4 hidden min-h-0 flex-1 flex-col md:flex">
        <h2 className="mb-2 text-sm font-semibold text-ink">
          Lịch sử trò chuyện
        </h2>
        {conversations.length > 0 ? (
          <nav className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {conversations.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              return (
                <button
                  className={`w-full rounded-md border px-3 py-2 text-left text-sm transition ${
                    isActive
                      ? "border-primary bg-surface text-primary"
                      : "border-transparent text-ink hover:border-border hover:bg-surface"
                  }`}
                  key={conversation.id}
                  onClick={() => onSelectConversation(conversation.id)}
                  type="button"
                >
                  <span className="block truncate font-medium">
                    {conversation.title}
                  </span>
                  <span className="mt-1 block text-xs text-muted">
                    {formatUpdatedAt(conversation.updatedAt)}
                  </span>
                </button>
              );
            })}
          </nav>
        ) : (
          <div className="rounded-md border border-dashed border-border bg-surface p-3 text-sm leading-6 text-muted">
            <p className="font-medium text-ink">Chưa có cuộc trò chuyện</p>
            <p className="mt-1">Các cuộc trò chuyện sẽ được lưu trên trình duyệt này.</p>
          </div>
        )}
        <p className="mt-auto pt-4 text-xs leading-5 text-muted">
          Công cụ hỗ trợ nghiên cứu pháp luật, không thay thế tư vấn pháp lý
          chuyên nghiệp.
        </p>
      </div>
    </aside>
  );
}

function formatUpdatedAt(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "";
  }
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}
