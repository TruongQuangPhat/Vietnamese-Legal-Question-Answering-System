import { LegalQAWorkspace } from "@/components/legal-qa/legal-qa-workspace";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-canvas text-ink">
      <section className="mx-auto flex min-h-screen w-full max-w-7xl flex-col px-3 py-3 md:px-5 md:py-5">
        <LegalQAWorkspace />
      </section>
    </main>
  );
}
