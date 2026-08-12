import React from 'react';
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Folder, Code2, FileCode } from 'lucide-react';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  onFileClick?: (path: string) => void;
  onDirClick?: (path: string) => void;
  onSymbolClick?: (symbol: string) => void;
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({
  content,
  className = '',
  onFileClick,
  onDirClick,
  onSymbolClick,
}) => {
  return (
    <div className={`markdown-body dark:text-slate-200 text-rose-950 text-sm leading-relaxed ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        urlTransform={(url) => {
          if (url.startsWith('file:') || url.startsWith('dir:') || url.startsWith('symbol:')) return url;
          return defaultUrlTransform(url);
        }}
        components={{
          h1: ({ children }) => (
            <h1 className="text-lg font-bold dark:text-slate-100 text-rose-950 mt-4 mb-2 border-b border-slate-700/30 pb-1">
              {children}
            </h1>
          ),
          h2: ({ children }) => (
            <h2 className="text-base font-semibold dark:text-slate-100 text-rose-950 mt-3 mb-1.5">
              {children}
            </h2>
          ),
          h3: ({ children }) => (
            <h3 className="text-sm font-semibold dark:text-slate-200 text-rose-900 mt-2 mb-1">
              {children}
            </h3>
          ),
          p: ({ children }) => (
            <p className="mb-2 last:mb-0">
              {children}
            </p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc list-inside space-y-1 mb-3 pl-1 dark:text-slate-300 text-slate-800">
              {children}
            </ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal list-inside space-y-1 mb-3 pl-1 dark:text-slate-300 text-slate-800">
              {children}
            </ol>
          ),
          li: ({ children }) => (
            <li className="leading-normal">
              {children}
            </li>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-l-4 dark:border-sienna-400 border-softrose-500 pl-3 italic text-slate-400 my-2 subtle-bg py-1 rounded-r">
              {children}
            </blockquote>
          ),
          code({ className: codeClassName, children, ...props }: React.ComponentPropsWithoutRef<'code'> & { inline?: boolean }) {
            const isMultiLine = typeof children === 'string' && children.includes('\n');
            const hasLanguage = Boolean(codeClassName && codeClassName.includes('language-'));
            const isBlock = isMultiLine || hasLanguage;

            if (!isBlock) {
              return (
                <code
                  className="px-1.5 py-0.5 rounded card-bg border dark:text-sienna-300 text-softrose-600 font-mono text-xs inline"
                  {...props}
                >
                  {children}
                </code>
              );
            }
            return (
              <div className="rounded-lg overflow-hidden border subtle-bg my-3">
                <div className="px-4 py-2 card-bg border-b flex items-center justify-between text-xs text-slate-400 font-mono">
                  <span>Code Snippet</span>
                </div>
                <pre className="p-4 font-mono text-xs dark:text-slate-200 text-rose-950 overflow-x-auto leading-relaxed">
                  <code className={codeClassName} {...props}>
                    {children}
                  </code>
                </pre>
              </div>
            );
          },
          table: ({ children }) => (
            <div className="overflow-x-auto my-3 rounded-lg border subtle-bg">
              <table className="w-full text-left text-xs border-collapse">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="card-bg px-3 py-2 dark:text-slate-200 text-rose-950 font-semibold border-b">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="px-3 py-2 border-b border-slate-700/30 dark:text-slate-300 text-slate-800">
              {children}
            </td>
          ),
          a: ({ href, children }: React.ComponentPropsWithoutRef<'a'>) => {
            const safeDecode = (str: string) => {
              try {
                return decodeURIComponent(str);
              } catch {
                return str;
              }
            };

            if (href && href.startsWith('file:')) {
              const filePath = safeDecode(href.slice(5));
              return (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (onFileClick) onFileClick(filePath);
                  }}
                  className="inline-flex items-center gap-1 align-baseline my-0.5 border-0 bg-transparent p-0 outline-none cursor-pointer"
                  title={`Click to inspect file ${filePath}`}
                >
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded card-bg dark:text-sienna-300 text-softrose-600 border text-[11px] font-mono hover:underline">
                    <FileCode className="w-3 h-3 dark:text-sienna-400 text-softrose-500 flex-shrink-0" />
                    <span>{filePath}</span>
                  </span>
                </button>
              );
            }
            if (href && href.startsWith('dir:')) {
              const dirPath = safeDecode(href.slice(4));
              return (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (onDirClick) onDirClick(dirPath);
                  }}
                  className="inline-flex items-center gap-1 align-baseline my-0.5 border-0 bg-transparent p-0 outline-none cursor-pointer"
                  title={`Click to browse directory ${dirPath || '/'}`}
                >
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded card-bg dark:text-sienna-300 text-softrose-600 border text-[11px] font-mono hover:underline">
                    <Folder className="w-3 h-3 dark:text-sienna-400 text-softrose-500 flex-shrink-0" />
                    <span>{dirPath || '/'}</span>
                  </span>
                </button>
              );
            }
            if (href && href.startsWith('symbol:')) {
              const symbolName = safeDecode(href.slice(7));
              return (
                <button
                  type="button"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (onSymbolClick) onSymbolClick(symbolName);
                  }}
                  className="inline-flex items-center gap-1 align-baseline my-0.5 border-0 bg-transparent p-0 outline-none cursor-pointer"
                  title={`Click to inspect symbol ${symbolName}`}
                >
                  <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded card-bg dark:text-sienna-300 text-softrose-600 border text-[11px] font-mono hover:underline">
                    <Code2 className="w-3 h-3 dark:text-sienna-400 text-softrose-500 flex-shrink-0" />
                    <span>{symbolName}</span>
                  </span>
                </button>
              );
            }
            return (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="dark:text-sienna-300 text-softrose-600 hover:underline font-medium transition-colors"
              >
                {children}
              </a>
            );
          },
          hr: () => <hr className="my-4 border-slate-700/30" />,
        }}
      >
        {content || ''}
      </ReactMarkdown>
    </div>
  );
};

