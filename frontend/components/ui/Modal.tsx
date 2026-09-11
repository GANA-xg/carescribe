'use client';

import { forwardRef, useEffect, useRef } from 'react';
import { cn } from '../../lib/utils';
import { X } from 'lucide-react';

export interface ModalProps {
  children: React.ReactNode;
  isOpen: boolean;
  onClose: () => void;
  className?: string;
  title?: string;
}

const Modal = forwardRef<HTMLDivElement, ModalProps>(
  ({ children, isOpen, onClose, className, title }, ref) => {
    const modalRef = useRef<HTMLDivElement>(null);
    const backdropRef = useRef<HTMLDivElement>(null);

    // Close on escape key
    useEffect(() => {
      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === 'Escape') {
          onClose();
        }
      };

      if (isOpen) {
        document.addEventListener('keydown', handleEscape);
        document.body.style.overflow = 'hidden';
      }

      return () => {
        document.removeEventListener('keydown', handleEscape);
        document.body.style.overflow = 'unset';
      };
    }, [isOpen, onClose]);

    if (!isOpen) return null;

    return (
      <div
        ref={backdropRef}
        className="fixed inset-0 z-50 flex items-center justify-center bg-[var(--color-scrim)]"
        onClick={onClose}
      >
        <div
          ref={modalRef}
          className={cn(
            'relative mx-auto w-full max-w-lg rounded-[var(--rounded-md)] bg-white p-[var(--space-lg)]',
            'shadow-card',
            className
          )}
          onClick={(e) => e.stopPropagation()}
        >
          {title && (
            <div className="flex items-center justify-between mb-[var(--space-base)]">
              <h2 className="text-display-sm text-[var(--color-ink)]">{title}</h2>
              <button
                onClick={onClose}
                className="flex h-32 w-32 items-center justify-center rounded-full hover:bg-[var(--color-surface-soft)]"
                aria-label="Close modal"
              >
                <X className="h-4 w-4 text-[var(--color-muted)]" />
              </button>
            </div>
          )}
          {children}
        </div>
      </div>
    );
  }
);

Modal.displayName = 'Modal';

export { Modal };