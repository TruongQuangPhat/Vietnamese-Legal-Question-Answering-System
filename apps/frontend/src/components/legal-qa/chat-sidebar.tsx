"use client";

import { useState } from "react";
import type { Conversation } from "./chat-types";

type ChatSidebarProps = {
  activeConversationId: string | null;
  conversations: Conversation[];
  onNewChat: () => void;
  onDeleteConversation: (conversationId: string) => void;
  onRenameConversation: (conversationId: string, title: string) => void;
  onSelectConversation: (conversationId: string) => void;
};

export function ChatSidebar({
  activeConversationId,
  conversations,
  onDeleteConversation,
  onNewChat,
  onRenameConversation,
  onSelectConversation,
}: ChatSidebarProps) {
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const [editingConversationId, setEditingConversationId] = useState<
    string | null
  >(null);
  const [renameTitle, setRenameTitle] = useState("");

  function startRenaming(conversation: Conversation) {
    setOpenMenuId(null);
    setEditingConversationId(conversation.id);
    setRenameTitle(conversation.title);
  }

  function saveRename(conversation: Conversation) {
    const nextTitle = renameTitle.trim();
    setEditingConversationId(null);
    setRenameTitle("");
    if (!nextTitle || nextTitle === conversation.title) {
      return;
    }
    onRenameConversation(conversation.id, nextTitle);
  }

  function cancelRename() {
    setEditingConversationId(null);
    setRenameTitle("");
  }

  function deleteConversation(conversation: Conversation) {
    setOpenMenuId(null);
    if (editingConversationId === conversation.id) {
      cancelRename();
    }
    if (window.confirm("Xóa cuộc trò chuyện này khỏi trình duyệt?")) {
      onDeleteConversation(conversation.id);
    }
  }

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

      {conversations.length > 0 ? (
        <div className="mt-3 flex gap-2 overflow-x-auto pb-1 md:hidden">
          {conversations.map((conversation) => {
            const isActive = conversation.id === activeConversationId;
            return (
              <div
                className={`relative flex max-w-64 shrink-0 items-start gap-2 rounded-md border px-3 py-2 text-left text-sm transition ${
                  isActive
                    ? "border-primary bg-surface text-primary"
                    : "border-transparent bg-[#f8fafc] text-ink"
                }`}
                key={conversation.id}
              >
                {editingConversationId === conversation.id ? (
                  <ConversationTitleEditor
                    onCancel={cancelRename}
                    onChange={setRenameTitle}
                    onSave={() => saveRename(conversation)}
                    title={renameTitle}
                  />
                ) : (
                  <>
                    <button
                      className="min-w-0 flex-1 text-left"
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
                    <button
                      aria-expanded={openMenuId === conversation.id}
                      aria-label={`Mở menu ${conversation.title}`}
                      className="rounded-md px-2 py-1 text-xs font-semibold text-muted"
                      onClick={() =>
                        setOpenMenuId((currentId) =>
                          currentId === conversation.id ? null : conversation.id,
                        )
                      }
                      type="button"
                    >
                      ...
                    </button>
                    {openMenuId === conversation.id ? (
                      <ConversationMenu
                        onDelete={() => deleteConversation(conversation)}
                        onRename={() => startRenaming(conversation)}
                      />
                    ) : null}
                  </>
                )}
              </div>
            );
          })}
        </div>
      ) : null}

      <div className="mt-4 hidden min-h-0 flex-1 flex-col md:flex">
        <h2 className="mb-2 text-sm font-semibold text-ink">
          Lịch sử trò chuyện
        </h2>
        {conversations.length > 0 ? (
          <nav className="min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
            {conversations.map((conversation) => {
              const isActive = conversation.id === activeConversationId;
              return (
                <div
                  className={`relative w-full rounded-md border px-3 py-2 text-left text-sm transition ${
                    isActive
                      ? "border-primary bg-surface text-primary"
                      : "border-transparent text-ink hover:border-border hover:bg-surface"
                  }`}
                  key={conversation.id}
                >
                  {editingConversationId === conversation.id ? (
                    <ConversationTitleEditor
                      onCancel={cancelRename}
                      onChange={setRenameTitle}
                      onSave={() => saveRename(conversation)}
                      title={renameTitle}
                    />
                  ) : (
                    <>
                      <div className="flex items-start gap-2">
                        <button
                          className="min-w-0 flex-1 text-left"
                          onClick={() => onSelectConversation(conversation.id)}
                          type="button"
                        >
                          <span className="block truncate font-medium">
                            {conversation.title}
                          </span>
                          <span className="mt-1 block text-xs text-muted">
                            Cập nhật {formatUpdatedAt(conversation.updatedAt)}
                          </span>
                        </button>
                        <button
                          aria-expanded={openMenuId === conversation.id}
                          aria-label={`Mở menu ${conversation.title}`}
                          className="rounded-md px-2 py-1 text-xs font-semibold text-muted transition hover:bg-[#fff0f0] hover:text-[#a93434] focus:outline-none focus:ring-2 focus:ring-[#a93434]/30"
                          onClick={() =>
                            setOpenMenuId((currentId) =>
                              currentId === conversation.id
                                ? null
                                : conversation.id,
                            )
                          }
                          type="button"
                        >
                          ...
                        </button>
                      </div>
                      {openMenuId === conversation.id ? (
                        <ConversationMenu
                          onDelete={() => deleteConversation(conversation)}
                          onRename={() => startRenaming(conversation)}
                        />
                      ) : null}
                    </>
                  )}
                </div>
              );
            })}
          </nav>
        ) : null}
        <p className="mt-auto pt-4 text-xs leading-5 text-muted">
          Công cụ hỗ trợ nghiên cứu pháp luật, không thay thế tư vấn pháp lý
          chuyên nghiệp.
        </p>
      </div>
    </aside>
  );
}

type ConversationTitleEditorProps = {
  onCancel: () => void;
  onChange: (title: string) => void;
  onSave: () => void;
  title: string;
};

function ConversationTitleEditor({
  onCancel,
  onChange,
  onSave,
  title,
}: ConversationTitleEditorProps) {
  return (
    <form
      className="min-w-52 flex-1"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <input
        aria-label="Tên cuộc trò chuyện"
        autoFocus
        className="w-full rounded-md border-border bg-surface px-2 py-1 text-sm text-ink focus:border-primary focus:ring-primary"
        onChange={(event) => onChange(event.target.value)}
        onFocus={(event) => event.currentTarget.select()}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            onCancel();
          }
        }}
        value={title}
      />
      <div className="mt-2 flex items-center gap-2">
        <button
          className="rounded-md bg-primary px-2.5 py-1 text-xs font-semibold text-white hover:bg-[#164f49] focus:outline-none focus:ring-2 focus:ring-primary/30"
          type="submit"
        >
          Lưu
        </button>
        <button
          className="rounded-md border border-border bg-surface px-2.5 py-1 text-xs font-semibold text-muted hover:text-ink focus:outline-none focus:ring-2 focus:ring-primary/30"
          onClick={onCancel}
          type="button"
        >
          Hủy
        </button>
      </div>
    </form>
  );
}

type ConversationMenuProps = {
  onDelete: () => void;
  onRename: () => void;
};

function ConversationMenu({ onDelete, onRename }: ConversationMenuProps) {
  return (
    <div className="absolute right-2 top-9 z-30 w-32 rounded-md border border-border bg-surface p-1 text-sm text-ink shadow-panel">
      <button
        className="block w-full rounded px-3 py-2 text-left hover:bg-[#f8fafc] focus:outline-none focus:ring-2 focus:ring-primary/30"
        onClick={onRename}
        type="button"
      >
        Đổi tên
      </button>
      <button
        className="block w-full rounded px-3 py-2 text-left text-[#a93434] hover:bg-[#fff0f0] focus:outline-none focus:ring-2 focus:ring-[#a93434]/30"
        onClick={onDelete}
        type="button"
      >
        Xóa
      </button>
    </div>
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
