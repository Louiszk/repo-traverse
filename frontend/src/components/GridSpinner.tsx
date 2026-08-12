import React from 'react';

interface GridSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const GridSpinner: React.FC<GridSpinnerProps> = ({ size = 'md', className = '' }) => {
  // Perimeter order mapping to 3x3 grid slots (row, col):
  // (0,0)->0, (0,1)->1, (0,2)->2
  // (1,0)->7, (1,1)->empty, (1,2)->3
  // (2,0)->6, (2,1)->5, (2,2)->4
  const gridSlots = [
    { row: 0, col: 0, index: 0 },
    { row: 0, col: 1, index: 1 },
    { row: 0, col: 2, index: 2 },
    { row: 1, col: 0, index: 7 },
    { row: 1, col: 1, index: -1 }, // empty middle
    { row: 1, col: 2, index: 3 },
    { row: 2, col: 0, index: 6 },
    { row: 2, col: 1, index: 5 },
    { row: 2, col: 2, index: 4 },
  ];

  const sizeClasses = {
    sm: 'w-3.5 h-3.5 gap-[1.5px]',
    md: 'w-5 h-5 gap-[2px]',
    lg: 'w-6 h-6 gap-[2px]',
  };

  const cellClasses = {
    sm: 'rounded-[1px]',
    md: 'rounded-[2px]',
    lg: 'rounded-sm',
  };

  return (
    <div className={`grid grid-cols-3 grid-rows-3 aspect-square flex-shrink-0 ${sizeClasses[size]} ${className}`}>
      {gridSlots.map((slot, i) => {
        if (slot.index === -1) {
          return <div key={`empty-${i}`} className="w-full h-full" />;
        }

        const delay = (slot.index * 0.15).toFixed(2);

        return (
          <div
            key={`cell-${i}`}
            className={`w-full h-full ${cellClasses[size]} dark:bg-sienna-400/70 bg-softrose-500/70 dark:border-sienna-300/40 border-softrose-600/40 transition-all duration-150 animate-grid-chase`}
            style={{
              animationDelay: `${delay}s`,
            }}
          />
        );
      })}
    </div>
  );
};
