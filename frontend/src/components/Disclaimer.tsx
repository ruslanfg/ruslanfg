// Persistent, always-on-screen disclaimer (fixed to the viewport bottom).
// Required: outputs are statistical estimates and public market data for
// information only — not betting advice or guaranteed outcomes.
export function Disclaimer({ text }: { text: string }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-amber-500/20 bg-ink-950/95 backdrop-blur">
      <div className="mx-auto max-w-7xl px-4 py-2 text-[11px] leading-snug text-amber-200/85 sm:px-6">
        <span className="font-semibold text-amber-200">ⓘ Information only —</span> {text}
      </div>
    </div>
  );
}
