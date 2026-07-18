import { expect, test, type Page } from "@playwright/test";

const API_ORIGIN = "https://vnlaw-backend-prod-phat.azurewebsites.net";
const ASK_URL = `${API_ORIGIN}/api/v1/legal-qa/ask`;
const QUESTION = "Hợp đồng dân sự vô hiệu khi nào?";
const ANSWER = "Câu trả lời kiểm thử.";

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
