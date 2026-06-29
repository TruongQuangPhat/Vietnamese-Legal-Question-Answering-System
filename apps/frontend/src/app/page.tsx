import { LegalQAWorkspace } from "@/components/legal-qa/legal-qa-workspace";
import { getApiBaseUrl } from "@/lib/api-config";

export default function HomePage() {
  const apiBaseUrl = getApiBaseUrl();

  return (
    <main className="min-h-screen bg-canvas text-ink">
      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-6 py-8">
        <header className="border-b border-border pb-6">
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
        </header>

        <LegalQAWorkspace apiBaseUrl={apiBaseUrl} />
      </section>
    </main>
  );
}
