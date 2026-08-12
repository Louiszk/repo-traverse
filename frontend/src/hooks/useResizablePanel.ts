import { useState, useEffect } from 'react';
import type { MouseEvent as ReactMouseEvent, RefObject } from 'react';

const DESKTOP_LAYOUT_BREAKPOINT = 1024;
const SMALL_LAYOUT_BREAKPOINT = 640;

export const useResizablePanel = (defaultWidth = 50, containerRef: RefObject<HTMLElement>) => {
  const [leftWidthPercent, setLeftWidthPercent] = useState<number>(defaultWidth);
  const [isResizing, setIsResizing] = useState<boolean>(false);
  const [isDesktopLayout, setIsDesktopLayout] = useState<boolean>(() =>
    typeof window === 'undefined' ? true : window.innerWidth >= DESKTOP_LAYOUT_BREAKPOINT
  );
  const [isSmallViewport, setIsSmallViewport] = useState<boolean>(() =>
    typeof window === 'undefined' ? false : window.innerWidth < SMALL_LAYOUT_BREAKPOINT
  );

  useEffect(() => {
    const handleResize = () => {
      const desktopLayout = window.innerWidth >= DESKTOP_LAYOUT_BREAKPOINT;
      setIsDesktopLayout(desktopLayout);
      setIsSmallViewport(window.innerWidth < SMALL_LAYOUT_BREAKPOINT);
      if (!desktopLayout) {
        setIsResizing(false);
      }
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDesktopLayout || !isResizing || !containerRef.current) return;
      const containerRect = containerRef.current.getBoundingClientRect();
      const newLeftPx = e.clientX - containerRect.left;
      const newPercent = (newLeftPx / containerRect.width) * 100;
      const clamped = Math.max(25, Math.min(75, newPercent));
      setLeftWidthPercent(clamped);
    };

    const handleMouseUp = () => {
      if (isResizing) {
        setIsResizing(false);
      }
    };

    if (isResizing) {
      window.addEventListener('mousemove', handleMouseMove);
      window.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDesktopLayout, isResizing, containerRef]);

  const handleMouseDown = (e: ReactMouseEvent) => {
    if (!isDesktopLayout) return;
    e.preventDefault();
    setIsResizing(true);
  };

  return {
    leftWidthPercent,
    setLeftWidthPercent,
    isResizing,
    isDesktopLayout,
    isSmallViewport,
    handleMouseDown
  };
};
