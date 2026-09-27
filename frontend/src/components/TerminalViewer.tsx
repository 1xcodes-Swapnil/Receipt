import { useState } from 'react';
import { Terminal, Copy, Check } from 'lucide-react';

interface Props {
  command?: string | null;
  output?: string | null;
  title?: string;
}

export function TerminalViewer({ command, output, title = 'Terminal Execution Output' }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    const textToCopy = `${command ? `$ ${command}\n\n` : ''}${output ?? ''}`;
    navigator.clipboard.writeText(textToCopy);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="bg-brand-950 text-gray-200 rounded-2xl overflow-hidden border border-brand-800 shadow-soft-xl font-mono text-xs">
      <div className="bg-brand-900/90 px-4 py-2.5 border-b border-brand-800 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-rose-500/80 inline-block" />
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500/80 inline-block" />
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500/80 inline-block" />
          </div>
          <span className="text-gray-400 text-xs font-sans font-medium flex items-center gap-1.5 ml-2">
            <Terminal className="w-3.5 h-3.5 text-brand-300" />
            {title}
          </span>
        </div>
        <button
          onClick={handleCopy}
          className="text-gray-400 hover:text-white transition-colors p-1 rounded hover:bg-brand-800 flex items-center gap-1 text-[11px]"
          title="Copy output"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-emerald-400 font-sans">Copied!</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span className="font-sans">Copy</span>
            </>
          )}
        </button>
      </div>

      <div className="p-4 space-y-3 overflow-x-auto max-h-[360px] scrollbar-thin">
        {command && (
          <div className="flex items-start gap-2 text-emerald-400 bg-brand-900/40 p-2.5 rounded-lg border border-brand-800/60">
            <span className="text-brand-400 font-bold select-none">$</span>
            <span className="font-semibold break-all">{command}</span>
          </div>
        )}
        {output ? (
          <pre className="text-gray-300 leading-relaxed whitespace-pre-wrap break-words">
            {output}
          </pre>
        ) : (
          <div className="text-gray-500 italic py-2">No output recorded.</div>
        )}
      </div>
    </div>
  );
}
