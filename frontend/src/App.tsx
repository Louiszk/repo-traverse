import React, { useState } from 'react';
import { Header } from './components/Header';
import { Footer } from './components/Footer';
import { RepoInput } from './components/RepoInput';
import { ChatInterface } from './components/ChatInterface';
import { LegalModal, LegalDocType } from './components/LegalModal';
import { CSRF_HEADER_NAME } from './utils/constants';
import { useRepoIndexer } from './hooks/useRepoIndexer';
import { useChatStream } from './hooks/useChatStream';

import { useTheme } from './hooks/useTheme';

export const App: React.FC = () => {
  const [githubUrl, setGithubUrl] = useState<string>('');
  const [sessionId, setSessionId] = useState<string>('');
  const [csrfToken, setCsrfToken] = useState<string>('');
  const [isContextFull, setIsContextFull] = useState<boolean>(false);
  const [legalModalType, setLegalModalType] = useState<LegalDocType | null>(null);

  const { isDark: darkMode, toggleTheme: toggleDarkMode } = useTheme();

  const {
    messages,
    setMessages,
    isSendingChat,
    handleSendMessage,
  } = useChatStream({
    sessionId,
    csrfToken,
    onContextFull: () => setIsContextFull(true),
    onAuthError: () => {
      setCsrfToken('');
      setSessionId('');
    },
  });

  const {
    handleIndexRepo,
    isLoadingRepo,
    indexingStage,
    repoError,
    resetIndexer,
  } = useRepoIndexer({
    onSuccess: (url, newSessionId, newCsrfToken) => {
      setGithubUrl(url);
      setSessionId(newSessionId);
      setCsrfToken(newCsrfToken);
      setMessages([]);
    },
    onContextFullReset: () => setIsContextFull(false),
  });

  const handleResetRepo = () => {
    resetIndexer();
    const currentSessionId = sessionId;
    const currentCsrf = csrfToken;

    setGithubUrl('');
    setSessionId('');
    setCsrfToken('');
    setMessages([]);
    setIsContextFull(false);

    if (currentSessionId) {
      fetch('/api/clear-session', {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          [CSRF_HEADER_NAME]: currentCsrf,
        },
        body: JSON.stringify({ session_id: currentSessionId }),
      }).catch((err) => console.error('Failed to clear session on backend:', err));
    }
  };

  return (
    <div className="h-screen flex flex-col antialiased font-sans transition-colors duration-200 overflow-hidden">
      <Header
        currentRepo={githubUrl}
        sessionId={sessionId}
        onResetRepo={handleResetRepo}
        darkMode={darkMode}
        onToggleDarkMode={toggleDarkMode}
      />

      <main className="flex-1 flex flex-col w-full min-h-0 overflow-hidden">
        {!sessionId ? (
          <RepoInput
            onIndexRepo={handleIndexRepo}
            isLoading={isLoadingRepo}
            stage={indexingStage}
            error={repoError}
            onOpenLegal={(tab) => setLegalModalType(tab)}
          />
        ) : (
          <ChatInterface
            sessionId={sessionId}
            csrfToken={csrfToken}
            githubUrl={githubUrl}
            messages={messages}
            onSendMessage={handleSendMessage}
            isSending={isSendingChat}
            onResetRepo={handleResetRepo}
            isContextFull={isContextFull}
            onAuthError={() => {
              setCsrfToken('');
              setSessionId('');
            }}
          />
        )}
      </main>

      <Footer onOpenLegal={(tab) => setLegalModalType(tab)} />

      <LegalModal
        isOpen={legalModalType !== null}
        activeTab={legalModalType || 'privacy'}
        onClose={() => setLegalModalType(null)}
        onTabChange={(tab) => setLegalModalType(tab)}
      />
    </div>
  );
};

export default App;
