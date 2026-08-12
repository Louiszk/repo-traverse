import { useState, useEffect } from 'react';

export const syncThemeFromStorage = () => {
  const isDark = localStorage.getItem('theme') !== 'light';
  const root = document.documentElement;
  if (isDark) {
    root.classList.add('dark');
    localStorage.setItem('theme', 'dark');
  } else {
    root.classList.remove('dark');
    localStorage.setItem('theme', 'light');
  }
};

export const useTheme = () => {
  const [isDark, setIsDark] = useState<boolean>(() => {
    return localStorage.getItem('theme') !== 'light';
  });

  useEffect(() => {
    const root = document.documentElement;
    if (isDark) {
      root.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    } else {
      root.classList.remove('dark');
      localStorage.setItem('theme', 'light');
    }
  }, [isDark]);

  const toggleTheme = () => setIsDark(prev => !prev);

  return { isDark, toggleTheme };
};
