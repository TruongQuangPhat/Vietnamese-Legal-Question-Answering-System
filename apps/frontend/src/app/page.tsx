import { getApiBaseUrl } from "@/lib/api-config";

export default function HomePage() {
  const apiBaseUrl = getApiBaseUrl();

  return (
    <main className="min-h-screen bg-canvas text-ink">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col px-6 py-8">
        <header className="flex flex-col gap-3 border-b border-border pb-6 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-primary">
              VnLaw-QA
            </p>
            <h1 className="mt-2 text-3xl font-semibold md:text-4xl">
              Vietnamese Legal QA
            </h1>
            <p className="mt-3 max-w-2xl text-base leading-7 text-muted">
              Ask Vietnamese legal questions and review cited evidence from
              trusted legal documents.
            </p>
          </div>
          <div className="rounded-md border border-border bg-surface px-4 py-3 text-sm text-muted">
            API: <span className="font-medium text-ink">{apiBaseUrl}</span>
          </div>
        </header>

        <div className="grid flex-1 gap-5 py-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <section className="rounded-md border border-border bg-surface p-5 shadow-panel">
            <div className="flex items-center justify-between gap-4 border-b border-border pb-4">
              <div>
                <h2 className="text-lg font-semibold">Question workspace</h2>
                <p className="mt-1 text-sm text-muted">
                  Question input coming next.
                </p>
                <p className="mt-1 text-sm text-muted">
                  Legal QA API client ready for the next increment.
                </p>
              </div>
              <span className="rounded-full bg-[#e8f3f1] px-3 py-1 text-xs font-medium text-primary">
                Scaffold
              </span>
            </div>

            <div className="mt-5">
              <label
                className="mb-2 block text-sm font-medium text-ink"
                htmlFor="question-preview"
              >
                Legal question
              </label>
              <textarea
                id="question-preview"
                className="min-h-44 w-full resize-none rounded-md border-border bg-[#f8fafc] text-sm text-muted"
                disabled
                placeholder="Người lao động được quyền đơn phương chấm dứt hợp đồng lao động khi nào?"
              />
              <button
                className="mt-4 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white opacity-60"
                disabled
                type="button"
              >
                Ask question
              </button>
            </div>
          </section>

          <aside className="rounded-md border border-border bg-surface p-5 shadow-panel">
            <h2 className="text-lg font-semibold">Citations and evidence</h2>
            <p className="mt-2 text-sm leading-6 text-muted">
              Citations and evidence panel coming next.
            </p>
            <div className="mt-5 space-y-3">
              <div className="rounded-md border border-dashed border-border p-4">
                <p className="text-sm font-medium">Selected evidence</p>
                <p className="mt-1 text-sm text-muted">
                  Citable child chunks will appear here after API integration.
                </p>
              </div>
              <div className="rounded-md border border-dashed border-border p-4">
                <p className="text-sm font-medium">Answer status</p>
                <p className="mt-1 text-sm text-muted">
                  Answer, fallback, and safety warnings will appear here.
                </p>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  );
}
