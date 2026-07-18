import { expect, test, type Page } from "@playwright/test";

const API_ORIGIN = "https://vnlaw-backend-prod-phat.azurewebsites.net";
const ASK_URL = `${API_ORIGIN}/api/v1/legal-qa/ask`;
const QUESTION = "Hợp đồng dân sự vô hiệu khi nào?";
const ANSWER = "Câu trả lời kiểm thử.";
const UX_ANSWER =
  "Hợp đồng dân sự có thể vô hiệu khi vi phạm điều kiện có hiệu lực [E1] hoặc do giả tạo [E2].";

test("submit sends ask and renders answer when conversation sync fails", async ({
  page,
}) => {
  const consoleWarnings: string[] = [];
  let askRequests = 0;
  const observedRequests = recordRequestPaths(page);

  page.on("console", (message) => {
    if (message.type() === "warning") {
      consoleWarnings.push(message.text());
    }
  });
  await mockConversationFailure(page);
  await mockAskSuccess(page, () => {
    askRequests += 1;
  });

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await submitQuestion(page);

  await expect(page.getByText(ANSWER)).toBeVisible();
  await expect(page.getByText("Không gửi được yêu cầu")).toHaveCount(0);
  expect(askRequests, diagnosticMessage(observedRequests)).toBe(1);
  expect(consoleWarnings).toContain(
    "Conversation backend sync failed during create.",
  );
});

test("submit shows send error only when ask fails", async ({ page }) => {
  let askRequests = 0;
  const observedRequests = recordRequestPaths(page);

  await mockConversationFailure(page);
  await mockAskFailure(page, () => {
    askRequests += 1;
  });

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await submitQuestion(page);

  await expect(page.getByText("Không gửi được yêu cầu")).toBeVisible();
  await expect(
    page.getByText("Không thể nhận câu trả lời lúc này. Vui lòng thử lại."),
  ).toBeVisible();
  expect(askRequests, diagnosticMessage(observedRequests)).toBe(1);
});

test("enter key submit sends ask when conversation sync fails", async ({
  page,
}) => {
  let askRequests = 0;
  const observedRequests = recordRequestPaths(page);

  await mockConversationFailure(page);
  await mockAskSuccess(page, () => {
    askRequests += 1;
  });

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.getByRole("button", { name: "+ Cuộc trò chuyện mới" }).click();
  await page.getByLabel("Câu hỏi pháp lý").fill(QUESTION);
  await page.getByLabel("Câu hỏi pháp lý").press("Enter");

  await expect(page.getByText(ANSWER)).toBeVisible();
  await expect(page.getByText("Không gửi được yêu cầu")).toHaveCount(0);
  expect(askRequests, diagnosticMessage(observedRequests)).toBe(1);
});

test("submit still sends ask when browser storage throws", async ({ page }) => {
  let askRequests = 0;
  const observedRequests = recordRequestPaths(page);

  await page.addInitScript(() => {
    const throwStorageError = () => {
      throw new Error("storage unavailable");
    };
    Storage.prototype.getItem = throwStorageError;
    Storage.prototype.setItem = throwStorageError;
    Storage.prototype.clear = throwStorageError;
  });
  await mockConversationFailure(page);
  await mockAskSuccess(page, () => {
    askRequests += 1;
  });

  await page.goto("/");
  await submitQuestion(page);

  await expect(page.getByText(ANSWER)).toBeVisible();
  await expect(page.getByText("Không gửi được yêu cầu")).toHaveCount(0);
  expect(askRequests, diagnosticMessage(observedRequests)).toBe(1);
});

test("restored stale send error does not block a new submit", async ({ page }) => {
  let askRequests = 0;
  const observedRequests = recordRequestPaths(page);

  await page.addInitScript(() => {
    window.localStorage.setItem(
      "legal-qa-chat-conversations",
      JSON.stringify({
        version: 1,
        conversations: [
          {
            id: "failed-conversation",
            title: "Failed conversation",
            createdAt: "2026-07-18T00:00:00.000Z",
            updatedAt: "2026-07-18T00:00:00.000Z",
            messages: [
              {
                id: "failed-user-message",
                role: "user",
                content: "Câu hỏi cũ",
                createdAt: "2026-07-18T00:00:00.000Z",
              },
              {
                id: "failed-assistant-message",
                role: "assistant",
                content: "Không thể nhận câu trả lời lúc này. Vui lòng thử lại.",
                createdAt: "2026-07-18T00:00:01.000Z",
                status: "error",
                errorMessage:
                  "Không thể nhận câu trả lời lúc này. Vui lòng thử lại.",
              },
            ],
          },
        ],
      }),
    );
    window.sessionStorage.clear();
  });
  await mockConversationFailure(page);
  await mockAskSuccess(page, () => {
    askRequests += 1;
  });

  await page.goto("/");
  await page.getByRole("button", { name: "+ Cuộc trò chuyện mới" }).click();
  await page.getByLabel("Câu hỏi pháp lý").fill(QUESTION);
  await page.getByRole("button", { name: "Gửi" }).click();

  await expect(page.getByText(ANSWER)).toBeVisible();
  await expect(page.getByText("Không gửi được yêu cầu")).toHaveCount(0);
  expect(askRequests, diagnosticMessage(observedRequests)).toBe(1);
});

test("message sync failure after conversation create does not block ask", async ({
  page,
}) => {
  let askRequests = 0;
  const observedRequests = recordRequestPaths(page);

  await mockConversationMessageFailure(page);
  await mockAskSuccess(page, () => {
    askRequests += 1;
  });

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await submitQuestion(page);

  await expect(page.getByText(ANSWER)).toBeVisible();
  await expect(page.getByText("Không gửi được yêu cầu")).toHaveCount(0);
  expect(askRequests, diagnosticMessage(observedRequests)).toBe(1);
});

test("suggested prompt path sends ask", async ({ page }) => {
  let askRequests = 0;
  const observedRequests = recordRequestPaths(page);

  await mockConversationFailure(page);
  await mockAskSuccess(page, () => {
    askRequests += 1;
  });

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page
    .getByRole("button", {
      name: "Điều kiện kết hôn theo pháp luật Việt Nam là gì?",
    })
    .click();
  await page.getByRole("button", { name: "Gửi" }).click();

  await expect(page.getByText(ANSWER)).toBeVisible();
  await expect(page.getByText("Không gửi được yêu cầu")).toHaveCount(0);
  expect(askRequests, diagnosticMessage(observedRequests)).toBe(1);
});

test("loading answer shows spinner and current safe process stage", async ({
  page,
}) => {
  await mockConversationFailure(page);
  await mockAskDelayedSuccess(page);

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await page.getByRole("button", { name: "+ Cuộc trò chuyện mới" }).click();
  await page.getByLabel("Câu hỏi pháp lý").fill(QUESTION);
  await page.getByRole("button", { name: "Gửi" }).click();

  await expect(page.getByText("Đang xử lý câu hỏi")).toBeVisible();
  await expect(page.getByTestId("process-spinner")).toBeVisible();
  await expect(page.locator("[data-active-stage='true']")).toContainText(
    /Đang .+\.\.\./,
  );
});

test("answer shows user-friendly legal basis drawer without technical metadata", async ({
  page,
}) => {
  await mockConversationFailure(page);
  await mockAskLegalBasisSuccess(page);

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await submitQuestion(page);

  await expect(page.getByText(UX_ANSWER.split(" [E1]")[0])).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Đã sử dụng 2 căn cứ pháp lý" }),
  ).toBeVisible();
  await expect(page.getByText("caution_evidence_selected")).toHaveCount(0);
  await expect(page.getByText("auxiliary_parent_context_included")).toHaveCount(0);
  await expect(
    page.getByText("Một số căn cứ cần được xem xét thận trọng."),
  ).toHaveCount(0);
  await expect(
    page.getByText("Một số ngữ cảnh bổ trợ đã được dùng để hiểu căn cứ."),
  ).toHaveCount(0);
  await expect(page.getByText("Lưu ý")).toHaveCount(0);

  await page
    .getByRole("button", { name: "Đã sử dụng 2 căn cứ pháp lý" })
    .click();

  await expect(page.getByRole("dialog", { name: "Căn cứ pháp lý" })).toBeVisible();
  await expect(page.getByText("2 căn cứ được sử dụng")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Bộ luật Dân sự 2015, Điều 117" }),
  ).toBeVisible();
  await expect(
    page.getByText("Giao dịch dân sự có hiệu lực khi chủ thể có năng lực pháp luật."),
  ).toBeVisible();
  await expect(page.getByText("Evidence ID")).toHaveCount(0);
  await expect(page.getByText("Chunk ID")).toHaveCount(0);
  await expect(page.getByText("Score")).toHaveCount(0);
  await expect(page.getByText("test-chunk-1")).toHaveCount(0);
  await expect(page.getByText("0.987")).toHaveCount(0);
});

test("inline citation chip opens and highlights matching legal basis", async ({
  page,
}) => {
  await mockConversationFailure(page);
  await mockAskLegalBasisSuccess(page);

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await submitQuestion(page);

  await page.getByRole("button", { name: "Mở căn cứ pháp lý E2" }).click();

  await expect(page.getByRole("dialog", { name: "Căn cứ pháp lý" })).toBeVisible();
  await expect(page.locator("[data-highlighted='true']")).toContainText("Căn cứ 2");
  await expect(page.locator("[data-highlighted='true']")).toContainText(
    "Điều 124",
  );
});

test("severe retrieval warning uses friendly wording without raw warning code", async ({
  page,
}) => {
  await mockConversationFailure(page);
  await mockAskLegalBasisSuccess(page, {
    warnings: ["dense_retrieval_fallback_used"],
    metadata: {
      fallback_used: true,
      dense_retrieval_fallback_used: true,
      dense_retrieval_used: false,
    },
  });

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await submitQuestion(page);

  await expect(page.getByText("dense_retrieval_fallback_used")).toHaveCount(0);
  await expect(
    page.getByText(
      "Quá trình tìm căn cứ gặp vấn đề, câu trả lời có thể cần kiểm tra lại.",
    ),
  ).toBeVisible();
});

test("process panel expands to safe system summary only", async ({ page }) => {
  await mockConversationFailure(page);
  await mockAskLegalBasisSuccess(page);

  await page.goto("/");
  await page.evaluate(() => {
    localStorage.clear();
    sessionStorage.clear();
  });
  await submitQuestion(page);

  await expect(page.getByText("Đã tìm căn cứ pháp lý và tạo câu trả lời.")).toBeVisible();
  await expect(page.getByText("Tiếp nhận câu hỏi")).toHaveCount(0);
  await expect(page.getByText("1. Tiếp nhận câu hỏi")).toHaveCount(0);

  await page.getByRole("button", { name: /Xem quá trình/ }).click();

  await expect(page.getByText("Tiếp nhận câu hỏi")).toBeVisible();
  await expect(page.getByText("Đã dùng chế độ tìm kiếm kết hợp.")).toBeVisible();
  await expect(page.getByText("Không dùng chế độ dự phòng.")).toBeVisible();
  await expect(page.getByText("dense_retrieval_used")).toHaveCount(0);
  await expect(page.getByText("fallback_used")).toHaveCount(0);
  await expect(page.getByText("embedding_model_cache_hit")).toHaveCount(0);
  await expect(page.getByText("model_cache_key")).toHaveCount(0);
  await expect(page.getByText("Chain of Thought")).toHaveCount(0);
  await expect(page.getByText("Suy luận nội bộ")).toHaveCount(0);
  await expect(page.getByText("Lý luận ẩn")).toHaveCount(0);
});

async function submitQuestion(page: Page): Promise<void> {
  await page.getByRole("button", { name: "+ Cuộc trò chuyện mới" }).click();
  await page.getByLabel("Câu hỏi pháp lý").fill(QUESTION);
  await page.getByRole("button", { name: "Gửi" }).click();
}

async function mockConversationFailure(page: Page): Promise<void> {
  await page.route(`${API_ORIGIN}/api/v1/conversations**`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      status: 503,
      body: JSON.stringify({ detail: "conversation sync unavailable" }),
    });
  });
}

async function mockConversationMessageFailure(page: Page): Promise<void> {
  await page.route(`${API_ORIGIN}/api/v1/conversations`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      status: 200,
      body: JSON.stringify({
        id: "backend-conversation-id",
        title: "Test conversation",
        created_at: "2026-07-18T00:00:00.000Z",
        updated_at: "2026-07-18T00:00:00.000Z",
        message_count: 0,
      }),
    });
  });
  await page.route(
    `${API_ORIGIN}/api/v1/conversations/backend-conversation-id/messages`,
    async (route) => {
      await route.fulfill({
        contentType: "application/json",
        status: 503,
        body: JSON.stringify({ detail: "message sync unavailable" }),
      });
    },
  );
}

async function mockAskSuccess(
  page: Page,
  onAsk: () => void,
): Promise<void> {
  await page.route(ASK_URL, async (route) => {
    expect(route.request().method()).toBe("POST");
    onAsk();
    await route.fulfill({
      contentType: "application/json",
      status: 200,
      body: JSON.stringify({
        request_id: "test-request-id",
        decision: "answered",
        answer: ANSWER,
        citations: [
          {
            evidence_id: "E1",
            chunk_id: "test-chunk",
            law_id: "BLDS_2015",
            law_name: "Bộ luật Dân sự 2015",
            citation: "Bộ luật Dân sự 2015, Điều 1",
            source_url: "https://example.test",
            hierarchy_path: "Điều 1",
          },
        ],
        evidence: [],
        warnings: [],
        metadata: {
          retrieval_strategy: "coverage_aware_quota",
          model: "google/gemini-2.5-flash",
          reranking_used: false,
          latency_ms: 1234,
          conversation_context_used: false,
          conversation_context_message_count: 0,
          follow_up_detected: false,
          retrieval_question_prepared: false,
        },
      }),
    });
  });
}

async function mockAskFailure(page: Page, onAsk: () => void): Promise<void> {
  await page.route(ASK_URL, async (route) => {
    expect(route.request().method()).toBe("POST");
    onAsk();
    await route.fulfill({
      contentType: "application/json",
      status: 503,
      body: JSON.stringify({ detail: "ask unavailable" }),
    });
  });
}

async function mockAskDelayedSuccess(page: Page): Promise<void> {
  await page.route(ASK_URL, async (route) => {
    expect(route.request().method()).toBe("POST");
    await new Promise((resolve) => {
      setTimeout(resolve, 2500);
    });
    await route.fulfill({
      contentType: "application/json",
      status: 200,
      body: JSON.stringify({
        request_id: "test-request-id",
        decision: "answered",
        answer: ANSWER,
        citations: [],
        evidence: [],
        warnings: [],
        metadata: {
          retrieval_strategy: "coverage_aware_quota",
          retrieval_mode: "hybrid",
          model: "google/gemini-2.5-flash",
          reranking_used: false,
          latency_ms: 1234,
          conversation_context_used: false,
          conversation_context_message_count: 0,
          follow_up_detected: false,
          retrieval_question_prepared: false,
          dense_retrieval_used: true,
          dense_retrieval_fallback_used: false,
          fallback_used: false,
          embedding_model_cache_hit: true,
          embedding_model_loaded_before_request: true,
          model_cache_key: "bge-m3:test",
        },
      }),
    });
  });
}

type AskResponseOverride = {
  warnings?: string[];
  metadata?: Record<string, unknown>;
};

async function mockAskLegalBasisSuccess(
  page: Page,
  override: AskResponseOverride = {},
): Promise<void> {
  await page.route(ASK_URL, async (route) => {
    expect(route.request().method()).toBe("POST");
    await route.fulfill({
      contentType: "application/json",
      status: 200,
      body: JSON.stringify({
        request_id: "test-request-id",
        decision: "answered",
        answer: UX_ANSWER,
        citations: [
          {
            evidence_id: "E1",
            chunk_id: "test-chunk-1",
            law_id: "BLDS_2015",
            law_name: "Bộ luật Dân sự 2015",
            citation: "Bộ luật Dân sự 2015, Điều 117",
            source_url: "https://example.test/dieu-117",
            hierarchy_path: "Điều 117",
          },
          {
            evidence_id: "E2",
            chunk_id: "test-chunk-2",
            law_id: "BLDS_2015",
            law_name: "Bộ luật Dân sự 2015",
            citation: "Bộ luật Dân sự 2015, Điều 124",
            source_url: "https://example.test/dieu-124",
            hierarchy_path: "Điều 124",
          },
        ],
        evidence: [
          {
            evidence_id: "E1",
            chunk_id: "test-chunk-1",
            law_id: "BLDS_2015",
            law_name: "Bộ luật Dân sự 2015",
            citation: "Bộ luật Dân sự 2015, Điều 117",
            text:
              "Giao dịch dân sự có hiệu lực khi chủ thể có năng lực pháp luật.",
            source_url: "https://example.test/dieu-117",
            score: 0.987,
          },
          {
            evidence_id: "E2",
            chunk_id: "test-chunk-2",
            law_id: "BLDS_2015",
            law_name: "Bộ luật Dân sự 2015",
            citation: "Bộ luật Dân sự 2015, Điều 124",
            text:
              "Giao dịch dân sự giả tạo có thể bị tuyên vô hiệu theo quy định.",
            source_url: "https://example.test/dieu-124",
            score: 0.876,
          },
        ],
        warnings: override.warnings ?? [
          "caution_evidence_selected",
          "caution_evidence_selected",
          "auxiliary_parent_context_included",
        ],
        metadata: {
          retrieval_strategy: "coverage_aware_quota",
          retrieval_mode: "hybrid",
          model: "google/gemini-2.5-flash",
          reranking_used: false,
          latency_ms: 1234,
          conversation_context_used: false,
          conversation_context_message_count: 0,
          follow_up_detected: false,
          retrieval_question_prepared: false,
          dense_retrieval_used: true,
          dense_retrieval_fallback_used: false,
          fallback_used: false,
          embedding_model_cache_hit: true,
          embedding_model_loaded_before_request: true,
          model_cache_key: "bge-m3:test",
          ...override.metadata,
        },
      }),
    });
  });
}

function recordRequestPaths(page: Page): string[] {
  const observedRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    observedRequests.push(`${request.method()} ${url.origin}${url.pathname}`);
  });
  return observedRequests;
}

function diagnosticMessage(observedRequests: string[]): string {
  return [
    "Expected exactly one ask request.",
    `Observed requests: ${observedRequests.join(", ")}`,
  ].join(" ");
}
