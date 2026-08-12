import { Message } from '../types';

export const copyToClipboard = async (text: string): Promise<boolean> => {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    } else {
      const textArea = document.createElement('textarea');
      textArea.value = text;
      textArea.style.position = 'fixed';
      textArea.style.left = '-999999px';
      textArea.style.top = '-999999px';
      document.body.appendChild(textArea);
      textArea.focus();
      textArea.select();
      const successful = document.execCommand('copy');
      textArea.remove();
      return successful;
    }
  } catch (err) {
    console.error('Failed to copy text: ', err);
    return false;
  }
};

export const formatConversationAsText = (
  messages: Message[],
  repoName: string,
  sessionId: string
): string => {
  const date = new Date().toLocaleDateString();
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  let output = `=== RepoTraverse Conversation Export ===\n`;
  output += `Repository: ${repoName || 'N/A'}\n`;
  output += `Session ID: ${sessionId || 'N/A'}\n`;
  output += `Exported: ${date} at ${time}\n`;
  output += `========================================\n\n`;

  messages.forEach((msg, idx) => {
    const sender = msg.sender === 'user' ? 'You' : 'Model';
    output += `[${msg.timestamp}] ${sender}:\n`;
    if (msg.toolCalls && msg.toolCalls.length > 0) {
      const tools = msg.toolCalls.map((t) => t.name).join(', ');
      output += `(Tools used: ${tools})\n`;
    }
    output += `${msg.text || msg.errorMessage || ''}\n`;
    if (idx < messages.length - 1) {
      output += `\n----------------------------------------\n\n`;
    }
  });

  return output;
};

export const formatConversationAsMarkdown = (
  messages: Message[],
  repoName: string,
  sessionId: string
): string => {
  const date = new Date().toLocaleDateString();
  const time = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  let output = `# RepoTraverse Conversation\n\n`;
  output += `- **Repository:** \`${repoName || 'N/A'}\`\n`;
  output += `- **Session ID:** \`${sessionId || 'N/A'}\`\n`;
  output += `- **Export Date:** ${date} ${time}\n\n`;
  output += `---\n\n`;

  messages.forEach((msg) => {
    const sender = msg.sender === 'user' ? '👤 **You**' : '🤖 **Model**';
    output += `### ${sender} *(${msg.timestamp})*\n\n`;
    if (msg.toolCalls && msg.toolCalls.length > 0) {
      const tools = msg.toolCalls.map((t) => `\`${t.name}\``).join(', ');
      output += `*Tools executed: ${tools}*\n\n`;
    }
    output += `${msg.text || msg.errorMessage || ''}\n\n`;
    output += `---\n\n`;
  });

  return output;
};

export const downloadFile = (filename: string, content: string, mimeType: string): void => {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
};
