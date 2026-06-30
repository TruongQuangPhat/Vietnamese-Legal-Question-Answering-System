import { LegalQAWorkspace } from "@/components/legal-qa/legal-qa-workspace";
import { getApiBaseUrl } from "@/lib/api-config";

export default function HomePage() {
  const apiBaseUrl = getApiBaseUrl();

  return (
    <main className="min-h-screen bg-canvas text-ink">
      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-3 py-3 md:px-5 md:py-5">
        <LegalQAWorkspace apiBaseUrl={apiBaseUrl} />
      </section>
    </main>
  );
}
