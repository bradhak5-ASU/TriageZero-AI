import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { useToast } from '../../context/ToastContext';

interface CopyButtonProps {
  text: string;
  label?: string;
}

export function CopyButton({ text, label = 'Copy to clipboard' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);
  const { pushToast } = useToast();

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      pushToast('Clipboard unavailable in this browser', 'warn');
    }
  };

  return (
    <button
      type="button"
      className="icon-btn"
      onClick={copy}
      aria-label={copied ? 'Copied' : label}
      title={copied ? 'Copied' : label}
      style={{ width: 26, height: 26 }}
    >
      {copied ? (
        <Check size={13} style={{ color: 'var(--ok)' }} aria-hidden />
      ) : (
        <Copy size={13} aria-hidden />
      )}
    </button>
  );
}
