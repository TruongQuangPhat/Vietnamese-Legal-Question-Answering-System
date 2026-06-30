type ChatSidebarProps = {
  onNewChat: () => void;
};

export function ChatSidebar({ onNewChat }: ChatSidebarProps) {
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
        <div className="rounded-md border border-dashed border-border bg-surface p-3 text-sm leading-6 text-muted">
          <p className="font-medium text-ink">Cuộc trò chuyện hiện tại</p>
          <p className="mt-1">Lịch sử sẽ được lưu ở bước sau.</p>
        </div>
        <p className="mt-auto pt-4 text-xs leading-5 text-muted">
          Công cụ hỗ trợ nghiên cứu pháp luật, không thay thế tư vấn pháp lý
          chuyên nghiệp.
        </p>
      </div>
    </aside>
  );
}
