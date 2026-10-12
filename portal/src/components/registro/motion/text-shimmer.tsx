'use client';
import React, { useMemo } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { cn } from '@/lib/utils';
import { useHidratado } from '@/lib/hidratado';

// Elementos permitidos, creados una sola vez fuera del render (react-hooks/static-components).
const ELEMENTOS = { p: motion.p, span: motion.span, div: motion.div } as const;

export type TextShimmerProps = {
  children: string;
  as?: keyof typeof ELEMENTOS;
  className?: string;
  duration?: number;
  spread?: number;
};

function TextShimmerComponent({
  children,
  as: Component = 'p',
  className,
  duration = 2,
  spread = 2,
}: TextShimmerProps) {
  const MotionComponent = ELEMENTOS[Component];
  // Portal: con movimiento reducido, texto estático en --muted (sin bucle). Hasta hidratar también
  // estático: useReducedMotion difiere entre servidor y cliente.
  const reducido = useReducedMotion() === true;
  const hidratado = useHidratado();

  const dynamicSpread = useMemo(() => {
    return children.length * spread;
  }, [children, spread]);

  if (reducido || !hidratado) {
    return <MotionComponent className={cn('inline-block text-muted', className)}>{children}</MotionComponent>;
  }

  return (
    <MotionComponent
      className={cn(
        'relative inline-block bg-[length:250%_100%,auto] bg-clip-text',
        // Espoir: base en --muted y brillo en --fg; los tokens ya cambian con el tema (sin dark:).
        'text-transparent [--base-color:var(--muted)] [--base-gradient-color:var(--fg)]',
        '[background-repeat:no-repeat,padding-box] [--bg:linear-gradient(90deg,transparent_calc(50%-var(--spread)),var(--base-gradient-color),transparent_calc(50%+var(--spread)))]',
        className
      )}
      initial={{ backgroundPosition: '100% center' }}
      animate={{ backgroundPosition: '0% center' }}
      transition={{
        repeat: Infinity,
        duration,
        ease: 'linear',
      }}
      style={
        {
          '--spread': `${dynamicSpread}px`,
          backgroundImage: `var(--bg), linear-gradient(var(--base-color), var(--base-color))`,
        } as React.CSSProperties
      }
    >
      {children}
    </MotionComponent>
  );
}

export const TextShimmer = React.memo(TextShimmerComponent);
