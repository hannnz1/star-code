import {useEffect, useId, useRef, type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {ArrowLeft, X} from 'lucide-react';
import {LanguageSwitch, ui} from '../i18n';

export function WorkspaceDialog({open, title, subtitle, onClose, busy = false, wide = false, side = false, backLabel, children}: {
  open: boolean; title: string; subtitle?: string; onClose: () => void;
  busy?: boolean; wide?: boolean; side?: boolean; backLabel?:string; children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null), titleId = useId();
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {document.body.style.overflow = previous;};
  }, [open]);
  return createPortal(<dialog ref={ref} className={'commerce-studio commerce-dialog' + (wide ? ' commerce-dialog-wide' : '') + (side ? ' crew-assistant-dialog' : '')}
    aria-labelledby={titleId} onCancel={event => {event.preventDefault(); if (!busy) onClose();}}
    onClick={event => {if (event.target === event.currentTarget && !busy) {
      const rect = event.currentTarget.getBoundingClientRect();
      if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) onClose();
    }}}>
    {open && <><header className="commerce-dialog-header"><div>
      <button className="commerce-dialog-back" disabled={busy} onClick={onClose}><ArrowLeft size={15}/>{backLabel || ui('返回看板')}</button>
      <h2 id={titleId}>{title}</h2>{subtitle && <p>{subtitle}</p>}
    </div><div className="commerce-dialog-controls"><LanguageSwitch/><button className="icon-button" disabled={busy}
      aria-label={ui('关闭任务面板')} onClick={onClose}><X size={18}/></button></div></header>
    <div className="commerce-dialog-body">{children}</div></>}
  </dialog>, document.body);
}
