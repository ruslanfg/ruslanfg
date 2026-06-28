// Persistent, always-on-screen disclaimer, restyled as a fixed broadcast ribbon.
// Content, persistence (fixed bottom), and full contrast are unchanged — outputs
// are statistical estimates and public market data for information only.
export function Disclaimer({ text }: { text: string }) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-amber-500/25 chrome-glass bg-ink-950/90">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2 sm:px-6">
        <span className="hidden shrink-0 font-display text-[10px] uppercase tracking-[0.1em] text-amber-300 sm:inline">
          Info only · Not betting advice
        </span>
        <span className="hidden h-3 w-px shrink-0 bg-amber-500/30 sm:inline" />
        <p className="text-[11px] leading-snug text-amber-200/85">
          <span className="font-semibold text-amber-200 sm:hidden">ⓘ Information only — </span>
          {text}
        </p>
      </div>
    </div>
  );
}
