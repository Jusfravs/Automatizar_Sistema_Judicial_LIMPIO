'use client';
import { cn } from '@/lib/utils';
import { AnimatePresence, Transition, motion } from 'motion/react';
import {
  Children,
  cloneElement,
  ReactElement,
  useState,
  useId,
} from 'react';

type Hijo = ReactElement<{
  'data-id': string;
  'data-checked'?: string;
  className?: string;
  children?: React.ReactNode;
  onClick?: (e: React.MouseEvent<HTMLElement>) => void;
  onMouseEnter?: (e: React.MouseEvent<HTMLElement>) => void;
  onMouseLeave?: (e: React.MouseEvent<HTMLElement>) => void;
  onFocus?: (e: React.FocusEvent<HTMLElement>) => void;
  onBlur?: (e: React.FocusEvent<HTMLElement>) => void;
}>;

export type AnimatedBackgroundProps = {
  children:
    | ReactElement<{ 'data-id': string }>[]
    | ReactElement<{ 'data-id': string }>;
  defaultValue?: string;
  onValueChange?: (newActiveId: string | null) => void;
  className?: string;
  transition?: Transition;
  enableHover?: boolean;
};

export function AnimatedBackground({
  children,
  defaultValue,
  onValueChange,
  className,
  transition,
  enableHover = false,
}: AnimatedBackgroundProps) {
  const [activeId, setActiveId] = useState<string | null>(defaultValue ?? null);
  // Sincroniza con defaultValue durante el render (patrón de React), no en un efecto.
  const [defaultVisto, setDefaultVisto] = useState(defaultValue);
  if (defaultValue !== defaultVisto) {
    setDefaultVisto(defaultValue);
    if (defaultValue !== undefined) setActiveId(defaultValue);
  }
  const uniqueId = useId();

  const handleSetActiveId = (id: string | null) => {
    setActiveId(id);

    if (onValueChange) {
      onValueChange(id);
    }
  };

  return Children.map(children, (child: Hijo, index) => {
    const id = child.props['data-id'];

    // Portal: se componen con los manejadores propios del hijo (no se pierden) y, en modo hover,
    // el foco de teclado equivale al puntero.
    const p = child.props;
    const interactionProps = enableHover
      ? {
          onMouseEnter: (e: React.MouseEvent<HTMLElement>) => {
            p.onMouseEnter?.(e);
            handleSetActiveId(id);
          },
          onMouseLeave: (e: React.MouseEvent<HTMLElement>) => {
            p.onMouseLeave?.(e);
            handleSetActiveId(null);
          },
          onFocus: (e: React.FocusEvent<HTMLElement>) => {
            p.onFocus?.(e);
            handleSetActiveId(id);
          },
          onBlur: (e: React.FocusEvent<HTMLElement>) => {
            p.onBlur?.(e);
            handleSetActiveId(null);
          },
        }
      : {
          onClick: (e: React.MouseEvent<HTMLElement>) => {
            p.onClick?.(e);
            if (!e.defaultPrevented) handleSetActiveId(id);
          },
        };

    return cloneElement(
      child,
      {
        key: index,
        className: cn('relative inline-flex', child.props.className),
        'data-checked': activeId === id ? 'true' : 'false',
        ...interactionProps,
      },
      <>
        <AnimatePresence initial={false}>
          {activeId === id && (
            <motion.div
              layoutId={`background-${uniqueId}`}
              className={cn('absolute inset-0', className)}
              transition={transition}
              initial={{ opacity: defaultValue ? 1 : 0 }}
              animate={{
                opacity: 1,
              }}
              exit={{
                opacity: 0,
              }}
            />
          )}
        </AnimatePresence>
        <div className='z-10'>{child.props.children}</div>
      </>
    );
  });
}
